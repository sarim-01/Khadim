import asyncio
from datetime import datetime
from typing import Generator, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from agents.recommender_agent import RecommendationEngine
from infrastructure.db import SQL_ENGINE
from orders.orders_service import _create_kitchen_tasks

Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=SQL_ENGINE)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class WaiterCall(Base):
    __tablename__ = "waiter_calls"

    call_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    table_id = Column(PGUUID(as_uuid=True), ForeignKey("restaurant_tables.table_id"))
    called_at = Column(DateTime, default=datetime.utcnow)
    resolved = Column(Boolean, default=False)

router = APIRouter(prefix="/dine-in", tags=["dine-in"])
recommendation_engine = RecommendationEngine()


class TableLoginRequest(BaseModel):
    table_number: str
    pin: str


class DineInOrderItem(BaseModel):
    item_type: Literal["menu_item", "deal"]
    item_id: int
    quantity: int = Field(default=1, ge=1, le=99)


class DineInOrderRequest(BaseModel):
    session_id: UUID
    items: list[DineInOrderItem]


class DineInRecommendationSeedItem(BaseModel):
    item_type: Literal["menu_item", "deal", "custom_deal"] = "menu_item"
    item_id: int
    quantity: int = Field(default=1, ge=1, le=99)


class DineInRecommendationsRequest(BaseModel):
    session_id: UUID
    items: list[DineInRecommendationSeedItem]


class DineInSessionSettlementRequest(BaseModel):
    payment_method: Literal["card", "cash"]


def _count_incomplete_orders_for_session(executor, session_id: UUID) -> int:
    row = executor.execute(
        text(
            """
            SELECT COUNT(*) AS incomplete_orders
            FROM (
                SELECT
                    o.order_id,
                    CASE
                        WHEN COUNT(kt.task_id) = 0 THEN
                            LOWER(COALESCE(o.status, '')) IN ('completed', 'served')
                        ELSE
                            BOOL_AND(kt.status = 'COMPLETED')
                    END AS is_completed
                FROM public.orders o
                LEFT JOIN public.kitchen_tasks kt
                    ON kt.order_id = o.order_id
                WHERE o.session_id = :session_id
                  AND COALESCE(o.order_type, 'delivery') = 'dine_in'
                GROUP BY o.order_id, o.status
            ) completion
            WHERE completion.is_completed = FALSE
            """
        ),
        {"session_id": session_id},
    ).mappings().fetchone()

    if not row:
        return 0

    return int(row["incomplete_orders"] or 0)


