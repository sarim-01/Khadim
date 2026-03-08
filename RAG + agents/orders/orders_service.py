# orders/orders_service.py
from typing import Dict, Any, List, Optional
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
import json

from infrastructure.db import SQL_ENGINE


def _station_for_item(item_category: Optional[str], item_cuisine: Optional[str]) -> str:
    item_category = (item_category or "").lower()
    item_cuisine = (item_cuisine or "").lower()

    if item_category == "drink":
        return "DRINKS"
    if item_category == "bread":
        return "TANDOOR"
    if item_cuisine == "bbq":
        return "GRILL"
    if item_cuisine == "chinese":
        return "WOK"
    if item_cuisine == "desi":
        return "STOVE"
    return "FRY"


def _pick_chef_for_menu_item(conn, menu_item_id: int) -> str:
    row = conn.execute(
        text("""
            WITH candidates AS (
                SELECT c.cheff_name
                FROM menu_item_chefs mic
                JOIN chef c ON c.cheff_id = mic.chef_id
                WHERE mic.menu_item_id = :menu_item_id
                  AND c.active_status = true
            ),
            load AS (
                SELECT assigned_chef, COUNT(*) AS cnt
                FROM kitchen_tasks
                WHERE status IN ('QUEUED', 'IN_PROGRESS')
                GROUP BY assigned_chef
            )
            SELECT cand.cheff_name
            FROM candidates cand
            LEFT JOIN load l ON l.assigned_chef = cand.cheff_name
            ORDER BY COALESCE(l.cnt, 0) ASC
            LIMIT 1
        """),
        {"menu_item_id": menu_item_id},
    ).fetchone()

    return row[0] if row else "Unassigned"


def _expand_deal_items(conn, deal_id: int, deal_qty: int) -> List[Dict[str, Any]]:
    rows = conn.execute(
        text("""
            SELECT di.menu_item_id, di.quantity, mi.item_name, mi.item_category, mi.item_cuisine, mi.prep_time_minutes
            FROM deal_item di
            JOIN menu_item mi ON mi.item_id = di.menu_item_id
            WHERE di.deal_id = :deal_id
        """),
        {"deal_id": deal_id},
    ).mappings().all()

    expanded: List[Dict[str, Any]] = []
    for row in rows:
        expanded.append({
            "menu_item_id": int(row["menu_item_id"]),
            "qty": int(row["quantity"] or 1) * deal_qty,
            "item_name": row["item_name"],
            "item_category": row["item_category"],
            "item_cuisine": row["item_cuisine"],
            "prep_time_minutes": int(row["prep_time_minutes"] or 10),
        })

    return expanded


def _create_kitchen_tasks(conn, order_id: int, cart_items: List[Dict[str, Any]]) -> int:
    kitchen_items: List[Dict[str, Any]] = []

    for row in cart_items:
        item_type = row["item_type"]
        item_id = int(row["item_id"])
        qty = int(row["quantity"] or 1)

        if item_type == "menu_item":
            mi = conn.execute(
                text("""
                    SELECT item_id, item_name, item_category, item_cuisine, prep_time_minutes
                    FROM menu_item
                    WHERE item_id = :id
                    LIMIT 1
                """),
                {"id": item_id},
            ).mappings().fetchone()

            if not mi:
                continue

            kitchen_items.append({
                "menu_item_id": int(mi["item_id"]),
                "qty": qty,
                "item_name": mi["item_name"],
                "item_category": mi["item_category"],
                "item_cuisine": mi["item_cuisine"],
                "prep_time_minutes": int(mi["prep_time_minutes"] or 10),
            })

        elif item_type == "deal":
            kitchen_items.extend(_expand_deal_items(conn, item_id, qty))

    max_prep = 0

    for idx, item in enumerate(kitchen_items, start=1):
        menu_item_id = int(item["menu_item_id"])
        qty = int(item["qty"])
        item_name = item["item_name"]
        station = _station_for_item(item["item_category"], item["item_cuisine"])
        assigned_chef = _pick_chef_for_menu_item(conn, menu_item_id)
        estimated_minutes = max(1, int(item["prep_time_minutes"] or 10))

        max_prep = max(max_prep, estimated_minutes)

        task_id = f"{order_id}-{idx}"

        conn.execute(
            text("""
                INSERT INTO kitchen_tasks
                  (task_id, order_id, menu_item_id, item_name, qty, station, assigned_chef, estimated_minutes, status)
                VALUES
                  (:task_id, :order_id, :menu_item_id, :item_name, :qty, :station, :assigned_chef, :estimated_minutes, 'QUEUED')
            """),
            {
                "task_id": task_id,
                "order_id": order_id,
                "menu_item_id": menu_item_id,
                "item_name": item_name,
                "qty": qty,
                "station": station,
                "assigned_chef": assigned_chef,
                "estimated_minutes": estimated_minutes,
            },
        )

    return max_prep


