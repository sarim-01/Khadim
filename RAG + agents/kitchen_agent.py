import os
import json
import redis
import psycopg2
import psycopg2.extras
from datetime import datetime
from dotenv import load_dotenv

from config import AGENT_TASKS_CHANNEL
from database_connection import DatabaseConnection

load_dotenv()

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
            c.active_status
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
#   KITCHEN ORDER PLANNER
# =========================================================

def plan_order(payload):
    print(f"\n[DEBUG KITCHEN] ------------------------------------------------")
    print(f"[DEBUG KITCHEN] Incoming Payload: {payload}") 

    order_id = payload.get("order_id")
    items = payload.get("items", [])

    tasks = []
    chef_load = {}
    chef_tasks = {}
    cached_chefs = {}
    task_counter = 1

    for entry in items:
        item_id = entry.get("menu_item_id")
        
        # 1. Fetch menu item
        item = fetch_menu_item(item_id)
        
        if not item:
            print(f"[DEBUG KITCHEN] ❌ ERROR: Item {item_id} returns None from DB. Check your menu_item table!")
            continue 
            
        # 2. Assign Chef
        item_name = item.get("item_name")
        category = item.get("item_category")
        cuisine = item.get("item_cuisine")
        prep_time = item.get("prep_time_minutes") or 15
        station = infer_station(category, cuisine)

        # Check Chefs
        if item_id not in cached_chefs:
            cached_chefs[item_id] = fetch_chefs_for_item(item_id)
        
        chef_list = cached_chefs[item_id]
        
        if not chef_list:
             assigned_chef = "UNASSIGNED"
        else:
             # Simple assignment
             assigned_chef = chef_list[0]["cheff_name"]

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
                
                # --- [MODIFICATION START] ---
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
                            with db.get_connection() as conn:
                                with conn.cursor() as cur:
                                    cur.execute("DELETE FROM kitchen_tasks WHERE task_id = %s", (task_id,))
                                    conn.commit()
                            
                            print(f"[Kitchen] 🗑️ DELETED Task {task_id} from Database.")
                            result = {
                                "success": True, 
                                "task_id": task_id, 
                                "new_status": "COMPLETED",
                                "message": "Task completed and removed from DB."
                            }
                        
                        # === NORMAL UPDATE LOGIC ===
                        else:
                            ok = update_task_status(task_id, new_status)
                            result = {
                                "success": ok,
                                "task_id": task_id,
                                "old_status": old_status,
                                "new_status": new_status,
                                "message": f"Status updated: {old_status} -> {new_status}"
                            }
                # --- [MODIFICATION END] ---

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
    from agent_lifecycle_manager import wrap_agent
    wrap_agent("kitchen", main)