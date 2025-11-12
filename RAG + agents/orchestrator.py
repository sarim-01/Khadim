# Docker khol kar run following command on the terminal in Vs code docker run -d --name redis -p 6379:6379 redis

import os
import uuid
import re
import json
import time
import streamlit as st
from dotenv import load_dotenv

from search_agent import load_texts, SearchAgent
from conversation_manager import ConversationManager
from database_connection import DatabaseConnection
from chat_agent import get_ai_response 
from rag_retriever import RAGRetriever

from redis_connection import RedisConnection
from config import AGENT_TASKS_CHANNEL, RESPONSE_CHANNEL_PREFIX

load_dotenv()

# --- Streamlit Page Setup ---
st.set_page_config(page_title="Khadim Bot", page_icon="🍽️")
st.title("🍴 Khadim Restaurant Chatbot")

# ----------------------------------------------------
# Redis Pub/Sub Helper
# ----------------------------------------------------
def send_task_and_get_response(agent: str, command: str, payload: dict) -> dict:
    """
    Sends a Redis task and waits for agent response (robust version).
    Ensures correct Redis pub/sub decoding, timeout, and logging.
    """
    redis_conn = st.session_state.redis_conn
    response_channel = f"{RESPONSE_CHANNEL_PREFIX}{uuid.uuid4()}"
    task_data = {
        "agent": agent,
        "command": command,
        "payload": payload,
        "response_channel": response_channel
    }

    try:
        pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(response_channel)

        # Publish task to the shared channel
        redis_conn.publish(AGENT_TASKS_CHANNEL, json.dumps(task_data))
        print(f"[Orchestrator → Redis] Sent {agent}:{command}")

        # 👇 ADD THIS LINE
        print(f"[DEBUG] Published to Redis: {json.dumps(task_data, indent=2)}")  # 👈 ADDED

        # --- wait for reply ---
        timeout = time.time() + 8  # wait up to 8 seconds
        while time.time() < timeout:
            message = pubsub.get_message(timeout=1.0)
            if not message:
                continue

            # Debug: print every raw message
            print(f"[Orchestrator ← Redis] Raw message: {message}")

            data = message.get("data")
            if isinstance(data, bytes):  # decode if needed
                data = data.decode("utf-8", errors="ignore")

            try:
                result = json.loads(data)
                pubsub.unsubscribe(response_channel)
                print(f"[Orchestrator] Got reply from {agent} agent ✅")
                return result
            except json.JSONDecodeError:
                print(f"[WARN] Could not decode message: {data}")

        pubsub.unsubscribe(response_channel)
        print(f"[Timeout] No response from {agent} agent in 8s.")
        return {"success": False, "message": f"No response from {agent} agent."}

    except Exception as e:
        print(f"[Redis Error] {str(e)}")
        return {"success": False, "message": f"Redis communication error: {str(e)}"}




# ----------------------------------------------------
# Initialize Session State
# ----------------------------------------------------
if "initialized" not in st.session_state:
    st.session_state.conv_mgr = ConversationManager(max_history=10)
    st.session_state.search_agent = SearchAgent()
    st.session_state.rag_retriever = RAGRetriever()
    st.session_state.redis_conn = RedisConnection.get_instance()
    st.session_state.db_conn = DatabaseConnection.get_instance()

    st.session_state.redis_ok = st.session_state.redis_conn is not None
    st.session_state.db_ok = st.session_state.db_conn.test_connection()

    st.session_state.cart_id = str(uuid.uuid4())
    st.session_state.initialized = True
    st.session_state.force_refresh = False

    if st.session_state.redis_ok:
        send_task_and_get_response('cart', 'create_cart', {'user_id': st.session_state.cart_id})

if not st.session_state.db_ok:
    st.error("Database connection failed.")
    st.stop()

if not st.session_state.redis_ok:
    st.error("Redis connection failed. Agents cannot be contacted.")
    st.stop()

# ----------------------------------------------------
# Sidebar: Cart Summary + Place Order
# ----------------------------------------------------
with st.sidebar:
    st.header("🛒 Your Cart")

    # Ensure we have a cart_id
    if "cart_id" not in st.session_state:
        st.session_state.cart_id = str(uuid.uuid4())
        send_task_and_get_response('cart', 'create_cart', {'user_id': st.session_state.cart_id})

    # Try a few times to get fresh data (handles small DB delays)
    summary = {}
    for _ in range(5):
        summary = send_task_and_get_response(
            agent='cart',
            command='get_cart_summary',
            payload={'cart_id': st.session_state.cart_id}
        )
        # ✅ FIX: Check for 'items' instead of 'success'
        if summary and "items" in summary:
            break
        time.sleep(0.3)

    # --- Display Cart Info ---
    if not summary or "items" not in summary:
        st.error("Could not contact Cart Agent.")
        st.caption(summary.get("message", "") if isinstance(summary, dict) else "")
    elif summary.get("is_empty", True):
        st.info(" Your cart is empty.")
    else:
        for item in summary["items"]:
            st.write(
                f"{item['quantity']}× **{item['item_name']}** — Rs. {item['unit_price']:.2f} "
                f"(Total: Rs. {item['total_price']:.2f})"
            )
        st.markdown(f"### Total: Rs. {summary['total_price']:.2f}")

        # Place order button
        if st.button("Place Order"):
            finalize_result = send_task_and_get_response(
                'cart', 'place_order', {'cart_id': st.session_state.cart_id}
            )
            if finalize_result.get('success'):
                cart_summary = finalize_result.get('order_data')
                order_result = send_task_and_get_response(
                    'order',
                    'save_and_summarize_order',
                    {'cart_id': st.session_state.cart_id, 'cart_summary': cart_summary}
                )
                st.success(order_result['message'])
                # Reset to new cart
                new_cart_id = str(uuid.uuid4())
                st.session_state.cart_id = new_cart_id
                send_task_and_get_response('cart', 'create_cart', {'user_id': new_cart_id})
                st.rerun()
            else:
                st.warning(finalize_result.get('message', 'Order failed.'))



