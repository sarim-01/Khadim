# app.py

import os
import uuid
import re
import json
import streamlit as st
from dotenv import load_dotenv

from search_agent import load_texts
from conversation_manager import ConversationManager
from cart_agent import CartAgent
from database_connection import DatabaseConnection
from chat_agent import get_ai_response 
from rag_retriever import RAGRetriever

load_dotenv()

# This simple keyword search is still useful for precise lookups after a tool is called.
class SearchAgent:
    def __init__(self):
        self.blocks = load_texts()
    def search(self, term: str):
        term_lower = term.lower()
        hits = []
        for block in self.blocks:
            if term_lower in block.lower():
                lines = block.splitlines()
                entry = {"raw": block}
                name_line = lines[0]
                if "Menu Item:" in name_line:
                    entry["type"] = "menu_item"
                    entry["item_name"] = name_line.split(":", 1)[1].strip()
                    entry["item_id"] = abs(hash(entry["item_name"])) % 1000
                elif "Deal:" in name_line:
                    entry["type"] = "deal"
                    entry["item_name"] = name_line.split(":", 1)[1].strip()
                    entry["deal_id"] = abs(hash(entry["item_name"])) % 1000
                price = 0.0
                for ln in lines:
                    if ln.lower().startswith("price:"):
                        try:
                            price = float(ln.split(":", 1)[1].strip())
                        except: pass
                        break
                entry["price"] = price
                hits.append(entry)
        return hits
    def get_context_blocks(self):
        return "\n\n---\n\n".join(self.blocks)

# --- Streamlit App ---
st.set_page_config(page_title="Khadim Bot", page_icon="🍽️")
st.title("🍴 Khadim Restaurant Chatbot")

# Initialize session state
if "initialized" not in st.session_state:
    st.session_state.conv_mgr = ConversationManager(max_history=10)
    st.session_state.search_agent = SearchAgent() # For precise tool lookups
    st.session_state.cart_agent = CartAgent()
    st.session_state.rag_retriever = RAGRetriever() # For fast conversational search
    st.session_state.cart_id = str(uuid.uuid4())
    db = DatabaseConnection.get_instance()
    st.session_state.db_ok = db.test_connection()
    st.session_state.initialized = True

if not st.session_state.db_ok:
    st.error("🚨 Database connection failed.")
    st.stop()

# Sidebar
with st.sidebar:
    st.header("🛒 Cart")
    summary = st.session_state.cart_agent.get_cart_summary(cart_id=st.session_state.cart_id)
    if summary.get("is_empty", True):
        st.write("Your cart is empty")
    else:
        for item in summary["items"]:
            st.write(f"{item['quantity']}× {item['item_name']} @ Rs. {item['unit_price']:.2f} = Rs. {item['total_price']:.2f}")
        st.markdown(f"**Total:** Rs. {summary['total_price']:.2f}")
        if st.button("Place Order"):
            cart = st.session_state.cart_agent
            result = cart.place_order(st.session_state.cart_id)
            st.success(result['message'])
            if result.get('success'):
                new_cart_id = str(uuid.uuid4())
                st.session_state.cart_id = new_cart_id
                cart.create_cart(new_cart_id)
            st.rerun()

# Main chat interface
st.markdown("---")
st.header("💬 Conversation")
for msg in st.session_state.conv_mgr.get_history():
    st.markdown(f"**{msg['role'].title()}:** {msg['content']}")

with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_input("Your message", "")
    submitted = st.form_submit_button("Send")

# --- RAG-POWERED ORCHESTRATOR LOGIC ---
if submitted and user_input:
    conv_mgr = st.session_state.conv_mgr
    agent = st.session_state.search_agent
    cart = st.session_state.cart_agent
    rag = st.session_state.rag_retriever
    
    conv_mgr.add_message("user", user_input)
    
    # First, perform a RAG search to find the most relevant context for the LLM
    relevant_context = rag.search(user_input)
    
    # Now, get the AI response using only that small, relevant context
    ai_message = get_ai_response(user_input, conv_mgr.get_history(), relevant_context)
    
    bot_response = ""
    
    # Check if the AI wants to use a tool
    if ai_message.tool_calls:
        tool_call = ai_message.tool_calls[0]
        function_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)
        
        # Execute the correct tool (function)
        if function_name == "add_to_cart":
            item_name = args.get("item_name")
            quantity = args.get("quantity", 1)
            hits = agent.search(item_name) # Use simple keyword search for precise lookup
            if hits:
                item_data = hits[0]
                result = cart.add_item(st.session_state.cart_id, item_data, quantity)
                bot_response = result['message']
            else:
                bot_response = f"I'm sorry, I couldn't find '{item_name}' on the menu."

        elif function_name == "remove_from_cart":
            item_name = args.get("item_name")
            result = cart.remove_item(st.session_state.cart_id, item_name=item_name)
            bot_response = result['message']
            
        elif function_name == "show_cart":
            summary = cart.get_cart_summary(st.session_state.cart_id)
            if summary['is_empty']:
                bot_response = "Your cart is currently empty."
            else:
                bot_response = "Here are the items in your cart:\n"
                for it in summary["items"]:
                    bot_response += f"- {it['quantity']}× {it['item_name']} @ Rs. {it['unit_price']:.2f}\n"
                bot_response += f"**Total: Rs. {summary['total_price']:.2f}**"
        
        elif function_name == "place_order":
            result = cart.place_order(st.session_state.cart_id)
            bot_response = result['message']
            if result.get('success'):
                new_cart_id = str(uuid.uuid4())
                st.session_state.cart_id = new_cart_id
                cart.create_cart(new_cart_id)
                bot_response += "\n\nI've started a new empty cart for you."
    
    else:
        # If no tool was called, it's a conversational response from the RAG context
        bot_response = ai_message.content

    conv_mgr.add_message("assistant", bot_response)
    st.rerun()