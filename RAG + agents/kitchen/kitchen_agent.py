import os
import json
import redis
import psycopg2
import psycopg2.extras
from datetime import datetime
from dotenv import load_dotenv

from infrastructure.config import AGENT_TASKS_CHANNEL
from infrastructure.database_connection import DatabaseConnection
from infrastructure.redis_lock import get_lock_manager

load_dotenv()

# Get lock manager for chef assignment
lock_manager = get_lock_manager()

# =========================================================
#   ALLOWED STATUS TRANSITIONS (STRICT WORKFLOW)
# =========================================================

ALLOWED_STATUS_FLOW = {
    "QUEUED": ["IN_PROGRESS"],
    "IN_PROGRESS": ["READY"],
    "READY": ["COMPLETED"],
    "COMPLETED": []  
}


# =========================================================
#   REDIS CONFIG
# =========================================================

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

redis_client = redis.StrictRedis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True
)

# =========================================================
#   DB HELPER
# =========================================================

def get_db_instance():
    """Get the singleton DB instance."""
    return DatabaseConnection.get_instance()

# =========================================================
#   DB INSERT
# =========================================================

def save_kitchen_task(task: dict):
    sql = """
        INSERT INTO kitchen_tasks (
            task_id, order_id, menu_item_id, item_name, qty,
            station, assigned_chef, estimated_minutes, status
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (task_id) DO NOTHING;
    """
    
    db = get_db_instance()
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                task["task_id"],
                task["order_id"],
                task["menu_item_id"],
                task["item_name"],
                task["qty"],
                task["station"],
                task["assigned_chef"],
                task["estimated_minutes"],
                task["status"]
            ))
            conn.commit()


def update_task_status(task_id, new_status):
    sql = """
        UPDATE kitchen_tasks
        SET status = %s, updated_at = CURRENT_TIMESTAMP
        WHERE task_id = %s
        RETURNING task_id;
    """
    db = get_db_instance()
    with db.get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (new_status, task_id))
            updated = cur.fetchone()
            conn.commit()
            return updated is not None


KITCHEN_TO_ORDER_STATUS = {
    "QUEUED":      "in_kitchen",
    "IN_PROGRESS": "preparing",
    "READY":       "ready",
    "COMPLETED":   "completed",
}

# Lower rank = earlier stage (worst/slowest task wins)
_STATUS_RANK = {
    "QUEUED": 0,
    "IN_PROGRESS": 1,
    "READY": 2,
    "COMPLETED": 3,
}


def sync_order_status(order_id, kitchen_status, estimated_minutes=None):
    """Update orders table to reflect current kitchen status."""
    order_status = KITCHEN_TO_ORDER_STATUS.get(kitchen_status)
    if not order_status:
        return
    db = get_db_instance()
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            if estimated_minutes is not None:
                cur.execute(
                    "UPDATE orders SET status=%s, estimated_prep_time_minutes=%s WHERE order_id=%s",
                    (order_status, estimated_minutes, order_id)
                )
            else:
                cur.execute(
                    "UPDATE orders SET status=%s WHERE order_id=%s",
                    (order_status, order_id)
                )
            conn.commit()
    print(f"[Kitchen] Synced order {order_id} → status={order_status}")


def compute_and_sync_order_status(order_id):
    """
    Look at ALL remaining tasks for the order and advance the order status
    only when every task has reached that level.
      - Any task still QUEUED       → in_kitchen  (hold)
      - All IN_PROGRESS or better   → preparing   (remaining time = max of IN_PROGRESS tasks)
    - All READY                   → ready        (time = 0)
    - All COMPLETED               → completed    (time = 0)
      - No tasks left               → completed    (time = 0)
    """
    db = get_db_instance()
    with db.get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT status, estimated_minutes FROM kitchen_tasks WHERE order_id=%s",
                (order_id,)
            )
            tasks = cur.fetchall()

    if not tasks:
        sync_order_status(order_id, "COMPLETED", 0)
        return

    statuses = [t["status"] for t in tasks]

    # Determine the worst (lowest-rank) status among all tasks
    worst = min(statuses, key=lambda s: _STATUS_RANK.get(s, 0))

    if worst == "QUEUED":
        # At least one task hasn't started yet — hold at in_kitchen
        sync_order_status(order_id, "QUEUED")
    elif worst == "IN_PROGRESS":
        # All started; show remaining time of the slowest IN_PROGRESS task
        in_progress_times = [t["estimated_minutes"] for t in tasks if t["status"] == "IN_PROGRESS"]
        remaining = max(in_progress_times) if in_progress_times else 0
        sync_order_status(order_id, "IN_PROGRESS", remaining)
    elif worst == "READY":
        # All tasks are READY or COMPLETED
        sync_order_status(order_id, "READY", 0)
    else:
        # All tasks are COMPLETED
        sync_order_status(order_id, "COMPLETED", 0)