@router.get("/top-sellers")
def get_top_sellers():
    with SQL_ENGINE.begin() as conn:
        top_menu_rows = (
            conn.execute(
                text(
                    """
                    SELECT
                        m.item_id,
                        m.item_name,
                        m.item_price,
                        m.item_category,
                        m.image_url,
                        COALESCE(SUM(oi.quantity), 0) AS sold_count
                    FROM public.menu_item m
                    LEFT JOIN public.order_items oi
                        ON oi.item_type = 'menu_item'
                       AND oi.item_id = m.item_id
                    LEFT JOIN public.orders o
                        ON o.order_id = oi.order_id
                       AND o.order_type = 'dine_in'
                    GROUP BY m.item_id, m.item_name, m.item_price, m.item_category, m.image_url
                    ORDER BY sold_count DESC, m.item_id ASC
                    LIMIT 5
                    """
                )
            )
            .mappings()
            .fetchall()
        )

        top_deal_rows = (
            conn.execute(
                text(
                    """
                    SELECT
                        d.deal_id,
                        d.deal_name,
                        d.deal_price,
                        d.image_url,
                        COALESCE(di.items, '') AS deal_items,
                        COALESCE(SUM(oi.quantity), 0) AS sold_count
                    FROM public.deal d
                    LEFT JOIN public.order_items oi
                        ON oi.item_type = 'deal'
                       AND oi.item_id = d.deal_id
                    LEFT JOIN public.orders o
                        ON o.order_id = oi.order_id
                       AND o.order_type = 'dine_in'
                    LEFT JOIN (
                        SELECT
                            di.deal_id,
                            STRING_AGG(
                                CONCAT(mi.item_name, ' x', di.quantity),
                                ', '
                                ORDER BY mi.item_name
                            ) AS items
                        FROM public.deal_item di
                        JOIN public.menu_item mi ON mi.item_id = di.menu_item_id
                        GROUP BY di.deal_id
                    ) di ON di.deal_id = d.deal_id
                    GROUP BY d.deal_id, d.deal_name, d.deal_price, d.image_url, di.items
                    ORDER BY sold_count DESC, d.deal_id ASC
                    LIMIT 3
                    """
                )
            )
            .mappings()
            .fetchall()
        )

    top_menu_items = [
        {
            "item_type": "menu_item",
            "item_id": int(row["item_id"]),
            "item_name": row["item_name"],
            "item_price": float(row["item_price"] or 0),
            "item_category": row["item_category"] or "",
            "image_url": row["image_url"] or "",
            "sold_count": int(row["sold_count"] or 0),
        }
        for row in top_menu_rows
    ]

    top_deals = [
        {
            "item_type": "deal",
            "item_id": int(row["deal_id"]),
            "item_name": row["deal_name"],
            "item_price": float(row["deal_price"] or 0),
            "item_category": "",
            "image_url": row["image_url"] or "",
            "deal_items": row["deal_items"] or "",
            "sold_count": int(row["sold_count"] or 0),
        }
        for row in top_deal_rows
    ]

    return {
        "top_menu_items": top_menu_items,
        "top_deals": top_deals,
        "top_sellers": [*top_menu_items, *top_deals],
    }


@router.post("/recommendations")
def get_dine_in_recommendations(payload: DineInRecommendationsRequest):
    if not payload.items:
        return {"recommendations": []}

    with SQL_ENGINE.begin() as conn:
        session_row = conn.execute(
            text(
                """
                SELECT session_id
                FROM public.dine_in_sessions
                WHERE session_id = :session_id
                  AND status = 'active'
                LIMIT 1
                """
            ),
            {"session_id": payload.session_id},
        ).mappings().fetchone()

        if not session_row:
            raise HTTPException(status_code=404, detail="Active dine-in session not found")

        cart_menu_items = []
        for seed in payload.items:
            if seed.item_type != "menu_item":
                continue

            row = conn.execute(
                text(
                    """
                    SELECT item_id, item_name, item_category
                    FROM public.menu_item
                    WHERE item_id = :item_id
                    LIMIT 1
                    """
                ),
                {"item_id": seed.item_id},
            ).mappings().fetchone()

            if not row:
                continue

            cart_menu_items.append(
                {
                    "item_id": int(row["item_id"]),
                    "item_name": row["item_name"],
                    "item_category": row["item_category"] or "",
                }
            )

        if not cart_menu_items:
            return {"recommendations": []}

        all_names = [row["item_name"] for row in cart_menu_items if row["item_name"]]
        exclude_categories = {"drink", "side", "starter", "bread"}

        main_items = [
            row
            for row in cart_menu_items
            if (row["item_category"] or "").lower() not in exclude_categories
        ]

        seen_recommendations: set[str] = set()
        current_item_ids = {int(row["item_id"]) for row in cart_menu_items}
        results = []

        for item in main_items:
            rec = recommendation_engine.get_recommendation(item["item_name"], all_names)
            if not rec.get("success"):
                continue

            rec_name = str(rec.get("recommended_item") or "").strip()
            if not rec_name:
                continue

            rec_key = rec_name.lower()
            if rec_key in seen_recommendations:
                continue

            rec_row = conn.execute(
                text(
                    """
                    SELECT item_id, item_price, image_url
                    FROM public.menu_item
                    WHERE LOWER(item_name) = LOWER(:name)
                    LIMIT 1
                    """
                ),
                {"name": rec_name},
            ).mappings().fetchone()

            if not rec_row:
                continue

            rec_item_id = int(rec_row["item_id"])
            if rec_item_id in current_item_ids:
                continue

            seen_recommendations.add(rec_key)

            results.append(
                {
                    "for_item": item["item_name"],
                    "recommended_name": rec_name,
                    "recommended_item_id": rec_item_id,
                    "recommended_price": float(rec_row["item_price"] or 0),
                    "image_url": rec_row["image_url"] or "",
                    "reason": rec.get("reason") or "",
                }
            )

    return {"recommendations": results}


