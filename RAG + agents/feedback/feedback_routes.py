from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from typing import Dict, Any

from feedback.feedback_models import FeedbackCreateRequest
from infrastructure.db import SQL_ENGINE
from auth.auth_routes import get_current_user

router = APIRouter(prefix="/feedback", tags=["Feedback"])

ALLOWED_TYPES = {"GENERAL", "ORDER", "DELIVERY", "APP", "FOOD", "DEAL", "CUSTOM_DEAL"}


@router.post("")
def submit_feedback(
    payload: FeedbackCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    feedback_type = (payload.feedback_type or "GENERAL").upper()
    if feedback_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Invalid feedback type")

    user_id = str(current_user["user_id"])

    with SQL_ENGINE.begin() as conn:
        # Verify order exists if provided
        if payload.order_id is not None:
            order_exists = conn.execute(
                text("SELECT 1 FROM public.orders WHERE order_id = :oid"),
                {"oid": payload.order_id},
            ).scalar()
            if not order_exists:
                raise HTTPException(status_code=404, detail="Order not found")

        # Block duplicate overall-order review (item_id is None = overall review)
        if payload.order_id is not None and payload.item_id is None:
            duplicate = conn.execute(
                text("""
                    SELECT 1 FROM public.feedback
                    WHERE user_id = :uid AND order_id = :oid AND item_id IS NULL
                    LIMIT 1
                """),
                {"uid": user_id, "oid": payload.order_id},
            ).scalar()
            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="You have already reviewed this order",
                )

        result = conn.execute(
            text("""
                INSERT INTO public.feedback (
                    user_id, order_id, item_id, deal_id,
                    rating, message, feedback_type
                )
                VALUES (
                    :user_id, :order_id, :item_id, :deal_id,
                    :rating, :message, :feedback_type
                )
                RETURNING
                    feedback_id, user_id, order_id, item_id, deal_id,
                    rating, message, feedback_type, status, created_at
            """),
            {
                "user_id": user_id,
                "order_id": payload.order_id,
                "item_id": payload.item_id,
                "deal_id": payload.deal_id,
                "rating": payload.rating,
                "message": message,
                "feedback_type": feedback_type,
            },
        ).mappings().first()

    return {
        "message": "Feedback submitted successfully",
        "feedback": dict(result),
    }


@router.get("/order/{order_id}")
def get_feedback_for_order(
    order_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Return all feedback rows for a given order (auth required)."""
    with SQL_ENGINE.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    f.feedback_id, f.user_id, f.order_id, f.item_id, f.deal_id,
                    f.rating, f.message, f.feedback_type, f.status, f.created_at,
                    mi.item_name
                FROM public.feedback f
                LEFT JOIN public.menu_item mi ON mi.item_id = f.item_id
                WHERE f.order_id = :oid
                ORDER BY f.created_at
            """),
            {"oid": order_id},
        ).mappings().all()

    return {"order_id": order_id, "feedback": [dict(r) for r in rows]}


@router.get("/item/{item_id}")
def get_feedback_for_item(
    item_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Return average rating + all feedback entries for a menu item (admin analytics)."""
    with SQL_ENGINE.connect() as conn:
        agg = conn.execute(
            text("""
                SELECT
                    COUNT(*) AS total_reviews,
                    ROUND(AVG(rating)::numeric, 2) AS average_rating
                FROM public.feedback
                WHERE item_id = :iid
            """),
            {"iid": item_id},
        ).mappings().first()

        rows = conn.execute(
            text("""
                SELECT
                    f.feedback_id, f.user_id, f.order_id,
                    f.rating, f.message, f.feedback_type, f.status, f.created_at
                FROM public.feedback f
                WHERE f.item_id = :iid
                ORDER BY f.created_at DESC
            """),
            {"iid": item_id},
        ).mappings().all()

    return {
        "item_id": item_id,
        "total_reviews": int(agg["total_reviews"]),
        "average_rating": float(agg["average_rating"] or 0),
        "feedback": [dict(r) for r in rows],
    }