from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from typing import Dict, Any

from feedback.feedback_models import FeedbackCreateRequest, CustomDealFeedbackRequest
from infrastructure.db import SQL_ENGINE
from auth.auth_routes import get_current_user
from infrastructure.database_connection import DatabaseConnection
from personalization.score_builder import ScoreBuilder

router = APIRouter(prefix="/feedback", tags=["Feedback"])

ALLOWED_TYPES = {"GENERAL", "ORDER", "DELIVERY", "APP", "FOOD", "DEAL", "CUSTOM_DEAL"}

_executor = ThreadPoolExecutor(max_workers=2)


def _rebuild_profile(user_id: str) -> None:
    """Invalidate recommendation cache and rebuild the user profile.
    Intended to run in a background thread — never blocks the API response."""
    try:
        db_conn = DatabaseConnection.get_instance().get_connection()
        sb = ScoreBuilder(db_conn)
        sb.invalidate_cache(user_id)
        sb.build_user_profile(user_id)
    except Exception:
        pass  # Don't let personalization errors surface to the caller


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
                    user_id, order_id, item_id, deal_id, custom_deal_id,
                    rating, message, feedback_type
                )
                VALUES (
                    :user_id, :order_id, :item_id, :deal_id, :custom_deal_id,
                    :rating, :message, :feedback_type
                )
                RETURNING
                    feedback_id, user_id, order_id, item_id, deal_id, custom_deal_id,
                    rating, message, feedback_type, status, created_at
            """),
            {
                "user_id": user_id,
                "order_id": payload.order_id,
                "item_id": payload.item_id,
                "deal_id": payload.deal_id,
                "custom_deal_id": payload.custom_deal_id,
                "rating": payload.rating,
                "message": message,
                "feedback_type": feedback_type,
            },
        ).mappings().first()

    # Fire-and-forget: invalidate cache + rebuild personalization profile
    _executor.submit(_rebuild_profile, user_id)

    return {
        "message": "Feedback submitted successfully",
        "feedback": dict(result),
    }


# ─── Custom Deal Feedback ────────────────────────────────────────

@router.post("/custom-deal")
def submit_custom_deal_feedback(
    payload: CustomDealFeedbackRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Submit feedback for a custom deal order.
    - One overall CUSTOM_DEAL feedback row.
    - Optional per-item FOOD feedback rows.
    - Personalization: if no item ratings given, set soft_rating on all
      custom_deal_items to overall_rating.
    """
    user_id = str(current_user["user_id"])
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    with SQL_ENGINE.begin() as conn:
        # Verify order exists
        order_exists = conn.execute(
            text("SELECT 1 FROM public.orders WHERE order_id = :oid"),
            {"oid": payload.order_id},
        ).scalar()
        if not order_exists:
            raise HTTPException(status_code=404, detail="Order not found")

        # Verify custom deal exists
        deal_exists = conn.execute(
            text("SELECT 1 FROM public.custom_deals WHERE custom_deal_id = :cdid"),
            {"cdid": payload.custom_deal_id},
        ).scalar()
        if not deal_exists:
            raise HTTPException(status_code=404, detail="Custom deal not found")

        # Duplicate check: same user + order + custom_deal_id
        dup = conn.execute(
            text("""
                SELECT 1 FROM public.feedback
                WHERE user_id = :uid
                  AND order_id = :oid
                  AND custom_deal_id = :cdid
                  AND feedback_type = 'CUSTOM_DEAL'
                LIMIT 1
            """),
            {"uid": user_id, "oid": payload.order_id, "cdid": payload.custom_deal_id},
        ).scalar()
        if dup:
            raise HTTPException(
                status_code=400,
                detail="You have already reviewed this custom deal",
            )

        # 1. Insert overall custom deal feedback
        overall = conn.execute(
            text("""
                INSERT INTO public.feedback (
                    user_id, order_id, custom_deal_id,
                    rating, message, feedback_type
                )
                VALUES (
                    :user_id, :order_id, :custom_deal_id,
                    :rating, :message, 'CUSTOM_DEAL'
                )
                RETURNING
                    feedback_id, user_id, order_id, custom_deal_id,
                    rating, message, feedback_type, status, created_at
            """),
            {
                "user_id": user_id,
                "order_id": payload.order_id,
                "custom_deal_id": payload.custom_deal_id,
                "rating": payload.overall_rating,
                "message": message,
            },
        ).mappings().first()

        # 2. Insert per-item feedback rows (if any)
        item_feedback_rows = []
        if payload.item_ratings:
            for ir in payload.item_ratings:
                row = conn.execute(
                    text("""
                        INSERT INTO public.feedback (
                            user_id, order_id, item_id, custom_deal_id,
                            rating, message, feedback_type
                        )
                        VALUES (
                            :user_id, :order_id, :item_id, :custom_deal_id,
                            :rating, :message, 'FOOD'
                        )
                        RETURNING feedback_id, item_id, rating
                    """),
                    {
                        "user_id": user_id,
                        "order_id": payload.order_id,
                        "item_id": ir.item_id,
                        "custom_deal_id": payload.custom_deal_id,
                        "rating": ir.rating,
                        "message": message,
                    },
                ).mappings().first()
                item_feedback_rows.append(dict(row))

                # Update soft_rating on the specific custom_deal_items row
                conn.execute(
                    text("""
                        UPDATE public.custom_deal_items
                        SET soft_rating = :rating
                        WHERE custom_deal_id = :cdid AND item_id = :iid
                    """),
                    {
                        "rating": ir.rating,
                        "cdid": payload.custom_deal_id,
                        "iid": ir.item_id,
                    },
                )

        # 3. Personalization inference: if no per-item ratings, apply overall
        #    as soft_rating on ALL items in the deal
        if not payload.item_ratings:
            conn.execute(
                text("""
                    UPDATE public.custom_deal_items
                    SET soft_rating = :rating
                    WHERE custom_deal_id = :cdid
                """),
                {"rating": payload.overall_rating, "cdid": payload.custom_deal_id},
            )

    # Fire-and-forget: invalidate cache + rebuild personalization profile
    _executor.submit(_rebuild_profile, user_id)

    return {
        "message": "Custom deal feedback submitted successfully",
        "overall_feedback": dict(overall),
        "item_feedback": item_feedback_rows,
    }


# ─── GET Endpoints ───────────────────────────────────────────────

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
                    f.feedback_id, f.user_id, f.order_id,
                    f.item_id, f.deal_id, f.custom_deal_id,
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


# ─── GET /feedback/me/average ────────────────────────────────────
# Returns the current user's average rating across all their submitted
# feedback. Used by the re-engagement service to compute an engagement
# score for personalised push notifications.

@router.get("/me/average")
def get_my_average_rating(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user_id = str(current_user["user_id"])

    with SQL_ENGINE.connect() as conn:
        row = conn.execute(
            text("""
                SELECT
                    COUNT(*)                              AS total_reviews,
                    ROUND(AVG(rating)::numeric, 2)        AS average_rating
                FROM public.feedback
                WHERE user_id = :uid
                  AND rating IS NOT NULL
            """),
            {"uid": user_id},
        ).mappings().first()

    total = int(row["total_reviews"]) if row else 0
    avg   = float(row["average_rating"] or 0) if row else 0.0

    return {
        "user_id": user_id,
        "total_reviews": total,
        "average_rating": avg,
    }