@router.post("/table-login")
def table_login(payload: TableLoginRequest):
    raw_table_number = payload.table_number.strip()
    table_number = raw_table_number.upper()
    # Accept both "T1" and "1" style input from kiosk keypad/screens.
    if table_number and not table_number.startswith("T") and table_number.isdigit():
        table_number = f"T{table_number}"
    pin = payload.pin.strip()

    with SQL_ENGINE.begin() as conn:
        table_row = conn.execute(
            text(
                """
                SELECT table_id, table_number, status
                FROM public.restaurant_tables
                                WHERE UPPER(table_number) = :table_number
                  AND table_pin = :pin
                LIMIT 1
                """
            ),
            {"table_number": table_number, "pin": pin},
        ).mappings().fetchone()

        if not table_row:
            raise HTTPException(status_code=401, detail="Invalid table number or PIN")

        active_session_row = conn.execute(
            text(
                """
                SELECT session_id, table_id, started_at
                FROM public.dine_in_sessions
                WHERE table_id = :table_id
                  AND status = 'active'
                ORDER BY started_at DESC
                LIMIT 1
                """
            ),
            {"table_id": table_row["table_id"]},
        ).mappings().fetchone()

        if active_session_row:
            return {
                "session_id": str(active_session_row["session_id"]),
                "table_id": str(active_session_row["table_id"]),
                "table_number": table_row["table_number"],
                "started_at": active_session_row["started_at"].isoformat()
                if active_session_row["started_at"]
                else None,
            }

        if (table_row["status"] or "").lower() != "available":
            raise HTTPException(status_code=409, detail="Table is not available")

        session_row = conn.execute(
            text(
                """
                INSERT INTO public.dine_in_sessions (table_id, status)
                VALUES (:table_id, 'active')
                RETURNING session_id, table_id, started_at
                """
            ),
            {"table_id": table_row["table_id"]},
        ).mappings().fetchone()

        conn.execute(
            text(
                """
                UPDATE public.restaurant_tables
                SET status = 'occupied'
                WHERE table_id = :table_id
                """
            ),
            {"table_id": table_row["table_id"]},
        )

    return {
        "session_id": str(session_row["session_id"]),
        "table_id": str(session_row["table_id"]),
        "table_number": table_row["table_number"],
        "started_at": session_row["started_at"].isoformat() if session_row["started_at"] else None,
    }


