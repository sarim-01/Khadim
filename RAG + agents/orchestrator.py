# Docker khol kar run following command on the terminal in Vs code: docker run -d --name redis -p 6379:6379 redis

import os
import uuid
import re
import json
import time
import requests # Needed for weather test
import streamlit as st
from datetime import datetime
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
# Redis Pub/Sub Helper (YOUR ROBUST VERSION)
# ----------------------------------------------------
def send_task_and_get_response(agent: str, command: str, payload: dict) -> dict:
    """
    Sends a Redis task and waits for agent response.
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

        # Publish task
        redis_conn.publish(AGENT_TASKS_CHANNEL, json.dumps(task_data))
        # print(f"[DEBUG] Published to {agent}: {command}")

        # Wait for reply
        timeout = time.time() + 8
        while time.time() < timeout:
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
                pass

        pubsub.unsubscribe(response_channel)
        return {"success": False, "message": f"Timeout: No response from {agent}."}

    except Exception as e:
        return {"success": False, "message": f"Redis error: {str(e)}"}

# ----------------------------------------------------
# KITCHEN & ORDER HELPERS (FROM GROUP MEMBER)
# ----------------------------------------------------

def expand_deal_items(db: DatabaseConnection, deal_id: int, deal_qty: int):
    """
    Convert a deal_id into its underlying menu items.
    """
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
            # Handle both RealDictCursor and standard tuple cursor
            if isinstance(row, dict):
                menu_item_id = int(row["menu_item_id"])
                base_qty = int(row["quantity"] or 1)
            else:
                menu_item_id = int(row[0])
                base_qty = int(row[1] or 1)

            items.append({
                "menu_item_id": menu_item_id,
                "qty": base_qty * deal_qty,
            })
    except Exception as e:
        print(f"Error expanding deal: {e}")
        
    return items

def finalize_order_and_send_to_kitchen(cart_id: str) -> dict:
    """
    Full pipeline: 
    1) Cart Finalize 
    2) Save Order 
    3) ID CORRECTION (For Items AND Deals)
    4) Send to Kitchen
    """
    # 1) Finalize cart
    finalize_result = send_task_and_get_response("cart", "place_order", {"cart_id": cart_id})

    if not finalize_result.get("success"):
        return {"success": False, "message": finalize_result.get("message", "Your cart is empty.")}

    cart_summary = finalize_result.get("order_data", {})
    raw_items = cart_summary.get("items", [])

    # 2) Save order in DB
    order_result = send_task_and_get_response(
        "order", "save_and_summarize_order",
        {"cart_id": cart_id, "cart_summary": cart_summary}
    )

    base_message = order_result.get("message", "Order processed.")
    order_id = order_result.get("order_id")

    # ---------------------------------------------------------
    # 3) PREPARE & HEAL KITCHEN ITEMS (THE FIX)
    # ---------------------------------------------------------
    kitchen_items = []
    db = st.session_state.db_conn
    
    print(f"\n[ORCHESTRATOR] Starting ID Correction for Order #{order_id}...")

    for it in raw_items:
        original_id = it.get("item_id")
        name = it.get("item_name")
        qty = int(it.get("quantity", 1))
        # Default to menu_item if missing, but deals usually have "deal"
        item_type = it.get("item_type", "menu_item") 

        if not name: 
            continue

        real_id = original_id # Start assuming it's correct

        # --- HEALING LOGIC ---
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    
                    # CASE A: It is a DEAL
                    if item_type == "deal":
                        cur.execute("SELECT deal_id FROM deal WHERE deal_name ILIKE %s", (name,))
                        row = cur.fetchone()
                        if row:
                            real_id = row[0] if isinstance(row, tuple) else row['deal_id']
                            if str(real_id) != str(original_id):
                                print(f"[FIXED DEAL] '{name}': Swapped Stale ID {original_id} -> Real ID {real_id}")
                    
                    # CASE B: It is a MENU ITEM
                    else:
                        cur.execute("SELECT item_id FROM menu_item WHERE item_name ILIKE %s", (name,))
                        row = cur.fetchone()
                        if row:
                            real_id = row[0] if isinstance(row, tuple) else row['item_id']
                            if str(real_id) != str(original_id):
                                print(f"[FIXED ITEM] '{name}': Swapped Stale ID {original_id} -> Real ID {real_id}")

        except Exception as e:
            print(f"[ERROR] ID Correction failed: {e}")
        # -------------------------

        # --- BUILD KITCHEN PAYLOAD ---
        
        # 1. If it's a Deal, we must expand it using the REAL ID
        if item_type == "deal":
            deal_id = int(real_id)
            # Use the helper function to look up 'deal_item' table
            expanded = expand_deal_items(db, deal_id, qty)
            
            if not expanded:
                print(f"[WARN] Deal '{name}' (ID {deal_id}) expanded to 0 items. Check deal_item table!")
            
            for e in expanded:
                # Tag it so Kitchen knows it came from a deal
                e["expanded_from_deal"] = name
            
            kitchen_items.extend(expanded)

        # 2. If it's a regular Menu Item
        else:
            kitchen_items.append({"menu_item_id": int(real_id), "qty": qty})

    # 4) Send Corrected Payload to Kitchen
    kitchen_message = ""
    if order_id and kitchen_items:
        kitchen_payload = {"order_id": order_id, "items": kitchen_items}
        
        # Debug Print
        print(f"[ORCHESTRATOR] Sending Corrected Payload to Kitchen: {len(kitchen_items)} items")
        
        kitchen_plan = send_task_and_get_response("kitchen", "plan_order", kitchen_payload)

        if kitchen_plan.get("success"):
            est = kitchen_plan.get("estimated_total_minutes", "?")
            kitchen_message = f"\n\n👨‍🍳 **Kitchen Update:** Your order is being prepared.\n⏱️ Estimated time: **{est} minutes**."
        else:
            kitchen_message = "\n\n(Note: Kitchen system offline, but order is saved.)"
    
    full_message = base_message + kitchen_message
    return {
        "success": True,
        "message": full_message,
        "order_result": order_result
    }

def update_kitchen_task(task_id: str, new_status: str) -> dict:
    """Debug helper to update kitchen status"""
    return send_task_and_get_response("kitchen", "update_status", {"task_id": task_id, "new_status": new_status})

# ----------------------------------------------------
# Initialize Session State & STARTUP LOGIC
# ----------------------------------------------------
if "initialized" not in st.session_state:
    st.session_state.conv_mgr = ConversationManager(max_history=10)
    st.session_state.search_agent = SearchAgent()
    st.session_state.rag_retriever = RAGRetriever()
    st.session_state.redis_conn = RedisConnection.get_instance()
    st.session_state.db_conn = DatabaseConnection.get_instance()

    st.session_state.redis_ok = st.session_state.redis_conn is not None
    st.session_state.db_ok = st.session_state.db_conn.test_connection()

    # Create Initial Cart
    st.session_state.cart_id = str(uuid.uuid4())
    st.session_state.initialized = True
    st.session_state.force_refresh = False
    st.session_state.selected_city = "Islamabad" # Default

    if st.session_state.redis_ok:
        send_task_and_get_response('cart', 'create_cart', {'user_id': st.session_state.cart_id})

    # --- STARTUP SMART GREETING (NEW FEATURE) ---
    if "did_startup_upsell" not in st.session_state and st.session_state.redis_ok:
        st.session_state.did_startup_upsell = True
        
        now = datetime.now()
        hour = now.hour
        greeting = "Good morning" if 5 <= hour < 12 else "Good afternoon" if 12 <= hour < 17 else "Good evening"
        
        startup_msg = f"{greeting}! Welcome to Khadim.\n\n"
        
        # 1. Weather Upsell
        result = send_task_and_get_response("upsell", "weather_upsell", {"city": st.session_state.selected_city})
        
        if result.get("success"):
            wx = result.get("weather", {})
            temp = wx.get("temp")
            cond = wx.get("condition")
            headline = result.get("headline", "Here are some suggestions:")
            items = result.get("items", [])
            
            if temp and cond:
                startup_msg += f"It's currently **{temp:.1f}°C** ({cond}) in {st.session_state.selected_city}.\n{headline}\n"
            
            for it in items:
                startup_msg += f"- {it.get('item_name')} ({it.get('item_cuisine')})\n"
        
        startup_msg += "\nHow can I help you today?"
        st.session_state.conv_mgr.add_message("assistant", startup_msg)

if not st.session_state.db_ok:
    st.error("Database connection failed.")
    st.stop()

if not st.session_state.redis_ok:
    st.error("Redis connection failed.")
    st.stop()

# ----------------------------------------------------
# Sidebar
# ----------------------------------------------------
with st.sidebar:
    # --- CITY SELECTOR (For Weather Upsell Testing) ---
    st.header("🌍 Location")
    cities = ["Islamabad", "Lahore", "Karachi", "London", "Moscow", "Dubai"]
    selection = st.selectbox("Select City", cities, index=0)
    
    if selection != st.session_state.selected_city:
        st.session_state.selected_city = selection
        # Reset startup upsell to trigger it again with new city
        st.session_state.did_startup_upsell = False 
        st.rerun()

    st.divider()

    # --- CART SECTION (YOUR ROBUST LOGIC) ---
    st.header("🛒 Your Cart")
    summary = {}
    for _ in range(3): 
        summary = send_task_and_get_response('cart', 'get_cart_summary', {'cart_id': st.session_state.cart_id})
        if summary and "items" in summary: break
        time.sleep(0.2)

    if not summary or "items" not in summary:
        st.caption("Connecting to cart...")
    elif summary.get("is_empty", True):
        st.info("Cart is empty.")
    else:
        for item in summary["items"]:
            st.write(f"{item['quantity']}× **{item['item_name']}**\nRs. {item['total_price']:.2f}")
        st.markdown(f"### Total: Rs. {summary['total_price']:.2f}")

        # --- PLACE ORDER BUTTON ---
        if st.button("Place Order"):
            with st.spinner("sending to kitchen..."):
                # Use the NEW Pipeline
                flow_result = finalize_order_and_send_to_kitchen(st.session_state.cart_id)
                
                if flow_result.get('success'):
                    msg = flow_result.get('message')
                    st.success("Order Sent!")
                    
                    # Sync with Chat
                    st.session_state.conv_mgr.add_message("assistant", f"{msg}\n\nI have started a new empty cart for you.")
                    
                    # Reset Cart
                    new_cart_id = str(uuid.uuid4())
                    st.session_state.cart_id = new_cart_id
                    send_task_and_get_response('cart', 'create_cart', {'user_id': new_cart_id})
                    
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(flow_result.get('message', 'Order failed.'))

    st.divider()
    
    # --- DEV TOOLS (From Group Member) ---
    with st.expander("👨‍🍳 Dev Tools"):
        st.caption("Kitchen Status Test")
        t_id = st.text_input("Task ID (e.g. orderid-1)")
        stat = st.selectbox("Status", ["QUEUED", "IN_PROGRESS", "READY", "COMPLETED"])
        if st.button("Update Status"):
            res = update_kitchen_task(t_id, stat)
            st.write(res)

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
# Chat Logic
# ----------------------------------------------------
if submitted and user_input:
    conv_mgr = st.session_state.conv_mgr

    # --- HANDLE AFFIRMATIVE RESPONSE TO RECOMMENDATIONS ---
    # Check if user is saying "yes" to a previous recommendation
    affirmative_words = ["yes", "sure", "okay", "ok", "yeah", "yep", "add it", "add that", "sounds good"]
    user_lower = user_input.lower().strip()
    
    if "last_recommendation" in st.session_state and any(word in user_lower for word in affirmative_words):
        recommended_item = st.session_state.last_recommendation
        
        with st.spinner(f"Adding {recommended_item} to cart..."):
            # Search for the recommended item
            agent_search = st.session_state.search_agent
            hits = agent_search.search(recommended_item)
            
            if hits:
                item_data = hits[0]
                if "type" not in item_data or not item_data["type"]:
                    item_data["type"] = "menu_item"
                
                # Add to cart
                payload = {
                    'cart_id': st.session_state.cart_id,
                    'item_data': item_data,
                    'quantity': 1
                }
                result = send_task_and_get_response('cart', 'add_item', payload)
                bot_response = result.get('message', f"Added {recommended_item} to cart!")
            else:
                bot_response = f"Sorry, I couldn't find {recommended_item} in our system."
        
        # Clear the recommendation
        del st.session_state.last_recommendation
        
        # Add to conversation and refresh
        conv_mgr.add_message("user", user_input)
        conv_mgr.add_message("assistant", bot_response)
        st.session_state.force_refresh = True
        st.rerun()

    # --- [INSERT THIS BLOCK] START ---
    # Handle "Add this deal" for Custom Deals
    if "last_custom_deal" in st.session_state and "add" in user_input.lower() and "deal" in user_input.lower():
        items_to_add = st.session_state.last_custom_deal
        
        # Set global flag to disable recommendations for custom deals
        st.session_state.adding_custom_deal = True
        
        with st.spinner("Adding custom deal items to cart..."):
            for item in items_to_add:
                # Mark item as coming from custom deal to skip recommender
                item['from_custom_deal'] = True
                payload = {
                    'cart_id': st.session_state.cart_id,
                    'item_data': item, # Contains the item_id and price
                    'quantity': item.get('quantity', 1)
                }
                # We use the standard Cart Agent to add items one by one
                send_task_and_get_response('cart', 'add_item', payload)
            
        bot_response = "🎉 I've added the custom deal to your cart! You can say 'show cart' to verify."
        
        # Clear the flags and state
        del st.session_state.last_custom_deal
        st.session_state.adding_custom_deal = False
        
        # Add messages to history and stop processing
        conv_mgr.add_message("user", user_input)
        conv_mgr.add_message("assistant", bot_response)
        st.rerun()
    # --- [INSERT THIS BLOCK] END ---

    agent_search = st.session_state.search_agent
    rag = st.session_state.rag_retriever

    # Add Reminder to Input (YOUR FIX)
    reminder_text = """
