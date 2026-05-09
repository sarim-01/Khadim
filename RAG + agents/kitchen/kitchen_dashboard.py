import streamlit as st
import time
import pandas as pd
import json
import uuid
import os
from dotenv import load_dotenv
from infrastructure.database_connection import DatabaseConnection
from infrastructure.redis_client import get_sync_redis
import psycopg2.extras

load_dotenv()

# --- CONFIG ---
st.set_page_config(page_title="👨‍🍳 Kitchen Dashboard", page_icon="🔥", layout="wide")

# Redis: REDIS_URL (Railway) or REDIS_HOST + REDIS_PORT
AGENT_TASKS_CHANNEL = "agent_tasks"
RESPONSE_CHANNEL_PREFIX = "agent_response_"

# Status Colors & Labels
STATUS_CONFIG = {
    "QUEUED":      {"color": "🔴", "label": "QUEUED"},
    "IN_PROGRESS": {"color": "🟠", "label": "COOKING"},
    "READY":       {"color": "🟢", "label": "READY TO SERVE"},
    "COMPLETED":   {"color": "🏁", "label": "DONE"}
}

# --- HELPERS ---

def get_redis_client():
    return get_sync_redis()

def send_update_command(task_id, new_status):
    """Sends a command to the Kitchen Agent via Redis to update status."""
    try:
        r = get_redis_client()
        response_channel = f"{RESPONSE_CHANNEL_PREFIX}{uuid.uuid4()}"
        
        payload = {
            "agent": "kitchen",
            "command": "update_status",
            "payload": {
                "task_id": task_id,
                "new_status": new_status
            },
            "response_channel": response_channel
        }
        
        r.publish(AGENT_TASKS_CHANNEL, json.dumps(payload))
        st.toast(f"Task {task_id} updated to {new_status}!", icon="👨‍🍳")
        
        # Small delay to allow DB to update before reload
        time.sleep(0.5) 
        st.rerun()
    except Exception as e:
        st.error(f"Failed to update task: {e}")

def fetch_active_tasks():
    """Fetches all tasks that are NOT completed."""
    db = DatabaseConnection.get_instance()
    sql = """
        SELECT kt.*, o.order_type, o.round_number,
               rt.table_number, ds.session_id
        FROM kitchen_tasks kt
        LEFT JOIN orders o ON kt.order_id = o.order_id
        LEFT JOIN restaurant_tables rt ON o.table_id = rt.table_id
        LEFT JOIN dine_in_sessions ds ON o.session_id = ds.session_id
        WHERE kt.status != 'COMPLETED'
        ORDER BY kt.order_id ASC, kt.created_at ASC
    """
    try:
        with db.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return cur.fetchall()
    except Exception as e:
        st.error(f"Database Error: {e}")
        return []


def fetch_all_tables():
    db = DatabaseConnection.get_instance()
    sql = """
        SELECT rt.table_id, rt.table_number, rt.status,
               ds.session_id, ds.started_at, ds.total_amount,
               ds.round_count
        FROM restaurant_tables rt
        LEFT JOIN dine_in_sessions ds
            ON rt.table_id = ds.table_id
            AND ds.status NOT IN ('closed')
        ORDER BY rt.table_number
    """
    try:
        with db.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return cur.fetchall()
    except Exception as e:
        st.error(f"Database Error: {e}")
        return []


def fetch_waiter_calls():
    db = DatabaseConnection.get_instance()
    sql = """
        SELECT wc.call_id, wc.table_id, wc.called_at, wc.resolved,
               rt.table_number
        FROM waiter_calls wc
        JOIN restaurant_tables rt ON wc.table_id = rt.table_id
        WHERE wc.resolved = false
        ORDER BY wc.called_at ASC
    """
    try:
        with db.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return cur.fetchall()
    except Exception:
        return []


def confirm_cash_payment(session_id):
    db = DatabaseConnection.get_instance()
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE orders SET payment_status = 'paid'
                    WHERE session_id = %s
                """,
                    (session_id,),
                )
                cur.execute(
                    """
                    UPDATE dine_in_sessions
                    SET status = 'closed', ended_at = NOW(),
                        payment_method = 'cash'
                    WHERE session_id = %s
                """,
                    (session_id,),
                )
                cur.execute(
                    """
                    UPDATE restaurant_tables SET status = 'available'
                    WHERE table_id = (
                        SELECT table_id FROM dine_in_sessions
                        WHERE session_id = %s
                    )
                """,
                    (session_id,),
                )
            conn.commit()
        st.toast("✅ Cash confirmed! Table is now available.", icon="💵")
        time.sleep(0.5)
        st.rerun()
    except Exception as e:
        st.error(f"Failed to confirm payment: {e}")


def mark_table_ready(table_id):
    db = DatabaseConnection.get_instance()
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE restaurant_tables SET status = 'available'
                    WHERE table_id = %s
                """,
                    (table_id,),
                )
            conn.commit()
        st.toast("✅ Table is now available!", icon="🟢")
        time.sleep(0.5)
        st.rerun()
    except Exception as e:
        st.error(f"Failed to mark table ready: {e}")