@router.post("/order")
def create_dine_in_order(payload: DineInOrderRequest):
    if not payload.items:
        raise HTTPException(status_code=400, detail="At least one item is required")

    with SQL_ENGINE.begin() as conn:
        session_row = conn.execute(
            text(
                """
                                SELECT session_id, table_id, COALESCE(round_count, 0) AS round_count
                FROM public.dine_in_sessions
                WHERE session_id = :session_id
                  AND status = 'active'
                LIMIT 1
                """
            ),
            {"session_id": payload.session_id},
        ).mappings().fetchone()

        if not session_row:
            raise HTTPException(status_code=404, detail="Active dine-in session not found")

        next_round_number = int(session_row["round_count"] or 0) + 1

        normalized_items = []
        subtotal = 0.0

        for item in payload.items:
            if item.item_type == "menu_item":
                item_row = conn.execute(
                    text(
                        """
                        SELECT item_id, item_name, item_price
                        FROM public.menu_item
                        WHERE item_id = :item_id
                        LIMIT 1
                        """
                    ),
                    {"item_id": item.item_id},
                ).mappings().fetchone()

                if not item_row:
                    raise HTTPException(status_code=404, detail=f"Menu item {item.item_id} not found")

                snapshot_name = item_row["item_name"]
                snapshot_price = float(item_row["item_price"] or 0)
                resolved_item_id = int(item_row["item_id"])
            else:
                item_row = conn.execute(
                    text(
                        """
                        SELECT deal_id, deal_name, deal_price
                        FROM public.deal
                        WHERE deal_id = :item_id
                        LIMIT 1
                        """
                    ),
                    {"item_id": item.item_id},
                ).mappings().fetchone()

                if not item_row:
                    raise HTTPException(status_code=404, detail=f"Deal {item.item_id} not found")

                snapshot_name = item_row["deal_name"]
                snapshot_price = float(item_row["deal_price"] or 0)
                resolved_item_id = int(item_row["deal_id"])

            qty = int(item.quantity)
            line_total = round(snapshot_price * qty, 2)
            subtotal = round(subtotal + line_total, 2)

            normalized_items.append(
                {
                    "item_type": item.item_type,
                    "item_id": resolved_item_id,
                    "item_name": snapshot_name,
                    "quantity": qty,
                    "unit_price": snapshot_price,
                    "line_total": line_total,
                }
            )

        tax = round(subtotal * 0.05, 2)
        delivery_fee = 0.0
        total = round(subtotal + tax, 2)

        cart_row = conn.execute(
            text(
                """
                INSERT INTO public.cart (cart_id, status, user_id)
                VALUES (gen_random_uuid(), 'inactive', NULL)
                RETURNING cart_id
                """
            )
        ).mappings().fetchone()

        order_row = conn.execute(
            text(
                """
                INSERT INTO public.orders (
                    cart_id,
                    total_price,
                    subtotal,
                    tax,
                    delivery_fee,
                    order_type,
                    table_id,
                    session_id,
                    status,
                    estimated_prep_time_minutes,
                    round_number,
                    payment_status
                )
                VALUES (
                    :cart_id,
                    :total_price,
                    :subtotal,
                    :tax,
                    :delivery_fee,
                    'dine_in',
                    :table_id,
                    :session_id,
                    'confirmed',
                    15,
                    :round_number,
                    'to_be_paid'
                )
                RETURNING order_id
                """
            ),
            {
                "cart_id": cart_row["cart_id"],
                "total_price": total,
                "subtotal": subtotal,
                "tax": tax,
                "delivery_fee": delivery_fee,
                "table_id": session_row["table_id"],
                "session_id": payload.session_id,
                "round_number": next_round_number,
            },
        ).mappings().fetchone()

        order_id = int(order_row["order_id"])

        from websocket_manager import manager

        broadcast_message = {
            "event": "new_order",
            "order_id": order_id,
            "total": total,
        }

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Worker-thread context: run broadcast to completion in a fresh loop.
            asyncio.run(
                manager.broadcast(
                    room=f"session_{payload.session_id}",
                    message=broadcast_message,
                )
            )
        else:
            loop.create_task(
                manager.broadcast(
                    room=f"session_{payload.session_id}",
                    message=broadcast_message,
                )
            )

        for item in normalized_items:
            conn.execute(
                text(
                    """
                    INSERT INTO public.order_items (
                        order_id,
                        item_type,
                        item_id,
                        name_snapshot,
                        unit_price_snapshot,
                        quantity,
                        line_total
                    )
                    VALUES (
                        :order_id,
                        :item_type,
                        :item_id,
                        :name_snapshot,
                        :unit_price_snapshot,
                        :quantity,
                        :line_total
                    )
                    """
                ),
                {
                    "order_id": order_id,
                    "item_type": item["item_type"],
                    "item_id": int(item["item_id"]),
                    "name_snapshot": item["item_name"],
                    "unit_price_snapshot": item["unit_price"],
                    "quantity": int(item["quantity"]),
                    "line_total": item["line_total"],
                },
            )

        # Mirror delivery flow: generate kitchen_tasks for every dine-in order item
        # so kitchen dashboard and prep workflow can track this order.
        kitchen_cart_items = [
            {
                "item_type": item["item_type"],
                "item_id": int(item["item_id"]),
                "quantity": int(item["quantity"]),
            }
            for item in normalized_items
        ]
        estimated_prep_minutes = _create_kitchen_tasks(
            conn,
            order_id,
            kitchen_cart_items,
        )

        conn.execute(
            text(
                """
                UPDATE public.orders
                SET estimated_prep_time_minutes = :estimated_prep_time_minutes
                WHERE order_id = :order_id
                """
            ),
            {
                "estimated_prep_time_minutes": int(estimated_prep_minutes or 0),
                "order_id": order_id,
            },
        )

        conn.execute(
            text(
                """
                UPDATE public.dine_in_sessions
                SET round_count = COALESCE(round_count, 0) + 1,
                    total_amount = COALESCE(total_amount, 0) + :total
                WHERE session_id = :session_id
                """
            ),
            {"session_id": payload.session_id, "total": total},
        )

    return {
        "order_id": order_id,
        "session_id": str(payload.session_id),
        "round_number": next_round_number,
        "total_price": total,
        "items": normalized_items,
    }


