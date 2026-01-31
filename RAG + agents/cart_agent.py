# cart_agent.py
import json
import uuid
from typing import Dict, List, Optional
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Import your project utilities
from database_connection import DatabaseConnection
from redis_connection import RedisConnection
from config import AGENT_TASKS_CHANNEL

load_dotenv()

class CartTools:
    """
    This class holds the 'Tools' (Functions) for the Cart Agent.
    Instead of using @tool (which is for AI), we define them as class methods 
    backed by the Database.
    """
    
    def __init__(self):
        self.db = DatabaseConnection.get_instance()
        self._init_tables()
    
    def _init_tables(self):
        """Initialize cart tables in Postgres"""
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS cart (
                        cart_id UUID PRIMARY KEY,
                        status TEXT DEFAULT 'active',
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS cart_items (
                        cart_id UUID REFERENCES cart(cart_id) ON DELETE CASCADE,
                        item_id INTEGER,
                        item_type TEXT, 
                        item_name TEXT,
                        quantity INTEGER,
                        unit_price DECIMAL(10,2),
                        PRIMARY KEY (cart_id, item_id, item_type)
                    );
                """)
                conn.commit()

    # --- THE TOOLS ---

    def create_cart(self, user_id: str) -> Dict:
        """Creates a new cart session in the DB."""
        cart_id = user_id or str(uuid.uuid4())
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO cart (cart_id) VALUES (%s) ON CONFLICT (cart_id) DO NOTHING",
                    (cart_id,)
                )
                conn.commit()
        return {'success': True, 'cart_id': cart_id, 'message': "Cart created"}

    def add_item(self, cart_id: str, item_data: Dict, quantity: int = 1) -> Dict:
        """Adds an item to the database."""
        try:
            self.create_cart(cart_id) # Ensure cart exists
            
            # Extract data provided by Orchestrator
            is_deal = 'deal_id' in item_data
            item_id = item_data.get('deal_id') if is_deal else item_data.get('item_id')
            item_type = 'deal' if is_deal else 'menu_item'
            item_name = item_data.get('item_name')
            price = item_data.get('price')

            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    # Upsert: Update quantity if exists, otherwise Insert
                    cur.execute("""
                        INSERT INTO cart_items 
                        (cart_id, item_id, item_type, item_name, quantity, unit_price)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (cart_id, item_id, item_type) 
                        DO UPDATE SET quantity = cart_items.quantity + %s
                    """, (cart_id, item_id, item_type, item_name, quantity, price, quantity))
                    conn.commit()
            
            return {'success': True, 'message': f"Added {quantity}x {item_name} to cart"}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def remove_item(self, cart_id: str, item_name: str) -> Dict:
        """Removes an item from the database."""
        rows_deleted = 0
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM cart_items 
                    WHERE cart_id = %s AND item_name ILIKE %s
                """, (cart_id, f"%{item_name}%"))
                rows_deleted = cur.rowcount
                conn.commit()
        
        if rows_deleted > 0:
            return {'success': True, 'message': f"Removed {item_name}"}
        else:
            return {'success': False, 'message': f"Item '{item_name}' not found in your cart."}

    def get_cart_summary(self, cart_id: str) -> Dict:
        """Returns the cart JSON summary."""
        with self.db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM cart_items WHERE cart_id = %s", (cart_id,))
                items = cur.fetchall()
                
                formatted = []
                total = 0.0
                for i in items:
                    t_price = float(i['quantity']) * float(i['unit_price'])
                    total += t_price
                    formatted.append({
                        "item_name": i['item_name'],
                        "quantity": i['quantity'],
                        "unit_price": float(i['unit_price']),
                        "total_price": t_price,
                        "item_id": i['item_id'], 
                        "item_type": i['item_type']
                    })
                
                return {
                    "success": True, 
                    "items": formatted, 
                    "total_price": total,
                    "is_empty": len(items) == 0
                }

    def place_order(self, cart_id: str) -> Dict:
        """Finalizes the cart."""
        summary = self.get_cart_summary(cart_id)
        if summary['is_empty']:
            return {'success': False, 'message': "Cart is empty"}
            
        # Clear the cart items in DB
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM cart_items WHERE cart_id = %s", (cart_id,))
                cur.execute("UPDATE cart SET status = 'inactive' WHERE cart_id = %s", (cart_id,))
                conn.commit()
        
        return {
            'success': True, 
            'message': "Order placed", 
            'order_data': summary # Send this data to Order Agent
        }


# --- MAIN LISTENER LOOP (No LLM needed here!) ---

def run_cart_agent():
    print("🛒 Cart Agent (Database Backed) is running...")
    
    # Initialize our Tools class
    tools = CartTools()
    
    # Connect to Redis
    redis_conn = RedisConnection.get_instance()
    pubsub = redis_conn.pubsub()
    pubsub.subscribe(AGENT_TASKS_CHANNEL)

    for message in pubsub.listen():
        if message['type'] == 'message':
            try:
                data = json.loads(message['data'])
                
                # 1. Check if the task is for US
                if data.get('agent') != 'cart':
                    continue

                command = data.get('command')
                payload = data.get('payload', {})
                response_channel = data.get('response_channel')
                
                print(f"📥 Received Command: {command}")

                # 2. Map the Command String to the Class Method (The "Tool")
                result = {}
                
                if command == 'create_cart':
                    result = tools.create_cart(payload.get('user_id'))
                
                elif command == 'add_item':
                    # Ensure args match Orchestrator payload
                    result = tools.add_item(
                        payload.get('cart_id'),
                        payload.get('item_data'),
                        payload.get('quantity', 1)
                    )
                
                elif command == 'remove_item':
                    result = tools.remove_item(
                        payload.get('cart_id'), 
                        payload.get('item_name')
                    )
                
                elif command == 'get_cart_summary':
                    result = tools.get_cart_summary(payload.get('cart_id'))
                
                elif command == 'place_order':
                    result = tools.place_order(payload.get('cart_id'))
                
                else:
                    result = {'success': False, 'message': f"Unknown tool: {command}"}

                # 3. Send Result Back
                if response_channel:
                    redis_conn.publish(response_channel, json.dumps(result))

            except Exception as e:
                print(f"❌ Error in Cart Agent: {e}")

if __name__ == "__main__":
    from agent_lifecycle_manager import wrap_agent
    wrap_agent("cart", run_cart_agent)