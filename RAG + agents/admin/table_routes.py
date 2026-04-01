import random
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

from auth.auth_routes import get_current_user
from infrastructure.db import SQL_ENGINE

router = APIRouter(prefix="/admin/tables", tags=["admin-tables"])

ADMIN_EMAIL = "admin@gmail.com"


def _require_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if current_user.get("email") != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


class CreateTableRequest(BaseModel):
    table_number: str
    table_pin: str = Field(min_length=1)


@router.post("")
def create_table(payload: CreateTableRequest):
    table_number = payload.table_number.strip()
    table_pin = payload.table_pin.strip()

    if not table_number or not table_pin:
        raise HTTPException(status_code=400, detail="table_number and table_pin are required")

    with SQL_ENGINE.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO public.restaurant_tables (table_number, table_pin, status)
                VALUES (:table_number, :table_pin, 'available')
                RETURNING table_id, table_number, status
                """
            ),
            {"table_number": table_number, "table_pin": table_pin},
        ).mappings().fetchone()

    return {
        "table_id": str(row["table_id"]),
        "table_number": row["table_number"],
        "status": row["status"],
    }


@router.get("")
def list_tables():
    with SQL_ENGINE.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    t.table_id,
                    t.table_number,
                    t.status,
                    s.session_id,
                    s.round_count,
                    s.total_amount
                FROM public.restaurant_tables t
                LEFT JOIN public.dine_in_sessions s
                    ON s.table_id = t.table_id
                   AND s.status = 'active'
                ORDER BY t.table_number
                """
            )
        ).mappings().fetchall()

    tables = []
    for row in rows:
        tables.append(
            {
                "table_id": str(row["table_id"]),
                "table_number": row["table_number"],
                "status": row["status"],
                "session_id": str(row["session_id"]) if row["session_id"] else None,
                "round_count": int(row["round_count"] or 0),
                "total_amount": float(row["total_amount"] or 0),
            }
        )

    return {"tables": tables}


@router.patch("/{table_id}/close")
def close_table(table_id: str):
    with SQL_ENGINE.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE public.dine_in_sessions
                SET status = 'closed', ended_at = NOW()
                WHERE table_id = :table_id
                  AND status = 'active'
                """
            ),
            {"table_id": table_id},
        )

        table_update = conn.execute(
            text(
                """
                UPDATE public.restaurant_tables
                SET status = 'available'
                WHERE table_id = :table_id
                """
            ),
            {"table_id": table_id},
        )

        if table_update.rowcount == 0:
            raise HTTPException(status_code=404, detail="Table not found")

    return {"success": True, "message": "Table closed"}


@router.get("/{table_id}/orders")
def get_table_orders(table_id: str):
    with SQL_ENGINE.connect() as conn:
        session_row = conn.execute(
            text(
                """
                SELECT session_id
                FROM public.dine_in_sessions
                WHERE table_id = :table_id
                  AND status = 'active'
                LIMIT 1
                """
            ),
            {"table_id": table_id},
        ).mappings().fetchone()

        if not session_row:
            raise HTTPException(status_code=404, detail="No active session for this table")

        rows = conn.execute(
            text(
                """
                SELECT
                    o.order_id,
                    o.session_id,
                    o.status,
                    o.total_price,
                    o.created_at
                FROM public.orders o
                JOIN public.dine_in_sessions s ON s.session_id = o.session_id
                WHERE s.table_id = :table_id
                  AND s.status = 'active'
                ORDER BY o.created_at DESC
                """
            ),
            {"table_id": table_id},
        ).mappings().fetchall()

    orders = []
    for row in rows:
        orders.append(
            {
                "order_id": int(row["order_id"]),
                "session_id": str(row["session_id"]) if row["session_id"] else None,
                "status": row["status"],
                "total_price": float(row["total_price"] or 0),
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
        )

    return {
        "table_id": table_id,
        "session_id": str(session_row["session_id"]),
        "orders": orders,
    }


class CreateTableNumberRequest(BaseModel):
    table_number: int


@router.get("/all")
def list_all_tables(_: Dict = Depends(_require_admin)):
    with SQL_ENGINE.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT rt.table_id, rt.table_number, rt.status, rt.table_pin,
                       ds.session_id, ds.started_at, ds.total_amount, ds.round_count,
                       wc.call_id AS pending_waiter_call
                FROM restaurant_tables rt
                LEFT JOIN dine_in_sessions ds
                    ON rt.table_id = ds.table_id AND ds.status = 'active'
                LEFT JOIN waiter_calls wc
                    ON rt.table_id = wc.table_id AND wc.resolved = false
                ORDER BY rt.table_number ASC
                """
            )
        ).mappings().fetchall()

    result = []
    for row in rows:
        result.append(
            {
                "table_id": str(row["table_id"]),
                "table_number": row["table_number"],
                "status": row["status"],
                "table_pin": row["table_pin"],
                "session_id": str(row["session_id"]) if row["session_id"] else None,
                "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                "total_amount": float(row["total_amount"] or 0),
                "round_count": int(row["round_count"] or 0),
                "pending_waiter_call": bool(row["pending_waiter_call"]),
            }
        )

    return result