@router.get("/sessions/{session_id}/orders")
def get_session_orders(session_id: UUID):
    with SQL_ENGINE.connect() as conn:
        session_row = conn.execute(
            text(
                """
                SELECT s.session_id, s.status, t.table_number
                FROM public.dine_in_sessions s
                JOIN public.restaurant_tables t ON t.table_id = s.table_id
                WHERE s.session_id = :session_id
                LIMIT 1
                """
            ),
            {"session_id": session_id},
        ).mappings().fetchone()

        if not session_row:
            raise HTTPException(status_code=404, detail="Dine-in session not found")

        order_rows = conn.execute(
            text(
                """
                SELECT
                    o.order_id,
                    o.round_number,
                    o.created_at,
                    o.total_price,
                    o.status,
                    o.payment_status,
                    o.estimated_prep_time_minutes,
                    CASE
                        WHEN kt.task_count IS NULL OR kt.task_count = 0
                            THEN COALESCE(o.status, 'confirmed')
                        WHEN kt.completed_count = kt.task_count
                            THEN 'completed'
                        WHEN kt.ready_or_completed_count = kt.task_count
                            THEN 'ready'
                        WHEN kt.in_progress_count > 0
                            THEN 'preparing'
                        ELSE 'in_kitchen'
                    END AS kitchen_status
                FROM public.orders o
                LEFT JOIN (
                    SELECT
                        order_id,
                        COUNT(*) AS task_count,
                        SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_count,
                        SUM(CASE WHEN status IN ('READY', 'COMPLETED') THEN 1 ELSE 0 END) AS ready_or_completed_count,
                        SUM(CASE WHEN status = 'IN_PROGRESS' THEN 1 ELSE 0 END) AS in_progress_count
                    FROM public.kitchen_tasks
                    GROUP BY order_id
                ) kt ON kt.order_id = o.order_id
                WHERE o.session_id = :session_id
                  AND COALESCE(o.order_type, 'delivery') = 'dine_in'
                ORDER BY o.created_at ASC, o.order_id ASC
                """
            ),
            {"session_id": session_id},
        ).mappings().fetchall()

        item_rows = conn.execute(
            text(
                """
                SELECT
                    oi.order_id,
                    oi.item_type,
                    oi.item_id,
                    oi.name_snapshot,
                    oi.quantity,
                    oi.unit_price_snapshot,
                    oi.line_total
                FROM public.order_items oi
                JOIN public.orders o ON o.order_id = oi.order_id
                WHERE o.session_id = :session_id
                  AND COALESCE(o.order_type, 'delivery') = 'dine_in'
                ORDER BY oi.order_id ASC, oi.id ASC
                """
            ),
            {"session_id": session_id},
        ).mappings().fetchall()

    items_by_order: dict[int, list[dict]] = {}
    for row in item_rows:
        order_id = int(row["order_id"])
        items_by_order.setdefault(order_id, []).append(
            {
                "item_type": row["item_type"],
                "item_id": int(row["item_id"]),
                "item_name": row["name_snapshot"],
                "quantity": int(row["quantity"] or 0),
                "price": float(row["unit_price_snapshot"] or 0),
                "line_total": float(row["line_total"] or 0),
            }
        )

    orders = []
    session_total = 0.0

    for index, row in enumerate(order_rows, start=1):
        order_total = float(row["total_price"] or 0)
        session_total = round(session_total + order_total, 2)

        payment_status = (row["payment_status"] or "").strip().lower()
        status = (row["status"] or "").strip().lower()
        # Settlement is independent from kitchen completion.
        # A round is paid only when payment is explicitly settled.
        is_paid = payment_status in {"paid", "settled"} or status in {
            "paid",
            "settled",
        }

        orders.append(
            {
                "order_id": int(row["order_id"]),
                "round_id": int(row["order_id"]),
                "round_number": int(row["round_number"] or index),
                "created_at": row["created_at"].isoformat()
                if row["created_at"]
                else None,
                "status": row["status"],
                "kitchen_status": row["kitchen_status"],
                "payment_status": row["payment_status"],
                "is_paid": is_paid,
                "estimated_prep_time_minutes": int(
                    row["estimated_prep_time_minutes"] or 0
                ),
                "round_total": order_total,
                "items": items_by_order.get(int(row["order_id"]), []),
            }
        )

    return {
        "session_id": str(session_row["session_id"]),
        "table_number": session_row["table_number"],
        "session_status": session_row["status"],
        "session_total": session_total,
        "orders": orders,
    }


