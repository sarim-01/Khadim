# cart_routes.py
from typing import Dict, Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from infrastructure.db import SQL_ENGINE
from auth.auth_routes import get_current_user

# If you want to reuse your CartTools DB logic:
from cart.cart_agent import CartTools
from orders.orders_service import place_order_sync



router = APIRouter(prefix="/cart", tags=["cart"])

cart_tools = CartTools()

ItemType = Literal["menu_item", "deal"]


class CreateCartResponse(BaseModel):
    success: bool
    cart_id: str


class AddItemRequest(BaseModel):
    cart_id: str
    item_type: ItemType
    item_id: int
    quantity: int = Field(default=1, ge=1, le=99)


class RemoveItemRequest(BaseModel):
    cart_id: str
    item_type: ItemType
    item_id: int

class SetQtyRequest(BaseModel):
    cart_id: str
    item_type: ItemType
    item_id: int
    quantity: int = Field(ge=0, le=99)


def _assert_cart_belongs_to_user(cart_id: str, user_id: str) -> None:
    with SQL_ENGINE.connect() as conn:
        row = conn.execute(
            text("SELECT user_id FROM cart WHERE cart_id = :cart_id LIMIT 1"),
            {"cart_id": cart_id},
        ).mappings().fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Cart not found")

    if str(row["user_id"]) != user_id:
        raise HTTPException(status_code=403, detail="Cart does not belong to user")


@router.put("/items/qty")
def set_quantity(req: SetQtyRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    _assert_cart_belongs_to_user(req.cart_id, user_id)

    if req.quantity == 0:
        with SQL_ENGINE.begin() as conn:
            conn.execute(
                text("""
                    DELETE FROM cart_items
                    WHERE cart_id = :cart_id AND item_id = :item_id AND item_type = :item_type
                """),
                {"cart_id": req.cart_id, "item_id": req.item_id, "item_type": req.item_type}
            )
        return {"success": True, "message": "Item removed"}

    # Ensure item exists (and get server-truth name/price)
    snapshot = _fetch_item_snapshot(req.item_type, req.item_id)

    # Upsert with exact quantity
    is_deal = "deal_id" in snapshot
    item_id = snapshot.get("deal_id") if is_deal else snapshot.get("item_id")
    item_type = "deal" if is_deal else "menu_item"
    item_name = snapshot.get("item_name")
    price = snapshot.get("price")

    with SQL_ENGINE.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO cart_items (cart_id, item_id, item_type, item_name, quantity, unit_price)
                VALUES (:cart_id, :item_id, :item_type, :item_name, :quantity, :unit_price)
                ON CONFLICT (cart_id, item_id, item_type)
                DO UPDATE SET quantity = EXCLUDED.quantity, unit_price = EXCLUDED.unit_price, item_name = EXCLUDED.item_name
            """),
            {
                "cart_id": req.cart_id,
                "item_id": item_id,
                "item_type": item_type,
                "item_name": item_name,
                "quantity": req.quantity,
                "unit_price": price,
            }
        )

    return {"success": True, "message": "Quantity updated"}


def _fetch_item_snapshot(item_type: str, item_id: int) -> Dict[str, Any]:
    """
    Server-truth: look up name + price from DB.
    Never trust client-sent name/price.
    """
    if item_type == "menu_item":
        q = text("""
            SELECT item_id, item_name, item_price
            FROM menu_item
            WHERE item_id = :id
            LIMIT 1
        """)
        with SQL_ENGINE.connect() as conn:
            row = conn.execute(q, {"id": item_id}).mappings().fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Menu item not found")

        return {
            "item_id": int(row["item_id"]),
            "item_name": row["item_name"],
            "price": float(row["item_price"]),
        }

    if item_type == "deal":
        q = text("""
            SELECT deal_id, deal_name, deal_price
            FROM deal
            WHERE deal_id = :id
            LIMIT 1
        """)
        with SQL_ENGINE.connect() as conn:
            row = conn.execute(q, {"id": item_id}).mappings().fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Deal not found")

        # CartTools uses deal_id to detect deal
        return {
            "deal_id": int(row["deal_id"]),
            "item_name": row["deal_name"],   # CartTools expects item_name
            "price": float(row["deal_price"]),
        }

    raise HTTPException(status_code=400, detail="Invalid item_type")



@router.post("/active", response_model=CreateCartResponse)
def active_cart(current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    res = cart_tools.create_cart(user_id)
    return {"success": True, "cart_id": res["cart_id"]}


@router.post("/create", response_model=CreateCartResponse)
def create_cart(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Create or reuse cart for this user.
    IMPORTANT: your CartTools currently uses user_id as cart_id (UUID),
    which is okay for now because auth user_id is UUID.
    """
    user_id = str(current_user["user_id"])
    res = cart_tools.create_cart(user_id)
    return {"success": True, "cart_id": res["cart_id"]}


@router.post("/items/add")
def add_item(req: AddItemRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    # Optional hard guard: cart_id must match user_id if you are using that approach
    user_id = str(current_user["user_id"])
    _assert_cart_belongs_to_user(req.cart_id, user_id)

    snapshot = _fetch_item_snapshot(req.item_type, req.item_id)

    # CartTools.add_item(cart_id, item_data, quantity)
    res = cart_tools.add_item(req.cart_id, snapshot, req.quantity)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to add item"))
    return res


@router.post("/items/remove")
def remove_item(req: RemoveItemRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    _assert_cart_belongs_to_user(req.cart_id, user_id)
    # Better than remove by name: delete by id + type directly
    with SQL_ENGINE.begin() as conn:
        result = conn.execute(
            text("""
                DELETE FROM cart_items
                WHERE cart_id = :cart_id AND item_id = :item_id AND item_type = :item_type
            """),
            {"cart_id": req.cart_id, "item_id": req.item_id, "item_type": req.item_type}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found in cart")

    return {"success": True, "message": "Removed item"}


@router.get("/{cart_id}")
def get_summary(cart_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    _assert_cart_belongs_to_user(cart_id, user_id)

    res = cart_tools.get_cart_summary(cart_id)
    res["cart_id"] = cart_id
    return res


# cart_routes.py (replace PlaceOrderRequest + /place_order endpoint)

class PlaceOrderRequest(BaseModel):
    cart_id: str
    delivery_address: str = Field(default="N/A", min_length=2, max_length=500)
    delivery_fee: float = Field(default=0.0, ge=0.0, le=9999.0)
    tax_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    transaction_id: Optional[str] = None


@router.post("/place_order")
def place_order(req: PlaceOrderRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    _assert_cart_belongs_to_user(req.cart_id, user_id)

    res = place_order_sync(
        cart_id=req.cart_id,
        delivery_address=req.delivery_address,
        delivery_fee=req.delivery_fee,
        tax_rate=req.tax_rate,
        transaction_id=req.transaction_id,
    )
    return res