def place_order_sync(
    cart_id: str,
    delivery_address: str = "N/A",
    delivery_fee: float = 0.0,
    tax_rate: float = 0.0,
) -> Dict[str, Any]:
    """
    Production checkout flow:
    - lock active cart
    - idempotent by cart_id
    - insert orders
    - insert order_items
    - expand deals into kitchen tasks
    - mark cart inactive + clear cart_items
    """
    try:
        with SQL_ENGINE.begin() as conn:
            cart_row = conn.execute(
                text("""
                    SELECT cart_id, user_id, status
                    FROM cart
                    WHERE cart_id = :cid
                    FOR UPDATE
                """),
                {"cid": cart_id},
            ).mappings().fetchone()

            if not cart_row:
                raise HTTPException(status_code=404, detail="Cart not found")

            if (cart_row["status"] or "").lower() != "active":
                raise HTTPException(
                    status_code=400,
                    detail=f"Cart is not active (status={cart_row['status']})"
                )

            existing = conn.execute(
                text("""
                    SELECT order_id, status, total_price, subtotal, tax, delivery_fee, estimated_prep_time_minutes
                    FROM orders
                    WHERE cart_id = :cid
                    LIMIT 1
                """),
                {"cid": cart_id},
            ).mappings().fetchone()

            if existing:
                return {
                    "success": True,
                    "order_id": int(existing["order_id"]),
                    "cart_id": cart_id,
                    "status": existing["status"],
                    "subtotal": float(existing["subtotal"] or 0),
                    "tax": float(existing["tax"] or 0),
                    "delivery_fee": float(existing["delivery_fee"] or 0),
                    "total_price": float(existing["total_price"] or 0),
                    "total": float(existing["total_price"] or 0),
                    "estimated_prep_time_minutes": int(existing["estimated_prep_time_minutes"] or 0),
                    "idempotent": True,
                    "message": "Order already exists for this cart",
                }

            conn.execute(
                text("""
                    UPDATE cart
                    SET status = 'checking_out', updated_at = NOW()
                    WHERE cart_id = :cid
                """),
                {"cid": cart_id},
            )

            cart_items = conn.execute(
                text("""
                    SELECT item_id, item_type, item_name, quantity, unit_price
                    FROM cart_items
                    WHERE cart_id = :cid
                    ORDER BY item_type, item_id
                """),
                {"cid": cart_id},
            ).mappings().all()

            if not cart_items:
                conn.execute(
                    text("""
                        UPDATE cart
                        SET status = 'active', updated_at = NOW()
                        WHERE cart_id = :cid
                    """),
                    {"cid": cart_id},
                )
                raise HTTPException(status_code=400, detail="Cart is empty")

            subtotal = round(
                sum(float(r["unit_price"] or 0) * int(r["quantity"] or 0) for r in cart_items),
                2,
            )
            tax = round(subtotal * float(tax_rate), 2)
            delivery_fee = round(float(delivery_fee), 2)
            total = round(subtotal + tax + delivery_fee, 2)

            summary = {
                "items": [
                    {
                        "item_id": int(r["item_id"]),
                        "item_type": r["item_type"],
                        "item_name": r["item_name"],
                        "quantity": int(r["quantity"]),
                        "unit_price": float(r["unit_price"]),
                        "line_total": round(float(r["unit_price"]) * int(r["quantity"]), 2),
                    }
                    for r in cart_items
                ],
                "subtotal": subtotal,
                "tax": tax,
                "delivery_fee": delivery_fee,
                "total_price": total,
            }

            order_row = conn.execute(
                text("""
                    INSERT INTO orders
                      (cart_id, total_price, order_data, status, delivery_address, subtotal, tax, delivery_fee)
                    VALUES
                      (:cart_id, :total_price, CAST(:order_data AS jsonb), 'confirmed', :delivery_address, :subtotal, :tax, :delivery_fee)
                    RETURNING order_id
                """),
                {
                    "cart_id": cart_id,
                    "total_price": total,
                    "order_data": json.dumps(summary),
                    "delivery_address": delivery_address,
                    "subtotal": subtotal,
                    "tax": tax,
                    "delivery_fee": delivery_fee,
                },
            ).mappings().fetchone()

            order_id = int(order_row["order_id"])

            for r in cart_items:
                unit_price = float(r["unit_price"] or 0)
                qty = int(r["quantity"] or 0)
                line_total = round(unit_price * qty, 2)

                conn.execute(
                    text("""
                        INSERT INTO order_items
                          (order_id, item_type, item_id, name_snapshot, unit_price_snapshot, quantity, line_total)
                        VALUES
                          (:order_id, :item_type, :item_id, :name_snapshot, :unit_price_snapshot, :quantity, :line_total)
                    """),
                    {
                        "order_id": order_id,
                        "item_type": r["item_type"],
                        "item_id": int(r["item_id"]),
                        "name_snapshot": r["item_name"] or "",
                        "unit_price_snapshot": unit_price,
                        "quantity": qty,
                        "line_total": line_total,
                    },
                )

            estimated_prep = _create_kitchen_tasks(conn, order_id, cart_items)

            conn.execute(
                text("""
                    UPDATE orders
                    SET estimated_prep_time_minutes = :m, updated_at = NOW()
                    WHERE order_id = :oid
                """),
                {"m": estimated_prep, "oid": order_id},
            )

            conn.execute(
                text("DELETE FROM cart_items WHERE cart_id = :cid"),
                {"cid": cart_id},
            )
            conn.execute(
                text("""
                    UPDATE cart
                    SET status = 'inactive', updated_at = NOW()
                    WHERE cart_id = :cid
                """),
                {"cid": cart_id},
            )

            return {
                "success": True,
                "order_id": order_id,
                "cart_id": cart_id,
                "status": "confirmed",
                "subtotal": subtotal,
                "tax": tax,
                "delivery_fee": delivery_fee,
                "total_price": total,
                "total": total,
                "estimated_prep_time_minutes": estimated_prep,
                "idempotent": False,
                "message": "Order placed successfully",
            }

    except IntegrityError:
        with SQL_ENGINE.connect() as conn:
            existing = conn.execute(
                text("""
                    SELECT order_id, status, total_price, subtotal, tax, delivery_fee, estimated_prep_time_minutes
                    FROM orders
                    WHERE cart_id = :cid
                    LIMIT 1
                """),
                {"cid": cart_id},
            ).mappings().fetchone()

        if existing:
            return {
                "success": True,
                "order_id": int(existing["order_id"]),
                "cart_id": cart_id,
                "status": existing["status"],
                "subtotal": float(existing["subtotal"] or 0),
                "tax": float(existing["tax"] or 0),
                "delivery_fee": float(existing["delivery_fee"] or 0),
                "total_price": float(existing["total_price"] or 0),
                "total": float(existing["total_price"] or 0),
                "estimated_prep_time_minutes": int(existing["estimated_prep_time_minutes"] or 0),
                "idempotent": True,
                "message": "Order already existed for this cart",
            }
        raise HTTPException(status_code=500, detail="Order creation race failed unexpectedly")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"place_order_sync failed: {repr(e)}")