@router.post("/sessions/{session_id}/call-waiter")
def call_waiter(session_id: UUID, for_cash_payment: bool = False):
    with SQL_ENGINE.begin() as conn:
        session = conn.execute(
            text(
                """
                SELECT table_id
                FROM public.dine_in_sessions
                WHERE session_id = :session_id
                  AND status = 'active'
                LIMIT 1
                """
            ),
            {"session_id": session_id},
        ).mappings().fetchone()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if for_cash_payment:
            incomplete_orders = _count_incomplete_orders_for_session(conn, session_id)
            if incomplete_orders > 0:
                raise HTTPException(
                    status_code=400,
                    detail="Payment can be requested only after all rounds are completed.",
                )

            conn.execute(
                text(
                    """
                    UPDATE public.restaurant_tables
                    SET status = 'bill_requested_cash'
                    WHERE table_id = :table_id
                    """
                ),
                {"table_id": session["table_id"]},
            )

        waiter_call_row = conn.execute(
            text(
                """
                INSERT INTO public.waiter_calls (table_id)
                VALUES (:table_id)
                RETURNING call_id, called_at
                """
            ),
            {"table_id": session["table_id"]},
        ).mappings().fetchone()

    if waiter_call_row is None:
        raise HTTPException(status_code=500, detail="Failed to create waiter call")

    payload = {
        "call_id": str(waiter_call_row["call_id"]),
        "called_at": waiter_call_row["called_at"].isoformat()
        if waiter_call_row["called_at"]
        else None,
    }

    if for_cash_payment:
        return {
            "message": "Cash bill requested. Waiter notified",
            **payload,
        }

    return {"message": "Waiter notified", **payload}


