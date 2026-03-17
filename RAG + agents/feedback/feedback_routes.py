from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from feedback.feedback_models import FeedbackCreateRequest
from infrastructure.db import SQL_ENGINE
from auth.auth_routes import get_current_user

router = APIRouter(prefix="/feedback", tags=["Feedback"])


@router.post("")
def submit_feedback(
    payload: FeedbackCreateRequest,
    current_user=Depends(get_current_user),
):
    message = payload.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    allowed_types = {"GENERAL", "ORDER", "DELIVERY", "APP", "FOOD"}
    feedback_type = (payload.feedback_type or "GENERAL").upper()

    if feedback_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid feedback type")

    with SQL_ENGINE.begin() as conn:
        if payload.order_id is not None:
            order_exists = conn.execute(
                text("""
                    SELECT 1
                    FROM public.orders
                    WHERE order_id = :order_id
                """),
                {"order_id": payload.order_id},
            ).scalar()

            if not order_exists:
                raise HTTPException(status_code=404, detail="Order not found")

        result = conn.execute(
            text("""
                INSERT INTO public.feedback (
                    user_id,
                    order_id,
                    rating,
                    message,
                    feedback_type
                )
                VALUES (
                    :user_id,
                    :order_id,
                    :rating,
                    :message,
                    :feedback_type
                )
                RETURNING
                    feedback_id,
                    user_id,
                    order_id,
                    rating,
                    message,
                    feedback_type,
                    status,
                    created_at
            """),
            {
                "user_id": str(current_user["user_id"]),
                "order_id": payload.order_id,
                "rating": payload.rating,
                "message": message,
                "feedback_type": feedback_type,
            },
        ).mappings().first()

    return {
        "message": "Feedback submitted successfully",
        "feedback": dict(result),
    }