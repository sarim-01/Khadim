# orders/order_routes.py
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from infrastructure.db import SQL_ENGINE
from auth.auth_routes import get_current_user
from orders.orders_service import (
    place_order_sync,
    list_orders_for_user,
    get_order_detail_for_user,
)

router = APIRouter(prefix="/orders", tags=["orders"])


class PlaceOrderRequest(BaseModel):
    delivery_address: str = Field(default="N/A", min_length=2, max_length=500)
    delivery_fee: float = Field(default=0.0, ge=0.0, le=9999.0)
    tax_rate: float = Field(default=0.0, ge=0.0, le=1.0)


@router.post("/place_order")
def place_order_for_active_cart(
    req: PlaceOrderRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user_id = str(current_user["user_id"])

    with SQL_ENGINE.connect() as conn:
        cart_row = conn.execute(
            text("""
                SELECT cart_id
                FROM cart
                WHERE user_id = :uid AND status = 'active'
                ORDER BY updated_at DESC
                LIMIT 1
            """),
            {"uid": user_id},
        ).mappings().fetchone()

    if not cart_row:
        raise HTTPException(status_code=400, detail="No active cart found")

    cart_id = str(cart_row["cart_id"])

    return place_order_sync(
        cart_id=cart_id,
        delivery_address=req.delivery_address,
        delivery_fee=req.delivery_fee,
        tax_rate=req.tax_rate,
    )


@router.get("/my")
def my_orders(current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    return {
        "success": True,
        "orders": list_orders_for_user(user_id),
    }


@router.get("/{order_id}")
def order_detail(order_id: int, current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    return {
        "success": True,
        "order": get_order_detail_for_user(order_id, user_id),
    }