@router.get("/sessions/{session_id}/waiter-calls/{call_id}/status")
def get_waiter_call_status(session_id: UUID, call_id: UUID):
    with SQL_ENGINE.begin() as conn:
        call_row = conn.execute(
            text(
                """
                SELECT
                    wc.call_id,
                    wc.called_at,
                    wc.resolved,
                    wc.table_id
                FROM public.waiter_calls wc
                WHERE wc.call_id = :call_id
                LIMIT 1
                """
            ),
            {"call_id": call_id},
        ).mappings().fetchone()

        if not call_row:
            raise HTTPException(status_code=404, detail="Waiter call not found")

        session_row = conn.execute(
            text(
                """
                SELECT table_id
                FROM public.dine_in_sessions
                WHERE session_id = :session_id
                LIMIT 1
                """
            ),
            {"session_id": session_id},
        ).mappings().fetchone()

        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")

        if str(session_row["table_id"]) != str(call_row["table_id"]):
            raise HTTPException(status_code=403, detail="Waiter call does not belong to this session")

    return {
        "call_id": str(call_row["call_id"]),
        "resolved": bool(call_row["resolved"]),
        "status": "acknowledged" if call_row["resolved"] else "notified",
        "called_at": call_row["called_at"].isoformat() if call_row["called_at"] else None,
    }


@router.post("/sessions/{session_id}/end")
def end_dine_in_session(session_id: UUID):
    with SQL_ENGINE.begin() as conn:
        session_row = conn.execute(
            text(
                """
                SELECT session_id, table_id, status
                FROM public.dine_in_sessions
                WHERE session_id = :session_id
                LIMIT 1
                """
            ),
            {"session_id": session_id},
        ).mappings().fetchone()

        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")

        pending_payment_row = conn.execute(
            text(
                """
                SELECT COUNT(*) AS pending_count
                FROM public.orders
                WHERE session_id = :session_id
                  AND COALESCE(order_type, 'delivery') = 'dine_in'
                  AND LOWER(COALESCE(payment_status, '')) NOT IN ('paid', 'settled')
                  AND LOWER(COALESCE(status, '')) NOT IN ('paid', 'settled')
                """
            ),
            {"session_id": session_id},
        ).mappings().fetchone()

        if int(pending_payment_row["pending_count"] or 0) > 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot end session with pending payment.",
            )

        conn.execute(
            text(
                """
                UPDATE public.dine_in_sessions
                SET status = 'closed',
                    ended_at = COALESCE(ended_at, NOW())
                WHERE session_id = :session_id
                """
            ),
            {"session_id": session_id},
        )

        conn.execute(
            text(
                """
                UPDATE public.restaurant_tables
                SET status = 'available'
                WHERE table_id = :table_id
                """
            ),
            {"table_id": session_row["table_id"]},
        )

        conn.execute(
            text(
                """
                UPDATE public.waiter_calls
                SET resolved = true
                WHERE table_id = :table_id
                  AND resolved = false
                """
            ),
            {"table_id": session_row["table_id"]},
        )

    return {
        "session_id": str(session_id),
        "message": "Session ended successfully.",
    }