# =========================================================
#   DB FETCH HELPERS
# =========================================================

def fetch_menu_item(item_id):
    sql = "SELECT * FROM menu_item WHERE item_id = %s"
    db = get_db_instance()
    with db.get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (item_id,))
            return cur.fetchone()


def fetch_chefs_for_item(item_id):
    sql = """
        SELECT 
            c.cheff_id,
            c.cheff_name,
            c.specialty,
            c.active_status,
            c.max_current_orders
        FROM chef c
        JOIN menu_item_chefs mic ON mic.chef_id = c.cheff_id
        WHERE mic.menu_item_id = %s
          AND c.active_status = TRUE
    """
    db = get_db_instance()
    with db.get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (item_id,))
            return cur.fetchall() or []


def get_chef_current_load():
    """
    Get the current number of active tasks (QUEUED or IN_PROGRESS) for each chef.
    Returns a dictionary: {chef_name: current_task_count}
    """
    sql = """
        SELECT assigned_chef, COUNT(*) as task_count
        FROM kitchen_tasks
        WHERE status IN ('QUEUED', 'IN_PROGRESS')
        GROUP BY assigned_chef
    """
    db = get_db_instance()
    with db.get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            return {row["assigned_chef"]: row["task_count"] for row in rows}


def select_best_chef(chef_list, chef_load, pending_assignments):
    """
    Select the best chef based on load balancing with conflict detection.
    
    Uses distributed locking to prevent competing chef assignments when
    multiple orders are being processed simultaneously.
    
    Args:
        chef_list: List of available chefs for this item
        chef_load: Dictionary of current task counts from DB {chef_name: count}
        pending_assignments: Dictionary tracking assignments within this order {chef_name: count}
    
    Returns:
        The chef_name with the lowest combined load, or "UNASSIGNED" if all chefs are at max capacity
    """
    if not chef_list:
        return "UNASSIGNED"
    
    best_chef = None
    min_load = float('inf')
    locked_chef = None
    
    # Sort chefs by load to try least loaded first
    sorted_chefs = sorted(
        chef_list, 
        key=lambda c: chef_load.get(c["cheff_name"], 0) + pending_assignments.get(c["cheff_name"], 0)
    )
    
    for chef in sorted_chefs:
        chef_name = chef["cheff_name"]
        max_orders = chef.get("max_current_orders") or 10  # Default to 10 if not set
        
        # Calculate total load: DB load + pending assignments in this order
        current_db_load = chef_load.get(chef_name, 0)
        pending_load = pending_assignments.get(chef_name, 0)
        total_load = current_db_load + pending_load
        
        # Skip if chef is at or over max capacity
        if total_load >= max_orders:
            print(f"[DEBUG KITCHEN] Chef {chef_name} at max capacity ({total_load}/{max_orders})")
            continue
        
        # Try to acquire a brief lock on this chef to prevent race conditions
        if lock_manager.acquire_chef_lock(chef_name, timeout=2):
            locked_chef = chef_name
            best_chef = chef_name
            min_load = total_load
            print(f"[DEBUG KITCHEN] Selected chef: {best_chef} (load: {min_load}) [locked]")
            break
        else:
            # Chef is being assigned by another process, try next
            print(f"[DEBUG KITCHEN] Chef {chef_name} locked by another process, trying next...")
            continue
    
    # Release the chef lock after assignment is recorded
    if locked_chef:
        lock_manager.release_chef_lock(locked_chef)
    
    if best_chef:
        return best_chef
    else:
        # All chefs at capacity or locked, pick the one with lowest load anyway
        best_chef = min(chef_list, key=lambda c: chef_load.get(c["cheff_name"], 0) + pending_assignments.get(c["cheff_name"], 0))
        print(f"[DEBUG KITCHEN] All chefs at capacity/locked, assigning to {best_chef['cheff_name']}")
        return best_chef["cheff_name"]

