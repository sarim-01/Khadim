import uuid
import re
from typing import Dict, List, Optional, Any
from database_connection import DatabaseConnection
from psycopg2.extras import RealDictCursor
import json
from redis_connection import RedisConnection
from config import AGENT_TASKS_CHANNEL

class CartAgent:
    """
    Cart agent for Khadim
    Handles: add items, remove items, view cart, clear cart, and place order.
    """
    
    def __init__(self):
        self.db = DatabaseConnection.get_instance()
        self._init_tables()
    
    def _init_tables(self):
        """Initialize cart tables if they don't exist"""
        schema = """
        CREATE TABLE IF NOT EXISTS cart (
            cart_id UUID PRIMARY KEY,
            status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            order_summary JSONB
        );
        
        CREATE TABLE IF NOT EXISTS cart_items (
            cart_id UUID REFERENCES cart(cart_id) ON DELETE CASCADE,
            item_id INTEGER NOT NULL,
            item_type TEXT CHECK (item_type IN ('menu_item', 'deal')),
            item_name TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            unit_price DECIMAL(10,2) NOT NULL,
            special_requests TEXT,
            PRIMARY KEY (cart_id, item_id, item_type)
        );
        """
        
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(schema)
                conn.commit()
    
    def create_cart(self, user_id: str = None) -> str:
        """Create new active cart"""
        cart_id = user_id or str(uuid.uuid4())
        
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO cart (cart_id) VALUES (%s) ON CONFLICT (cart_id) DO NOTHING",
                    (cart_id,)
                )
                conn.commit()
        
        return cart_id
    
    def add_item(self, cart_id: str, item_data: Dict, quantity: int = 1, 
                 special_requests: str = None) -> Dict:
        """
        Add item to cart
        item_data should contain: item_id, item_name, price, and optionally deal_id
        """
        try:
            # Ensure cart exists
            self.create_cart(cart_id)
            
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Determine item type and ID
                    item_type = 'deal' if 'deal_id' in item_data else 'menu_item'
                    item_id = item_data.get('deal_id', item_data.get('item_id'))
                    
                    # Check if item already exists
                    cur.execute("""
                        SELECT quantity FROM cart_items 
                        WHERE cart_id = %s AND item_id = %s AND item_type = %s
                    """, (cart_id, item_id, item_type))
                    
                    existing = cur.fetchone()
                    
                    if existing:
                        # Update existing item
                        new_quantity = existing['quantity'] + quantity
                        cur.execute("""
                            UPDATE cart_items 
                            SET quantity = %s, special_requests = %s
                            WHERE cart_id = %s AND item_id = %s AND item_type = %s
                        """, (new_quantity, special_requests, cart_id, item_id, item_type))
                        message = f"Updated {item_data['item_name']} quantity to {new_quantity}"
                    else:
                        # Add new item
                        cur.execute("""
                            INSERT INTO cart_items 
                            (cart_id, item_id, item_type, item_name, quantity, unit_price, special_requests)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (cart_id, item_id, item_type, item_data['item_name'], 
                              quantity, item_data['price'], special_requests))
                        message = f"Added {quantity}x {item_data['item_name']} to cart"
                    
                    # Update cart timestamp
                    cur.execute(
                        "UPDATE cart SET updated_at = CURRENT_TIMESTAMP WHERE cart_id = %s",
                        (cart_id,)
                    )
                
                    conn.commit()
            
            return {
                'success': True,
                'message': message,
                'cart_summary': self.get_cart_summary(cart_id)
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f"Failed to add item: {str(e)}",
                'cart_summary': None
            }
    
    def remove_item(self, cart_id: str, item_name: str = None, 
                    item_id: int = None, item_type: str = None) -> Dict:
        """Remove item from cart"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    if item_name:
                        # Remove by name 
                        cur.execute("""
                            DELETE FROM cart_items 
                            WHERE cart_id = %s AND item_name ILIKE %s
                        """, (cart_id, f"%{item_name}%"))
                    else:
                        # Remove by ID and type
                        cur.execute("""
                            DELETE FROM cart_items 
                            WHERE cart_id = %s AND item_id = %s AND item_type = %s
                        """, (cart_id, item_id, item_type))
                    
                    rows_affected = cur.rowcount
                    conn.commit()
            
            if rows_affected > 0:
                message = f"Removed {item_name or 'item'} from cart"
            else:
                message = "Item not found in cart"
            
            return {
                'success': True,
                'message': message,
                'cart_summary': self.get_cart_summary(cart_id)
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f"Failed to remove item: {str(e)}",
                'cart_summary': None
            }
    
    def get_cart_summary(self, cart_id: str) -> Dict:
        """Get complete cart summary"""
        with self.db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM cart_items 
                    WHERE cart_id = %s
                    ORDER BY item_name
                """, (cart_id,))
                
                items = []
                total_price = 0
                
                for row in cur.fetchall():
                    item_total = float(row['quantity'] * row['unit_price'])
                    total_price += item_total
                    
                    items.append({
                        'item_id': row['item_id'],
                        'item_type': row['item_type'],
                        'item_name': row['item_name'],
                        'quantity': row['quantity'],
                        'unit_price': float(row['unit_price']),
                        'total_price': item_total,
                        'special_requests': row['special_requests']
                    })
        
        return {
            'cart_id': cart_id,
            'items': items,
            'total_items': sum(item['quantity'] for item in items),
            'total_price': total_price,
            'is_empty': len(items) == 0
        }
    
    def clear_cart(self, cart_id: str) -> Dict:
        """Clear all items from cart"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM cart_items WHERE cart_id = %s", (cart_id,))
                    conn.commit()
            
            return {
                'success': True,
                'message': "Cart cleared successfully",
                'cart_summary': self.get_cart_summary(cart_id)
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f"Failed to clear cart: {str(e)}",
                'cart_summary': None
            }
    
    def place_order(self, cart_id: str) -> Dict:
        """
        Marks the cart as inactive and clears the items from cart_items table.
        """
        try:
            cart_summary = self.get_cart_summary(cart_id)
            
            if cart_summary['is_empty']:
                return {
                    'success': False,
                    'message': "Cannot place order - your cart is empty.",
                    'order_data': None
                }
            
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    # 1. Mark the cart as inactive
                    cur.execute("""
                        UPDATE cart 
                        SET status = 'inactive', 
                            updated_at = CURRENT_TIMESTAMP 
                        WHERE cart_id = %s
                    """, (cart_id,))
                    
                    # 2. Delete the items from the active cart_items table.
                    cur.execute("""
                        DELETE FROM cart_items 
                        WHERE cart_id = %s
                    """, (cart_id,))
                    
                    conn.commit()
            
            return {
                'success': True,
                'message': "Cart successfully converted to an order.",
                'order_data': cart_summary # Pass data to the OrderAgent
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f"Cart Agent failed to finalize cart: {str(e)}",
                'order_data': None
            }

    def _extract_quantity(self, text: str) -> int:
        """Extract quantity from user input"""
        numbers = re.findall(r'\d+', text)
        if numbers: return int(numbers[0])
        text_numbers = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5}
        for word, num in text_numbers.items():
            if word in text: return num
        return 1

    def _extract_special_requests(self, text: str) -> Optional[str]:
        """Extract special requests from user input"""
        patterns = [r"with (.+)", r"no (.+)", r"extra (.+)", r"less (.+)"]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match: return match.group(1).strip()
        return None

    def _extract_item_name(self, text: str, exclude_words: List[str]) -> str:
        """Extract item name from text"""
        words = text.split()
        filtered_words = [word for word in words if word not in exclude_words + ['from', 'the', 'my', 'cart']]
        return ' '.join(filtered_words)