@router.post("/sessions/{session_id}/settle-payment")
def settle_session_payment(session_id: UUID, payload: DineInSessionSettlementRequest):
    with SQL_ENGINE.begin() as conn:
        session_row = conn.execute(
            text(
                """
                SELECT session_id, table_id, status
                FROM public.dine_in_sessions
                WHERE session_id = :session_id
                LIMIT 1
                """
            ),
            {"session_id": session_id},
        ).mappings().fetchone()

        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")

        order_count_row = conn.execute(
            text(
                """
                SELECT COUNT(*) AS total_orders
                FROM public.orders
                WHERE session_id = :session_id
                  AND COALESCE(order_type, 'delivery') = 'dine_in'
                """
            ),
            {"session_id": session_id},
        ).mappings().fetchone()

        total_orders = int(order_count_row["total_orders"] or 0)
        if total_orders <= 0:
            raise HTTPException(status_code=400, detail="No dine-in orders found for this session")

        incomplete_orders = _count_incomplete_orders_for_session(conn, session_id)
        if incomplete_orders > 0:
            raise HTTPException(
                status_code=400,
                detail="Payment can be completed only after all rounds are marked completed in kitchen.",
            )

        if payload.payment_method == "cash":
            conn.execute(
                text(
                    """
                    UPDATE public.restaurant_tables
                    SET status = 'bill_requested_cash'
                    WHERE table_id = :table_id
                    """
                ),
                {"table_id": session_row["table_id"]},
            )

            conn.execute(
                text(
                    """
                    INSERT INTO public.waiter_calls (table_id)
                    VALUES (:table_id)
                    """
                ),
                {"table_id": session_row["table_id"]},
            )

            return {
                "session_id": str(session_id),
                "payment_method": "cash",
                "message": "Cash bill requested. Waiter notified",
            }

        conn.execute(
            text(
                """
                UPDATE public.orders
                SET payment_status = 'paid'
                WHERE session_id = :session_id
                  AND COALESCE(order_type, 'delivery') = 'dine_in'
                """
            ),
            {"session_id": session_id},
        )

        conn.execute(
            text(
                """
                UPDATE public.waiter_calls
                SET resolved = true
                WHERE table_id = :table_id
                  AND resolved = false
                """
            ),
            {"table_id": session_row["table_id"]},
        )

        conn.execute(
            text(
                """
                UPDATE public.dine_in_sessions
                SET status = 'closed',
                    ended_at = NOW(),
                    payment_method = 'card'
                WHERE session_id = :session_id
                """
            ),
            {"session_id": session_id},
        )

        conn.execute(
            text(
                """
                UPDATE public.restaurant_tables
                SET status = 'available'
                WHERE table_id = :table_id
                """
            ),
            {"table_id": session_row["table_id"]},
        )

    return {
        "session_id": str(session_id),
        "payment_method": "card",
        "message": "Card payment successful. Session settled and table is now available.",
    }


@router.get("/sessions/{session_id}/orders/{order_id}/tracking")
def get_dine_in_order_tracking(session_id: UUID, order_id: int):
    with SQL_ENGINE.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    o.order_id,
                    o.session_id,
                    o.round_number,
                    CASE
                        WHEN kt.task_count IS NULL OR kt.task_count = 0
                            THEN COALESCE(o.status, 'confirmed')
                        ELSE kt.tracking_status
                    END AS status,
                    o.payment_status,
                    COALESCE(
                        kt.max_estimated_minutes,
                        o.estimated_prep_time_minutes,
                        0
                    ) AS estimated_prep_time_minutes,
                    o.created_at
                FROM public.orders o
                LEFT JOIN (
                    SELECT
                        order_id,
                        COUNT(*) AS task_count,
                        MAX(estimated_minutes) AS max_estimated_minutes,
                        CASE
                            WHEN BOOL_AND(status = 'COMPLETED') THEN 'completed'
                            WHEN BOOL_AND(status IN ('READY', 'COMPLETED')) THEN 'ready'
                            WHEN BOOL_OR(status = 'IN_PROGRESS') THEN 'preparing'
                            ELSE 'in_kitchen'
                        END AS tracking_status
                    FROM public.kitchen_tasks
                    GROUP BY order_id
                ) kt ON kt.order_id = o.order_id
                WHERE o.order_id = :order_id
                  AND o.session_id = :session_id
                  AND COALESCE(o.order_type, 'delivery') = 'dine_in'
                LIMIT 1
                """
            ),
            {"order_id": order_id, "session_id": session_id},
        ).mappings().fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Dine-in order not found")

    return {
        "order_id": int(row["order_id"]),
        "session_id": str(row["session_id"]),
        "round_number": int(row["round_number"] or 0),
        "status": row["status"],
        "payment_status": row["payment_status"],
        "estimated_prep_time_minutes": int(row["estimated_prep_time_minutes"] or 0),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.websocket("/ws/session/{session_id}")
async def session_ws(websocket: WebSocket, session_id: str):
    from websocket_manager import manager

    await manager.connect(websocket, room=f"session_{session_id}")
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket, room=f"session_{session_id}")