(SYSTEM NOTE: Check your tools. If the user is asking to add, remove, search, or place an order, you MUST generate the 'TOOL_CALL:' line. Do not just say you did it.)
"""
    # conv_mgr.add_message("user", user_input) # Don't add reminder to UI history
    # We add reminder only when sending to AI
    
    relevant_context = rag.search(user_input)
    ai_message = get_ai_response(user_input + reminder_text, conv_mgr.get_history(), relevant_context)
    
    # Store user msg in UI
    conv_mgr.add_message("user", user_input)
    
    bot_response = ""

    if ai_message.tool_calls:
        responses = []
        
        for tool_call in ai_message.tool_calls:
            function_name = tool_call["name"]
            args = tool_call["args"]

            # --- WEATHER UPSELL (NEW) ---
            if function_name == "weather_upsell":
                city = st.session_state.selected_city
                res = send_task_and_get_response("upsell", "weather_upsell", {"city": city})
                if res.get("success"):
                    responses.append(res.get("headline", "Recommendations based on weather:"))
                    for it in res.get("items", []):
                        responses.append(f"- {it['item_name']}")
                else:
                    responses.append("Couldn't check weather right now.")

            # --- 2. SEARCH MENU (NOW SEMANTIC / RAG WITH AI FORMATTING) ---
            elif function_name == "search_menu":
                query = args.get("query", "")
                
                # Get RAG results with more items (AI will filter intelligently)
                rag_results = rag.search(query, k=10)
                
                if rag_results:
                    # Instead of showing raw results, ask AI to format them nicely
                    formatting_prompt = f"""Based on the user's query "{query}", here are the menu items I found:

