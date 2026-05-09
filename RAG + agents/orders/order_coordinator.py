import os
import uuid
import json
import time
from dotenv import load_dotenv

from infrastructure.config import AGENT_TASKS_CHANNEL, RESPONSE_CHANNEL_PREFIX
from infrastructure.database_connection import DatabaseConnection
from infrastructure.redis_client import get_sync_redis

"""
Legacy Redis-based coordination flow.

Production mobile app checkout should use:
    /cart/place_order  -> orders_service.place_order_sync()

Keep this file only for agent-based experiments, demos, or future async orchestration.
Do not use it as the main mobile app checkout path.
"""
# `order_coordinator` acts as a lightweight pipeline layer that "glues" together
# the cart, order and kitchen agents.  It can be triggered either from Streamlit
# (via the orchestrator) or directly by publishing a task to Redis with
# agent="coordinator".

load_dotenv()


def get_redis_client():
    return get_sync_redis()


def send_task_and_get_response(agent: str, command: str, payload: dict, timeout: float = 8.0) -> dict:
    """Publish a task and wait for a single JSON response (same as orchestrator)."""

    r = get_redis_client()
    response_channel = f"{RESPONSE_CHANNEL_PREFIX}{uuid.uuid4()}"
    task_data = {
        "agent": agent,
        "command": command,
        "payload": payload,
        "response_channel": response_channel
    }

    pubsub = r.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(response_channel)

    r.publish(AGENT_TASKS_CHANNEL, json.dumps(task_data))

    deadline = time.time() + timeout
    while time.time() < deadline:
        message = pubsub.get_message(timeout=1.0)
        if not message:
            continue
        data = message.get("data")
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="ignore")
        try:
            result = json.loads(data)
            pubsub.unsubscribe(response_channel)
            return result
        except json.JSONDecodeError:
            continue

    pubsub.unsubscribe(response_channel)
    return {"success": False, "message": f"Timeout waiting for {agent} response."}


def expand_deal_items(db: DatabaseConnection, deal_id: int, deal_qty: int):
    """Helper copied from orchestrator to expand a deal into menu items."""
    items = []
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT menu_item_id, quantity FROM deal_item WHERE deal_id = %s",
                    (deal_id,)
                )
                rows = cur.fetchall() or []

        for row in rows:
            if isinstance(row, dict):
                menu_item_id = int(row["menu_item_id"])
                base_qty = int(row.get("quantity", 1) or 1)
            else:
                menu_item_id = int(row[0])
                base_qty = int(row[1] or 1)
            items.append({"menu_item_id": menu_item_id, "qty": base_qty * deal_qty})
    except Exception as e:
        print(f"OrderCoordinator.expand_deal_items: {e}")
    return items


def process_cart_order(cart_id: str) -> dict:
    """Complete pipeline to finalize a cart, save it as an order and dispatch to kitchen."""

    # finalise cart
    finalize_result = send_task_and_get_response("cart", "place_order", {"cart_id": cart_id})
    if not finalize_result.get("success"):
        return {"success": False, "message": finalize_result.get("message", "failed to finalize")}

    cart_summary = finalize_result.get("order_data", {})
    raw_items = cart_summary.get("items", [])

    # save order in db
    order_result = send_task_and_get_response(
        "order", "save_and_summarize_order",
        {"cart_id": cart_id, "cart_summary": cart_summary}
    )
    order_id = order_result.get("order_id")
    base_message = order_result.get("message", "Order processed.")

    # correct ids and build kitchen payload
    kitchen_items = []
    db = DatabaseConnection.get_instance()

    for it in raw_items:
        original_id = it.get("item_id")
        name = it.get("item_name")
        qty = int(it.get("quantity", 1))
        item_type = it.get("item_type", "menu_item")
        if not name:
            continue

        real_id = original_id
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    if item_type == "deal":
                        cur.execute("SELECT deal_id FROM deal WHERE deal_name ILIKE %s", (name,))
                        row = cur.fetchone()
                        if row:
                            real_id = row[0] if isinstance(row, tuple) else row["deal_id"]
                    else:
                        cur.execute("SELECT item_id FROM menu_item WHERE item_name ILIKE %s", (name,))
                        row = cur.fetchone()
                        if row:
                            real_id = row[0] if isinstance(row, tuple) else row["item_id"]
        except Exception as e:
            print(f"OrderCoordinator ID correction failed: {e}")

        if item_type == "deal":
            deal_id = int(real_id)
            expanded = expand_deal_items(db, deal_id, qty)
            for e in expanded:
                e["expanded_from_deal"] = name
                e["item_type"] = "menu_item"
            kitchen_items.extend(expanded)

        elif item_type == "custom_deal":
            kitchen_items.append({
                "menu_item_id": int(real_id),
                "qty": qty,
                "item_type": "custom_deal",
            })

        else:
            kitchen_items.append({
                "menu_item_id": int(real_id),
                "qty": qty,
                "item_type": "menu_item",
            })

    kitchen_message = ""
    if order_id and kitchen_items:
        kitchen_payload = {"order_id": order_id, "items": kitchen_items}
        kitchen_plan = send_task_and_get_response("kitchen", "plan_order", kitchen_payload)
        if kitchen_plan.get("success"):
            est = kitchen_plan.get("estimated_total_minutes", "?")
            kitchen_message = f"\n\n👨‍🍳 Kitchen Update: estimated {est} minutes."
        else:
            kitchen_message = "\n\nKitchen unavailable."

    return {"success": True, "message": base_message + kitchen_message, "order_result": order_result}


# Redis listener for coordinator tasks ------------------------------------------------

def run_order_coordinator():
    r = get_redis_client()
    pubsub = r.pubsub()
    pubsub.subscribe(AGENT_TASKS_CHANNEL)
    print("OrderCoordinator listening for tasks...")

    for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        try:
            data = json.loads(message.get("data", "{}"))
        except Exception:
            continue
        if data.get("agent") != "coordinator":
            continue
        command = data.get("command")
        payload = data.get("payload", {})
        response_channel = data.get("response_channel")
        result = {"success": False, "message": "Unknown command"}
        if command == "process_cart_order":
            result = process_cart_order(payload.get("cart_id"))
        if response_channel:
            r.publish(response_channel, json.dumps(result))


if __name__ == "__main__":
    run_order_coordinator()