# =========================================================
#   STATION LOGIC
# =========================================================

def infer_station(category, cuisine):
    if category == "drink":
        return "DRINKS"
    if category in ("bread",):
        return "TANDOOR"
    if cuisine == "BBQ":
        return "GRILL"
    if cuisine in ("Fast Food", "Chinese"):
        return "FRY"
    if cuisine == "Desi":
        return "STOVE"
    return "GENERAL"

# =========================================================
#   CUSTOM DEAL EXPANDER
# =========================================================

def expand_items(items):
    """Replace any custom_deal entry with its actual menu items."""
    expanded = []
    for entry in items:
        if entry.get("item_type") == "custom_deal":
            sql = """
                SELECT item_id, quantity
                FROM public.custom_deal_items
                WHERE custom_deal_id = %s
            """
            db = get_db_instance()
            with db.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (entry["menu_item_id"],))
                    rows = cur.fetchall()
            for row in rows:
                expanded.append({
                    "menu_item_id": row["item_id"],
                    "qty": row["quantity"],
                    "item_type": "menu_item"
                })
        else:
            expanded.append(entry)
    return expanded


# =========================================================
#   KITCHEN ORDER PLANNER
# =========================================================

def plan_order(payload):
    print(f"\n[DEBUG KITCHEN] ------------------------------------------------")
    print(f"[DEBUG KITCHEN] Incoming Payload: {payload}") 

    order_id = payload.get("order_id")
    items = payload.get("items", [])

    # Expand any custom_deal entries into their individual menu items
    items = expand_items(items)

    tasks = []
    cached_chefs = {}
    task_counter = 1
    
    # Get current chef workloads from DB
    chef_load = get_chef_current_load()
    print(f"[DEBUG KITCHEN] Current chef loads: {chef_load}")
    
    # Track pending assignments within this order (for multi-item orders)
    pending_assignments = {}

    for entry in items:
        item_id = entry.get("menu_item_id")
        
        # 1. Fetch menu item
        item = fetch_menu_item(item_id)
        
        if not item:
            print(f"[DEBUG KITCHEN] ❌ ERROR: Item {item_id} returns None from DB. Check your menu_item table!")
            continue 
            
        # 2. Assign Chef using load balancing
        item_name = item.get("item_name")
        category = item.get("item_category")
        cuisine = item.get("item_cuisine")
        prep_time = item.get("prep_time_minutes") or 15
        station = infer_station(category, cuisine)

        # Check Chefs
        if item_id not in cached_chefs:
            cached_chefs[item_id] = fetch_chefs_for_item(item_id)
        
        chef_list = cached_chefs[item_id]
        
        # Use load-balanced chef selection
        assigned_chef = select_best_chef(chef_list, chef_load, pending_assignments)
        
        # Track this assignment for subsequent items in the same order
        pending_assignments[assigned_chef] = pending_assignments.get(assigned_chef, 0) + 1

        task_id = f"{order_id}-{task_counter}"
        task_data = {
            "task_id": task_id,
            "order_id": order_id,
            "menu_item_id": item_id,
            "item_name": item_name,
            "qty": entry.get("qty", 1),
            "station": station,
            "assigned_chef": assigned_chef,
            "estimated_minutes": prep_time,
            "status": "QUEUED"
        }

        # 3. Insert to DB
        try:
            save_kitchen_task(task_data)
            print(f"[DEBUG KITCHEN] ✅ INSERTED Task {task_id} into DB.")
            tasks.append(task_data)
        except Exception as e:
            print(f"[DEBUG KITCHEN] ❌ DB INSERT FAILED: {e}")

        task_counter += 1

    total_time = max([t["estimated_minutes"] for t in tasks]) if tasks else 0
    return {
        "success": True,
        "order_id": order_id,
        "estimated_total_minutes": total_time,
        "tasks": tasks,
        "chefs_summary": []
    }