def list_orders_for_user(user_id: str) -> List[Dict[str, Any]]:
    with SQL_ENGINE.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    o.order_id,
                    o.cart_id,
                    o.status,
                    o.total_price,
                    o.subtotal,
                    o.tax,
                    o.delivery_fee,
                    o.estimated_prep_time_minutes,
                    o.delivery_address,
                    o.created_at,
                    o.updated_at
                FROM orders o
                JOIN cart c ON c.cart_id = o.cart_id
                WHERE c.user_id = :uid
                ORDER BY o.created_at DESC, o.order_id DESC
            """),
            {"uid": user_id},
        ).mappings().all()

    return [
        {
            "order_id": int(r["order_id"]),
            "cart_id": str(r["cart_id"]),
            "status": r["status"],
            "total_price": float(r["total_price"] or 0),
            "subtotal": float(r["subtotal"] or 0),
            "tax": float(r["tax"] or 0),
            "delivery_fee": float(r["delivery_fee"] or 0),
            "estimated_prep_time_minutes": int(r["estimated_prep_time_minutes"] or 0),
            "delivery_address": r["delivery_address"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


def get_order_detail_for_user(order_id: int, user_id: str) -> Dict[str, Any]:
    with SQL_ENGINE.connect() as conn:
        order_row = conn.execute(
            text("""
                SELECT
                    o.order_id,
                    o.cart_id,
                    o.status,
                    o.total_price,
                    o.subtotal,
                    o.tax,
                    o.delivery_fee,
                    o.estimated_prep_time_minutes,
                    o.delivery_address,
                    o.created_at,
                    o.updated_at
                FROM orders o
                JOIN cart c ON c.cart_id = o.cart_id
                WHERE o.order_id = :oid
                  AND c.user_id = :uid
                LIMIT 1
            """),
            {"oid": order_id, "uid": user_id},
        ).mappings().fetchone()

        if not order_row:
            raise HTTPException(status_code=404, detail="Order not found")

        items = conn.execute(
            text("""
                SELECT
                    id,
                    item_type,
                    item_id,
                    name_snapshot,
                    unit_price_snapshot,
                    quantity,
                    line_total
                FROM order_items
                WHERE order_id = :oid
                ORDER BY id ASC
            """),
            {"oid": order_id},
        ).mappings().all()

    return {
        "order_id": int(order_row["order_id"]),
        "cart_id": str(order_row["cart_id"]),
        "status": order_row["status"],
        "total_price": float(order_row["total_price"] or 0),
        "subtotal": float(order_row["subtotal"] or 0),
        "tax": float(order_row["tax"] or 0),
        "delivery_fee": float(order_row["delivery_fee"] or 0),
        "estimated_prep_time_minutes": int(order_row["estimated_prep_time_minutes"] or 0),
        "delivery_address": order_row["delivery_address"],
        "created_at": order_row["created_at"].isoformat() if order_row["created_at"] else None,
        "updated_at": order_row["updated_at"].isoformat() if order_row["updated_at"] else None,
        "items": [
            {
                "id": int(i["id"]),
                "item_type": i["item_type"],
                "item_id": int(i["item_id"]),
                "name": i["name_snapshot"],
                "unit_price": float(i["unit_price_snapshot"] or 0),
                "quantity": int(i["quantity"] or 0),
                "line_total": float(i["line_total"] or 0),
            }
            for i in items
        ],
    }