def resolve_waiter_call(call_id):
    db = DatabaseConnection.get_instance()
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE waiter_calls SET resolved = true
                    WHERE call_id = %s
                """,
                    (call_id,),
                )
            conn.commit()
        st.rerun()
    except Exception as e:
        st.error(f"Error: {e}")

# --- MAIN UI ---

st.title("👨‍🍳 Kitchen Display System (KDS)")

# 1. SIDEBAR CONTROLS
with st.sidebar:
    st.header("Controls")
    refresh_rate = st.slider("Auto-Refresh Rate (seconds)", 5, 60, 15)
    
    if st.button("🔄 Force Refresh Now", use_container_width=True):
        st.rerun()
    
    st.divider()
    st.caption("Status Legend:")
    st.markdown("🔴 **Queued**: New Order")
    st.markdown("🟠 **Cooking**: Chef working")
    st.markdown("🟢 **Ready**: Waiter can take")

    st.divider()
    st.header("🪑 Table Status")
    TABLE_STATUS_COLORS = {
        'available': '🟢',
        'occupied': '🟡',
        'bill_requested_cash': '🟠',
        'bill_requested_card': '🔵',
        'cleaning': '⚫',
    }

    tables = fetch_all_tables()
    for table in tables:
        icon = TABLE_STATUS_COLORS.get(table['status'], '⚪')
        label = table['table_number']
        status = table['status'].replace('_', ' ').title()
        with st.expander(f"{icon} {label} — {status}"):
            if table['started_at']:
                st.caption(f"Started: {table['started_at'].strftime('%I:%M %p')}")
                st.caption(
                    f"Rounds: {table['round_count']}  |  "
                    f"Total: Rs {table['total_amount']}"
                )
            if table['status'] == 'bill_requested_cash':
                if st.button(
                    f"💵 Confirm Cash — {label}",
                    key=f"cash_{table['session_id']}",
                    type="primary",
                    use_container_width=True,
                ):
                    confirm_cash_payment(str(table['session_id']))
            if table['status'] == 'cleaning':
                if st.button(
                    f"✅ Mark {label} Ready",
                    key=f"ready_{table['table_id']}",
                    use_container_width=True,
                ):
                    mark_table_ready(str(table['table_id']))

    st.divider()
    st.header("🔔 Waiter Calls")
    waiter_calls = fetch_waiter_calls()
    if not waiter_calls:
        st.caption("No active waiter calls.")
    else:
        for call in waiter_calls:
            col1, col2 = st.columns([2, 1])
            col1.markdown(
                f"**{call['table_number']}** — "
                f"{call['called_at'].strftime('%I:%M %p')}"
            )
            if col2.button("✅", key=f"resolve_{call['call_id']}"):
                resolve_waiter_call(str(call['call_id']))

# 2. FETCH DATA
tasks = fetch_active_tasks()

if not tasks:
    st.success("🎉 All caught up! No active orders.")
else:
    # Group tasks by Order ID
    df = pd.DataFrame(tasks)
    orders = df.groupby("order_id")

    # 3. GRID LAYOUT (Max 3 orders per row)
    COLS_PER_ROW = 3
    order_groups = [list(orders)[i:i + COLS_PER_ROW] for i in range(0, len(orders), COLS_PER_ROW)]

    for group in order_groups:
        cols = st.columns(COLS_PER_ROW)
        
        for idx, (order_id, order_items) in enumerate(group):
            with cols[idx]:
                # CARD CONTAINER
                with st.container(border=True):
                    # Header
                    c_head1, c_head2 = st.columns([2, 1])
                    c_head1.subheader(f"🆔 #{order_id}")
                    c_head2.caption(f"{len(order_items)} Items")
                    first_item = order_items.iloc[0]
                    if first_item.get('order_type') == 'dine_in':
                        st.markdown(
                            f"🪑 **TABLE {first_item['table_number']} — Round {first_item['round_number']}**",
                            unsafe_allow_html=False,
                        )
                    st.divider()

                    # ITEMS LIST
                    for _, item in order_items.iterrows():
                        task_id = item['task_id']
                        status = item['status']
                        item_name = item['item_name']
                        chef = item['assigned_chef']
                        qty = item['qty']
                        
                        # Get Style info
                        style = STATUS_CONFIG.get(status, STATUS_CONFIG["QUEUED"])
                        
                        # Item Row
                        st.markdown(f"**{qty}x {item_name}**")
                        st.caption(f"👨‍🍳 {chef} | {style['color']} {style['label']}")
                        
                        # BIG ACTION BUTTONS
                        if status == "QUEUED":
                            if st.button("🔥 Start Cooking", key=f"btn_cook_{task_id}", type="primary", use_container_width=True):
                                send_update_command(task_id, "IN_PROGRESS")
                        
                        elif status == "IN_PROGRESS":
                            if st.button("✅ Mark Ready", key=f"btn_ready_{task_id}", use_container_width=True):
                                send_update_command(task_id, "READY")
                                
                        elif status == "READY":
                            if st.button("🏁 Complete", key=f"btn_done_{task_id}", use_container_width=True):
                                send_update_command(task_id, "COMPLETED")
                        
                        st.markdown("---")


# 4. NON-BLOCKING AUTO REFRESH LOGIC
# This puts a small text at the bottom right instead of freezing the script
if refresh_rate:
    time.sleep(1) # Small sleep to prevent tight loops, but not blocking interactions
    st.empty() # Placeholder
    
    # We use a trick: only rerun if enough time passed, 
    # but Streamlit runs top-to-bottom. 
    # The 'st_autorefresh' library is better, but to keep it pure python:
    
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = time.time()

    if time.time() - st.session_state.last_refresh > refresh_rate:
        st.session_state.last_refresh = time.time()
        st.rerun()