# =========================================================
#   REDIS LISTENER
# =========================================================

def main():
    print("[Kitchen Agent] Started. Listening for tasks…")
    pubsub = redis_client.pubsub()
    pubsub.subscribe(AGENT_TASKS_CHANNEL)

    for msg in pubsub.listen():
        if msg["type"] != "message":
            continue

        try:
            task = json.loads(msg["data"])
        except Exception as e:
            print("[Kitchen Agent] JSON decode failed:", e)
            continue

        if task.get("agent") != "kitchen":
            continue

        command = task.get("command")
        payload = task.get("payload", {})
        response = task.get("response_channel")

        # --------------------------------------------------------
        # PLAN ORDER
        # --------------------------------------------------------
        if command == "plan_order":
            try:
                result = plan_order(payload)
                print(f"[Kitchen] Planned Order {result.get('order_id')}")
                # Sync order status + estimated time to orders table
                if result.get("success"):
                    sync_order_status(
                        result["order_id"],
                        "QUEUED",
                        result.get("estimated_total_minutes"),
                    )
            except Exception as e:
                print(f"[Kitchen Error] Plan Order failed: {e}")
                result = {"success": False, "message": str(e)}

        # --------------------------------------------------------
        # UPDATE STATUS (MODIFIED FOR HARD DELETE)
        # --------------------------------------------------------
        elif command == "update_status":
            task_id = payload.get("task_id")
            new_status = payload.get("new_status")

            try:
                db = get_db_instance()
                
                # Check current status first
                with db.get_connection() as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute("SELECT status FROM kitchen_tasks WHERE task_id = %s", (task_id,))
                        row = cur.fetchone()
                old_status = row["status"] if row else None

                if not old_status:
                    result = {"success": False, "message": f"Task {task_id} not found."}
                else:
                    # Allowed transitions logic
                    allowed_next = ALLOWED_STATUS_FLOW.get(old_status, [])

                    if new_status not in allowed_next:
                        result = {
                            "success": False,
                            "message": f"Invalid transition {old_status} -> {new_status}"
                        }
                    else:
                        # === HARD DELETE LOGIC ===
                        if new_status == "COMPLETED":
                            # Fetch order_id before deleting the row
                            with db.get_connection() as conn:
                                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                                    cur.execute("SELECT order_id FROM kitchen_tasks WHERE task_id = %s", (task_id,))
                                    task_row = cur.fetchone()
                            order_id_for_sync = task_row["order_id"] if task_row else None

                            with db.get_connection() as conn:
                                with conn.cursor() as cur:
                                    cur.execute("DELETE FROM kitchen_tasks WHERE task_id = %s", (task_id,))
                                    conn.commit()

                            print(f"[Kitchen] 🗑️ DELETED Task {task_id} from Database.")

                            # Recompute order status from remaining tasks
                            if order_id_for_sync:
                                compute_and_sync_order_status(order_id_for_sync)

                            result = {
                                "success": True,
                                "task_id": task_id,
                                "new_status": "COMPLETED",
                                "message": "Task completed and removed from DB."
                            }

                        # === NORMAL UPDATE LOGIC ===
                        else:
                            ok = update_task_status(task_id, new_status)
                            if ok:
                                with db.get_connection() as conn:
                                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                                        cur.execute("SELECT order_id FROM kitchen_tasks WHERE task_id=%s", (task_id,))
                                        t = cur.fetchone()
                                if t:
                                    compute_and_sync_order_status(t["order_id"])
                            result = {
                                "success": ok,
                                "task_id": task_id,
                                "old_status": old_status,
                                "new_status": new_status,
                                "message": f"Status updated: {old_status} -> {new_status}"
                            }

            except Exception as e:
                print(f"[Kitchen Error] Status update failed: {e}")
                result = {"success": False, "message": str(e)}

        # --------------------------------------------------------
        # UNKNOWN COMMAND
        # --------------------------------------------------------
        else:
            result = {"success": False, "message": f"Unknown command {command}"}

        # Send response back to orchestrator
        if response:
            redis_client.publish(response, json.dumps(result))


if __name__ == "__main__":
    from monitoring.agent_lifecycle_manager import wrap_agent
    wrap_agent("kitchen", main)