{rag_results}

Please present these items to the customer in a natural, friendly way. Follow these rules:
- Show only the MOST relevant items (usually 1-3, maximum 5 if all are highly relevant)
- Use conversational language, not database format
- If only 1 item matches perfectly, show only that one
- If nothing truly matches, politely say we don't have it and suggest alternatives
- Format prices as Rs. X
- Make it sound like a real waiter describing the food
- Be concise but helpful"""

                    # Get AI to format the response naturally
                    formatted_response = get_ai_response(
                        formatting_prompt, 
                        conv_mgr.get_history()[-4:],  # Limited context to avoid confusion
                        ""
                    )
                    
                    # Use AI's formatted response instead of raw data
                    responses.append(formatted_response.content if hasattr(formatted_response, 'content') else str(formatted_response))
                else:
                    responses.append(f"I searched the menu but couldn't find anything matching '{query}'.")

            elif function_name == "create_custom_deal":
                # Get the requirement text from the LLM
                user_req = args.get("user_requirement")
                
                print(f"[ORCHESTRATOR] Calling deal agent with: {user_req}")
                
                # Send to Custom Deal Agent via Redis
                result = send_task_and_get_response(
                    "deal_agent", 
                    "create_custom_deal", 
                    {"user_query": user_req}
                )
                
                print(f"[ORCHESTRATOR] Deal agent response: {result}")
                
                if result.get("success"):
                    msg = result.get("message")
                    
                    # Store the items in Session State!
                    # This allows the "Follow-up Handler" (Step 1) to find them later.
                    deal_data = result.get("deal_data", {})
                    st.session_state.last_custom_deal = deal_data.get("items", [])
                    
                    msg += "\n\n👉 **just say add if you want to buy it!**"
                    responses.append(msg)
                else:
                    error_msg = result.get("message", "Unknown error")
                    print(f"[ORCHESTRATOR] Deal agent failed: {error_msg}")
                    responses.append(f"I couldn't generate a custom deal at this time. ({error_msg})")       

            # --- ADD TO CART (With Recommender Integration) ---
            elif function_name == "add_to_cart":
                item_name = args.get("item_name")
                qty = int(args.get("quantity", 1))
                
                # STEP 1: Use RAG for semantic search to find the item
                rag_results = rag.search(item_name, k=3)
                
                # STEP 2: Extract actual item name from RAG results and use SearchAgent for exact DB lookup
                hits = []
                if rag_results:
                    # Parse RAG results to extract item names
                    for line in rag_results.split('\n'):
                        if line.startswith("Menu Item:") or line.startswith("Deal:"):
                            extracted_name = line.split(":", 1)[1].strip()
                            # Try to find exact match in SearchAgent
                            exact_hits = agent_search.search(extracted_name)
                            if exact_hits:
                                hits = exact_hits
                                break
                
                # STEP 3: Fallback to direct SearchAgent search
                if not hits:
                    hits = agent_search.search(item_name)
                    # Fuzzy match cleanup
                    if not hits and " " in item_name: 
                        hits = agent_search.search(item_name.replace(" ", ""))
                
                if hits:
                    item_data = hits[0]
                    
                    # Ensure proper type field
                    if "type" not in item_data or not item_data["type"]:
                        item_data["type"] = "menu_item"  # Default to menu_item if not specified
                    
                    # 1. Add item to cart (Cart Agent)
                    payload = {
                        'cart_id': st.session_state.cart_id, 
                        'item_data': item_data, 
                        'quantity': qty
                    }
                    result = send_task_and_get_response('cart', 'add_item', payload)
                    
                    # Base success message
                    final_msg = result.get('message', f"Added {item_name}.")
                    
                    # --- LOGIC CHANGE HERE: SMART TRIGGER CHECK ---
                    # Only trigger recommender if the item added is a MAIN course or a DEAL.
                    # We skip it for breads, drinks, starters, sides to avoid loops.
                    # Also skip if item is from a custom deal (to prevent recommending when custom deals are added)
                    
                    item_category = item_data.get('item_category', '').lower() if item_data.get('item_category') else ''
                    item_type = item_data.get('type', 'menu_item')  # 'deal' or 'menu_item', never None
                    from_custom_deal = item_data.get('from_custom_deal', False)  # Check if from custom deal

                    trigger_recommender = False
                    
                    # NEVER trigger recommender if we're adding custom deal items
                    if st.session_state.get('adding_custom_deal', False):
                        trigger_recommender = False
                    # Skip recommender if item is from a custom deal
                    elif from_custom_deal:
                         trigger_recommender = False
                    # If it's a deal (regular, not custom), SKIP recommender to avoid annoying users
                    elif item_type == 'deal':
                         trigger_recommender = False  # Changed from True to False
                    # If it's an individual item, only trigger for 'main' dishes
                    elif item_type == 'menu_item' and item_category == 'main':
                         trigger_recommender = True

                    if trigger_recommender:
                        # 2. GET RECOMMENDATION (Recommender Agent) 
                        # We need the current cart list to avoid duplicate suggestions
                        cart_summary = send_task_and_get_response('cart', 'get_cart_summary', {'cart_id': st.session_state.cart_id})
                        
                        current_items_list = []
                        if cart_summary.get('success') and 'items' in cart_summary:
                            current_items_list = [it['item_name'] for it in cart_summary['items']]
                        
                        # Ask the Recommender
                        rec_res = send_task_and_get_response(
                            'recommender', 
                            'get_recommendation', 
                            {
                                'last_item_name': item_data['item_name'], 
                                'current_cart_items': current_items_list
                            }
                        )
                        
                        if rec_res.get('success'):
                            rec_item = rec_res['recommended_item']
                            # Store recommendation in session state for follow-up
                            st.session_state.last_recommendation = rec_item
                            # Append the recommendation to the bot's response
                            final_msg += f"\n\n💡 **Suggestion:** Would you like to add **{rec_item}**? {rec_res['reason']}"
                    # --- END OF LOGIC CHANGE ---

                    responses.append(final_msg)
                    st.session_state.force_refresh = True
                else:
                    responses.append(f"I couldn't find '{item_name}' on the menu.")

            # --- REMOVE FROM CART ---
            elif function_name == "remove_from_cart":
                item_name = args.get("item_name")
                payload = {'cart_id': st.session_state.cart_id, 'item_name': item_name}
                result = send_task_and_get_response('cart', 'remove_item', payload)
                responses.append(result.get('message', "Item removed."))
                st.session_state.force_refresh = True

            # --- SHOW CART ---
            elif function_name == "show_cart":
                summary = send_task_and_get_response('cart', 'get_cart_summary', {'cart_id': st.session_state.cart_id})
                if summary.get('success') and not summary.get('is_empty'):
                    lines = [f"- {it['quantity']}x {it['item_name']} (Rs. {it['total_price']})" for it in summary['items']]
                    responses.append("Here is your cart:\n" + "\n".join(lines) + f"\n\n**Total: Rs. {summary['total_price']}**")
                else:
                    responses.append("Your cart is empty.")
                st.session_state.force_refresh = True

            # --- PLACE ORDER (UPDATED PIPELINE) ---
            elif function_name == "place_order":
                with st.spinner("Placing order..."):
                    flow_result = finalize_order_and_send_to_kitchen(st.session_state.cart_id)
                    
                    if flow_result.get('success'):
                        responses.append(flow_result.get('message'))
                        
                        # Reset
                        new_cart_id = str(uuid.uuid4())
                        st.session_state.cart_id = new_cart_id
                        send_task_and_get_response('cart', 'create_cart', {'user_id': new_cart_id})
                        st.session_state.force_refresh = True
                    else:
                        responses.append("I couldn't place the order. Your cart might be empty.")

        bot_response = "\n".join(responses)
    else:
        bot_response = ai_message.content

    conv_mgr.add_message("assistant", bot_response)

if st.session_state.get("force_refresh", False):
    st.session_state.force_refresh = False
    time.sleep(0.5)
    st.rerun()