# --- NEW AGENT LISTENER SECTION ---

def run_cart_agent():
    print("🛒 Cart Agent is running and listening for tasks...")
    
    # Instantiate the agent's logic
    cart_agent_logic = CartAgent()
    
    # Get Redis connection
    redis_conn = RedisConnection.get_instance()
    if not redis_conn:
        print("FATAL: Could not connect to Redis. Cart Agent shutting down.")
        return
        
    # Subscribe to the channel where tasks are published
    pubsub = redis_conn.pubsub()
    pubsub.subscribe(AGENT_TASKS_CHANNEL)
    
    for message in pubsub.listen():
        if message['type'] == 'message':
            try:
                # Decode the message data from JSON
                task_data = json.loads(message['data'])
                
                # Check if the task is for this agent
                if task_data.get('agent') == 'cart':
                    command = task_data.get('command')
                    payload = task_data.get('payload', {})
                    response_channel = task_data.get('response_channel')
                    
                    print(f"Cart Agent: Received command '{command}'")
                    
                    result = {}
                    # Execute the command by calling the class method
                    if command == 'add_item':
                        result = cart_agent_logic.add_item(**payload)
                    elif command == 'remove_item':
                        result = cart_agent_logic.remove_item(**payload)
                    elif command == 'get_cart_summary':
                        result = cart_agent_logic.get_cart_summary(**payload)
                    elif command == 'clear_cart':
                        result = cart_agent_logic.clear_cart(**payload)
                    elif command == 'place_order':
                        result = cart_agent_logic.place_order(**payload)
                    elif command == 'create_cart':
                        cart_id = cart_agent_logic.create_cart(**payload)
                        result = {'success': True, 'cart_id': cart_id}
                    else:
                        result = {'success': False, 'message': f"Unknown command: {command}"}
                        
                    # Publish the result back to the orchestrator's private channel
                    if response_channel:
                        print(f"🟢 Cart Agent publishing response to {response_channel}")
                        redis_conn.publish(response_channel, json.dumps(result))
                        
            except json.JSONDecodeError:
                print("Cart Agent: Error decoding JSON message.")
            except Exception as e:
                print(f"Cart Agent: An error occurred: {e}")


if __name__ == "__main__":
    run_cart_agent()