@router.get("/{table_id}/session-detail")
def get_table_session_detail(table_id: str, _: Dict = Depends(_require_admin)):
    with SQL_ENGINE.connect() as conn:
        session_row = conn.execute(
            text(
                """
                SELECT ds.session_id, ds.started_at, ds.total_amount,
                       ds.round_count, rt.table_number
                FROM dine_in_sessions ds
                JOIN restaurant_tables rt ON rt.table_id = ds.table_id
                WHERE ds.table_id = :table_id AND ds.status = 'active'
                LIMIT 1
                """
            ),
            {"table_id": table_id},
        ).mappings().fetchone()

        if not session_row:
            raise HTTPException(status_code=404, detail="No active session for this table")

        order_rows = conn.execute(
            text(
                """
                SELECT order_id, round_number, total_price, status, created_at
                FROM orders
                WHERE session_id = :session_id
                ORDER BY round_number ASC, created_at ASC
                """
            ),
            {"session_id": session_row["session_id"]},
        ).mappings().fetchall()

        orders = []
        for order_row in order_rows:
            item_rows = conn.execute(
                text(
                    """
                    SELECT name_snapshot, quantity,
                           unit_price_snapshot, line_total
                    FROM order_items
                    WHERE order_id = :order_id
                    ORDER BY id ASC
                    """
                ),
                {"order_id": order_row["order_id"]},
            ).mappings().fetchall()

            items = []
            for item in item_rows:
                items.append(
                    {
                        "name": item["name_snapshot"],
                        "quantity": int(item["quantity"] or 0),
                        "unit_price": float(item["unit_price_snapshot"] or 0),
                        "line_total": float(item["line_total"] or 0),
                    }
                )

            orders.append(
                {
                    "order_id": int(order_row["order_id"]),
                    "round_number": int(order_row["round_number"] or 0),
                    "total_price": float(order_row["total_price"] or 0),
                    "status": order_row["status"],
                    "created_at": order_row["created_at"].isoformat()
                    if order_row["created_at"]
                    else None,
                    "items": items,
                }
            )

    return {
        "table_number": session_row["table_number"],
        "session_id": str(session_row["session_id"]),
        "started_at": session_row["started_at"].isoformat() if session_row["started_at"] else None,
        "total_amount": float(session_row["total_amount"] or 0),
        "round_count": int(session_row["round_count"] or 0),
        "orders": orders,
    }


@router.post("/create")
def create_table_with_random_pin(payload: CreateTableNumberRequest, _: Dict = Depends(_require_admin)):
    pin = f"{random.randint(0, 999999):06d}"
    try:
        with SQL_ENGINE.begin() as conn:
            normalized_table_number = str(payload.table_number).strip()

            existing = conn.execute(
                text(
                    """
                    SELECT table_id
                    FROM restaurant_tables
                    WHERE TRIM(table_number) = :table_number
                    LIMIT 1
                    """
                ),
                {"table_number": normalized_table_number},
            ).mappings().fetchone()

            if existing:
                raise HTTPException(status_code=400, detail="Table number already exists")

            row = conn.execute(
                text(
                    """
                    INSERT INTO restaurant_tables (table_number, status, table_pin)
                    VALUES (:table_number, 'available', :pin)
                    RETURNING table_id, table_number, status, table_pin
                    """
                ),
                {"table_number": normalized_table_number, "pin": pin},
            ).mappings().fetchone()
    except IntegrityError as exc:
        if "unique" in str(exc).lower() or "table_number" in str(exc).lower():
            raise HTTPException(status_code=400, detail="Table number already exists")
        raise

    return {
        "table_id": str(row["table_id"]),
        "table_number": row["table_number"],
        "status": row["status"],
        "table_pin": row["table_pin"],
    }


@router.post("/{table_id}/regenerate-pin")
def regenerate_table_pin(table_id: str, _: Dict = Depends(_require_admin)):
    new_pin = f"{random.randint(0, 999999):06d}"
    with SQL_ENGINE.begin() as conn:
        updated = conn.execute(
            text(
                """
                UPDATE restaurant_tables
                SET table_pin = :pin
                WHERE table_id = :table_id
                """
            ),
            {"pin": new_pin, "table_id": table_id},
        )

        if updated.rowcount == 0:
            raise HTTPException(status_code=404, detail="Table not found")

    return {"table_id": table_id, "new_pin": new_pin}


@router.delete("/{table_id}")
def delete_table(table_id: str, _: Dict = Depends(_require_admin)):
    with SQL_ENGINE.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT status
                FROM restaurant_tables
                WHERE table_id = :table_id
                """
            ),
            {"table_id": table_id},
        ).mappings().fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Table not found")

        if row["status"] != "available":
            raise HTTPException(status_code=400, detail="Cannot delete an occupied table")

        conn.execute(
            text(
                """
                DELETE FROM restaurant_tables
                WHERE table_id = :table_id
                """
            ),
            {"table_id": table_id},
        )

    return {"deleted": True}


@router.get("/waiter-calls")
def get_waiter_calls(_: Dict = Depends(_require_admin)):
    with SQL_ENGINE.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT wc.call_id, wc.called_at, wc.resolved,
                       rt.table_number, rt.table_id
                FROM waiter_calls wc
                JOIN restaurant_tables rt ON rt.table_id = wc.table_id
                WHERE wc.resolved = false
                ORDER BY wc.called_at ASC
                """
            )
        ).mappings().fetchall()

    calls = []
    for row in rows:
        calls.append(
            {
                "call_id": str(row["call_id"]),
                "called_at": row["called_at"].isoformat() if row["called_at"] else None,
                "resolved": bool(row["resolved"]),
                "table_number": row["table_number"],
                "table_id": str(row["table_id"]),
            }
        )

    return calls
