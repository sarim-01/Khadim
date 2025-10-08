import streamlit as st
from extract import load_texts
from vector_store import build_index, query_index
from chat_agent import ask_bot, SYSTEM_PROMPT
from conversation_manager import ConversationManager
from postgres_cart_manager import PostgresCartManager
from database_utils import MenuDatabase
from cart_parser import CartCommandParser
from database_connection import DatabaseConnection

# Load all formatted text blocks (menu items + deals)
all_texts = load_texts()

# Build or cache index
@st.cache_resource
def get_index():
    return build_index(all_texts)

# Initialize all required components in session state
if 'conversation_manager' not in st.session_state:
    st.session_state.conversation_manager = ConversationManager(max_history=6)
if 'menu_db' not in st.session_state:
    st.session_state.menu_db = MenuDatabase()
if 'cart_manager' not in st.session_state:
    st.session_state.cart_manager = PostgresCartManager()
if 'user_cart_id' not in st.session_state:
    st.session_state.user_cart_id = st.session_state.cart_manager.create_cart()

index = get_index()

st.title("🍽️ AI Restaurant Waiter")

# Display conversation history
for message in st.session_state.conversation_manager.get_history():
    role = "You" if message["role"] == "user" else "Waiter"
    st.markdown(f"**{role}:** {message['content']}")

# Input and button
query = st.text_input("Ask your waiter:")

# Add a cart summary sidebar
with st.sidebar:
    st.subheader("Your Cart 🛒")
    cart_summary = st.session_state.cart_manager.get_cart_summary(st.session_state.user_cart_id)
    
    if cart_summary and cart_summary['items']:
        for item in cart_summary['items']:
            # Show price per item and subtotal
            st.write(f"• {item['quantity']}x {item['item_name']}")
            st.write(f"  Rs. {item['price']} each (Rs. {item['total']})")
            if item['special_requests']:
                st.write(f"  Note: {item['special_requests']}")
        st.write("---")
        st.write(f"Total Items: {cart_summary['total_items']}")
        st.write(f"Total: Rs. {cart_summary['total_price']:.2f}")
    else:
        st.write("Your cart is empty")

if st.button("Send") and query:
    # Add user message to history
    st.session_state.conversation_manager.add_message("user", query)
    
    with st.spinner("Thinking..."):
        contexts = query_index(index, all_texts, query, k=6)
        answer = ask_bot(contexts, query, st.session_state.conversation_manager.get_history())
        
        # Process cart-related commands using the parser
        cart_command = CartCommandParser.parse_command(query)
        
        if cart_command["command"] == "add":
            item_name = cart_command["item_name"]
            quantity = cart_command["quantity"]
            
            # Validate and get item details from database
            item_details = st.session_state.menu_db.get_item_details(item_name)
            
            if item_details:
                try:
                    item_data = {
                        "item_id": int(item_details["item_id"]),
                        "item_name": item_details["item_name"],
                        "price": float(item_details["item_price"])
                    }
                    
                    # Check for special requests in the query
                    special_requests = cart_command.get('special_requests')
                    
                    cart_result = st.session_state.cart_manager.add_item(
                        st.session_state.user_cart_id,
                        item_data,
                        quantity=quantity,
                        special_requests=special_requests
                    )
                    
                    # Force Streamlit to update the sidebar
                    if cart_result['success']:
                        st.sidebar.empty()
                        st.experimental_rerun()
                except Exception as e:
                    st.error(f"Error adding item to cart: {str(e)}")
                    cart_result = {
                        'success': False,
                        'message': str(e)
                    }
                
                if cart_result['success']:
                    answer += f"\n\nI've added {quantity}x {item_details['item_name']} (Rs. {item_details['item_price']} each) to your cart."
                    answer += f"\nQuantity/Serving Size: {item_details['quantity_description']}"
            else:
                # Item not found - suggest similar items
                similar_items = st.session_state.menu_db.get_similar_items(item_name)
                if similar_items:
                    answer += f"\n\nI couldn't find exactly '{item_name}'. Did you mean one of these?\n"
                    answer += "\n".join([f"- {item}" for item in similar_items])
                else:
                    answer += f"\n\nI'm sorry, I couldn't find '{item_name}' in our menu."

        elif cart_command["command"] == "clear":
            try:
                cart_result = st.session_state.cart_manager.clear_cart(st.session_state.user_cart_id)
                if cart_result['success']:
                    answer += "\n\nI've cleared your cart. You can start a fresh order now."
                else:
                    answer += f"\n\nI'm sorry, I couldn't clear your cart: {cart_result['message']}"
            except Exception as e:
                st.error(f"Error clearing cart: {str(e)}")
                answer += "\n\nI'm sorry, there was an error clearing your cart. Please try again."
                    
        elif cart_command["command"] == "remove":
            item_name = cart_command["item_name"]
            # Get item details to find its ID
            item_details = st.session_state.menu_db.get_item_details(item_name)
            if item_details:
                cart_result = st.session_state.cart_manager.update_quantity(
                    st.session_state.user_cart_id,
                    item_details['item_id'],
                    'menu_item',
                    0  # Set quantity to 0 to remove
                )
            if cart_result['success']:
                answer += f"\n\nI've removed {item_name} from your cart."
                
        elif cart_command["command"] == "show":
            cart_summary = st.session_state.cart_manager.get_cart_summary(st.session_state.user_cart_id)
            if cart_summary and cart_summary.get('items', []):
                answer += "\n\nHere's what's in your cart:\n"
                for item in cart_summary['items']:
                    answer += f"- {item['quantity']}x {item['item_name']} (Rs. {item['price'] * item['quantity']})\n"
                answer += f"\nTotal: Rs. {cart_summary['total_price']:.2f}"
            else:
                answer += "\n\nYour cart is currently empty."
    
    # Add assistant's response to history
    st.session_state.conversation_manager.add_message("assistant", answer)
    
    # Rerun to update the display
    st.rerun()