# ----------------------------------------------------
# Main Chat Interface
# ----------------------------------------------------
st.markdown("---")
st.header("Conversation")

for msg in st.session_state.conv_mgr.get_history():
    st.markdown(f"**{msg['role'].title()}:** {msg['content']}")

with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_input("Your message", "")
    submitted = st.form_submit_button("Send")

# ----------------------------------------------------
# RAG + Tool Execution
# ----------------------------------------------------
if submitted and user_input:
    conv_mgr = st.session_state.conv_mgr
    agent_search = st.session_state.search_agent
    rag = st.session_state.rag_retriever

    conv_mgr.add_message("user", user_input)

    # Use RAG for context
    relevant_context = rag.search(user_input)

    # Get AI response
    ai_message = get_ai_response(user_input, conv_mgr.get_history(), relevant_context)
    bot_response = ""

    # Handle tool calls
    if ai_message.tool_calls:
        tool_call = ai_message.tool_calls[0]
        function_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)

        # --- ADD TO CART ---
        if function_name == "add_to_cart":
            item_name = args.get("item_name")
            quantity = args.get("quantity", 1)
            hits = agent_search.search(item_name)
            if hits:
                item_data = hits[0]
                payload = {
                    'cart_id': st.session_state.cart_id,
                    'item_data': item_data,
                    'quantity': quantity
                }
                result = send_task_and_get_response('cart', 'add_item', payload)
                bot_response = result['message']
                st.session_state.force_refresh = True
            else:
                bot_response = f"I couldn't find '{item_name}' on the menu."

        # --- REMOVE ITEM ---
        elif function_name == "remove_from_cart":
            item_name = args.get("item_name")
            payload = {'cart_id': st.session_state.cart_id, 'item_name': item_name}
            result = send_task_and_get_response('cart', 'remove_item', payload)
            bot_response = result['message']
            st.session_state.force_refresh = True

        # --- SHOW CART ---
        elif function_name == "show_cart":
            payload = {'cart_id': st.session_state.cart_id}
            summary = send_task_and_get_response('cart', 'get_cart_summary', payload)
            if summary.get('success', False) and not summary.get('is_empty', True):
                bot_response = "Here are the items in your cart:\n"
                for it in summary["items"]:
                    bot_response += f"- {it['quantity']}× {it['item_name']} @ Rs. {it['unit_price']:.2f}\n"
                bot_response += f"**Total: Rs. {summary['total_price']:.2f}**"
            else:
                bot_response = "Your cart is currently empty."
            st.session_state.force_refresh = True

        # --- PLACE ORDER ---
        elif function_name == "place_order":
            finalize_result = send_task_and_get_response('cart', 'place_order', {'cart_id': st.session_state.cart_id})
            if finalize_result.get('success'):
                cart_summary = finalize_result.get('order_data')
                order_result = send_task_and_get_response(
                    'order',
                    'save_and_summarize_order',
                    {'cart_id': st.session_state.cart_id, 'cart_summary': cart_summary}
                )
                bot_response = order_result.get('message', 'Order failed.')
                if order_result.get('success'):
                    new_cart_id = str(uuid.uuid4())
                    st.session_state.cart_id = new_cart_id
                    send_task_and_get_response('cart', 'create_cart', {'user_id': new_cart_id})
                    bot_response += "\n\nI've started a new empty cart for you."
                st.session_state.force_refresh = True
            else:
                bot_response = finalize_result.get('message', 'Your cart is empty.')
                st.session_state.force_refresh = True

    else:
        bot_response = ai_message.content

    conv_mgr.add_message("assistant", bot_response)

# ----------------------------------------------------
# Force Refresh (Single Rerun per Update)
# ----------------------------------------------------
if st.session_state.get("force_refresh", False):
    st.session_state.force_refresh = False
    # Show current assistant response first
    placeholder = st.empty()
    placeholder.info("Updating cart... please wait")
    # Schedule rerun *after* a short delay
    time.sleep(1.0)
    st.rerun()
