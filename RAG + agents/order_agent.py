# order_agent.py

from database_connection import DatabaseConnection
from typing import Dict
import json
from redis_connection import RedisConnection
from config import AGENT_TASKS_CHANNEL

class OrderAgent:
    """Handles final order processing, summary, and order history saving."""
    
    def __init__(self):
        self.db = DatabaseConnection.get_instance()
        self._init_tables() # Add table init

    def _init_tables(self):
        """Creates the 'orders' table if it doesn't exist."""
        schema = """
        CREATE TABLE IF NOT EXISTS orders (
            order_id SERIAL PRIMARY KEY,
            cart_id UUID NOT NULL,
            total_price DECIMAL(10, 2) NOT NULL,
            estimated_prep_time_minutes INT,
            order_data JSONB,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(schema)
                    conn.commit()
            print("OrderAgent: 'orders' table checked/created.")
        except Exception as e:
            print(f"OrderAgent: FATAL: Could not create 'orders' table: {e}")

    def _calculate_total_prep_time(self, cart_summary: Dict) -> int:
        """
        Calculates a realistic prep time by finding the longest prep time
        among all items and deals in the cart.
        """
        max_prep_time = 0
        
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                for item in cart_summary.get('items', []):
                    item_prep_time = 0
                    if item['item_type'] == 'menu_item':
                        # Fetch prep time for a single menu item
                        cur.execute(
                            "SELECT prep_time_minutes FROM menu_item WHERE item_id = %s",
                            (item['item_id'],)
                        )
                        result = cur.fetchone()
                        if result and result[0] is not None:
                            item_prep_time = result[0]
                            
                    elif item['item_type'] == 'deal':
                        # For a deal, find the max prep time among its component items
                        cur.execute("""
                            SELECT MAX(mi.prep_time_minutes) 
                            FROM deal_item di
                            JOIN menu_item mi ON di.menu_item_id = mi.item_id
                            WHERE di.deal_id = %s
                        """, (item['item_id'],))
                        result = cur.fetchone()
                        if result and result[0] is not None:
                            item_prep_time = result[0]
                    
                    # Update the overall max prep time for the order
                    if item_prep_time > max_prep_time:
                        max_prep_time = item_prep_time
                        
        return max_prep_time if max_prep_time > 0 else 15 # Default if no times found

    def save_and_summarize_order(self, cart_id: str, cart_summary: Dict) -> Dict:
        """
        Saves the final order to the 'orders' table and prepares a confirmation summary.
        """
        
        total_price = cart_summary['total_price']
        # Use the new dynamic calculation instead of a hard-coded value
        estimated_prep_time = self._calculate_total_prep_time(cart_summary)
        
        try:
            order_data_json = json.dumps(cart_summary)
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO orders 
                        (cart_id, total_price, estimated_prep_time_minutes, order_data)
                        VALUES (%s, %s, %s, %s)
                        RETURNING order_id
                    """, (cart_id, total_price, estimated_prep_time, order_data_json))
                    
                    order_id = cur.fetchone()[0]
                    conn.commit()
            
            # Prepare a more detailed confirmation summary
            summary_message = (
                f"✅ Your order (ID: {order_id}) has been successfully placed!\n\n"
                f"**Total:** Rs. {total_price:.2f}\n\n"
                f"**Estimated waiting time:** Approximately {estimated_prep_time} minutes."
            )
            
            return {
                'success': True,
                'message': summary_message,
                'order_id': order_id,
                'prep_time': estimated_prep_time
            }

        except Exception as e:
            return {
                'success': False,
                'message': f"Order Confirmation Agent failed to save the order: {str(e)}",
                'order_id': None,
                'prep_time': None
            }

# --- NEW AGENT LISTENER SECTION ---

def run_order_agent():
    """
    Main loop for the Order Agent.
    Subscribes to the 'agent_tasks' channel and listens for work.
    """
    print("📦 Order Agent is running and listening for tasks...")
    
    # Instantiate the agent's logic
    order_agent_logic = OrderAgent()
    
    # Get Redis connection
    redis_conn = RedisConnection.get_instance()
    if not redis_conn:
        print("FATAL: Could not connect to Redis. Order Agent shutting down.")
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
                if task_data.get('agent') == 'order':
                    command = task_data.get('command')
                    payload = task_data.get('payload', {})
                    response_channel = task_data.get('response_channel')
                    
                    print(f"Order Agent: Received command '{command}'")
                    
                    result = {}
                    # Execute the command
                    if command == 'save_and_summarize_order':
                        result = order_agent_logic.save_and_summarize_order(**payload)
                    else:
                        result = {'success': False, 'message': f"Unknown command: {command}"}
                        
                    # Publish the result back
                    if response_channel:
                        redis_conn.publish(response_channel, json.dumps(result))
                        
            except json.JSONDecodeError:
                print("Order Agent: Error decoding JSON message.")
            except Exception as e:
                print(f"Order Agent: An error occurred: {e}")

# This starts the listener
if __name__ == "__main__":
    from agent_lifecycle_manager import wrap_agent
    wrap_agent("order", run_order_agent)