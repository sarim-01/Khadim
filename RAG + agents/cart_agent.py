# Khadim Cart Agent - Simple and Clean Implementation
# This is the main cart agent that handles all cart operations

import uuid
import re
from typing import Dict, List, Optional, Any
from database_connection import DatabaseConnection
from psycopg2.extras import RealDictCursor
import json

class CartAgent:
    """
    Simple cart agent for Khadim restaurant system.
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
            order_summary JSONB  -- <-- ADD THIS LINE
        );
        
        -- The cart_items table definition remains unchanged
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
                
                    # --- ADD THE DEBUG LINES HERE ---
                    print("DEBUG: About to commit changes to the database.")
                    conn.commit()
                    print("DEBUG: Changes were committed successfully.")
            
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
                        # Remove by name (more user-friendly)
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
        Saves cart summary to the cart table, marks cart as inactive,
        and clears the items from the cart_items table.
        """
        try:
            # First, get the current contents of the cart.
            cart_summary = self.get_cart_summary(cart_id)
            
            if cart_summary['is_empty']:
                return {
                    'success': False,
                    'message': "Cannot place order - your cart is empty.",
                    'order_data': None
                }
            
            # Convert the summary dictionary to a JSON string to store in the DB.
            summary_json = json.dumps(cart_summary)
            
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    # 1. Update the cart table: set status and save the summary.
                    cur.execute("""
                        UPDATE cart 
                        SET status = 'inactive', 
                            order_summary = %s, 
                            updated_at = CURRENT_TIMESTAMP 
                        WHERE cart_id = %s
                    """, (summary_json, cart_id,))
                    
                    # 2. Delete the items from the active cart_items table.
                    cur.execute("""
                        DELETE FROM cart_items 
                        WHERE cart_id = %s
                    """, (cart_id,))
                    
                    conn.commit()
            
            return {
                'success': True,
                'message': f"Order placed successfully! Total was Rs. {cart_summary['total_price']:.2f}",
                'order_data': cart_summary
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f"Failed to place order: {str(e)}",
                'order_data': None
            }
    
    def process_user_input(self, cart_id: str, user_input: str, 
                          search_context: Dict = None) -> Dict:
        """
        Process natural language input and perform cart operations
        search_context: Contains selected item from search agent
        """
        user_input = user_input.lower().strip()
        
        # Add to cart patterns
        add_patterns = [
            r"add|put|i want|i'll have|i will have|give me|can i get|order",
            r"this|that|it"  # When referring to search results
        ]
        
        # Check if user wants to add items
        if any(re.search(pattern, user_input) for pattern in add_patterns):
            if search_context and 'selected_item' in search_context and search_context['selected_item']:
                quantity = self._extract_quantity(user_input)
                special_requests = self._extract_special_requests(user_input)
                return self.add_item(cart_id, search_context['selected_item'], 
                                   quantity, special_requests)
            else:
                return {
                    'success': False,
                    'message': "Please search for and select an item first, then I can add it to your cart.",
                    'cart_summary': None
                }
        
        # Remove from cart
        elif re.search(r"remove|delete|take out", user_input):
            item_name = self._extract_item_name(user_input, ["remove", "delete", "take", "out"])
            return self.remove_item(cart_id, item_name=item_name)
        
        # Show cart
        elif re.search(r"show|view|check|what.*in.*cart|my cart", user_input):
            return {
                'success': True,
                'message': "Here's your current cart:",
                'cart_summary': self.get_cart_summary(cart_id)
            }
        
        # Clear cart
        elif re.search(r"clear|empty|start new|new cart", user_input):
            return self.clear_cart(cart_id)
        
        # Place order
        elif re.search(r"place order|order|that's all|checkout|done|finish", user_input):
            return self.place_order(cart_id)
        
        else:
            return {
                'success': False,
                'message': "I can help you add items, remove items, view cart, or place order. What would you like to do?",
                'cart_summary': None
            }
    
    def _extract_quantity(self, text: str) -> int:
        """Extract quantity from user input"""
        # Look for numbers
        numbers = re.findall(r'\d+', text)
        if numbers:
            return int(numbers[0])
        
        # Look for text numbers
        text_numbers = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
        }
        
        for word, num in text_numbers.items():
            if word in text:
                return num
        
        return 1  # Default quantity
    
    def _extract_special_requests(self, text: str) -> Optional[str]:
        """Extract special requests from user input"""
        patterns = [
            r"with (.+)",
            r"no (.+)",
            r"extra (.+)",
            r"less (.+)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_item_name(self, text: str, exclude_words: List[str]) -> str:
        """Extract item name from text"""
        words = text.split()
        filtered_words = [word for word in words if word not in exclude_words + ['from', 'the', 'my', 'cart']]
        return ' '.join(filtered_words)

# Example usage for testing
if __name__ == "__main__":
    cart = CartAgent()
    cart_id = "test_user_123"
    
    # Test adding item
    sample_item = {
        'item_id': 1,
        'item_name': 'Chicken Burger',
        'price': 15.99
    }
    
    result = cart.add_item(cart_id, sample_item, 2)
    print(f"Add result: {result['message']}")
    
    # Test cart summary
    summary = cart.get_cart_summary(cart_id)
    print(f"Cart total: Rs. {summary['total_price']:.2f}")