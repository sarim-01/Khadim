from typing import Dict, Optional, List
import uuid
from datetime import datetime
from database_connection import DatabaseConnection
from psycopg2.extras import RealDictCursor

class PostgresCartManager:
    def __init__(self):
        self.db = DatabaseConnection.get_instance()
        self._initialize_db()

    def _initialize_db(self):
        """Initialize cart tables if they don't exist"""
        with open('database/cart_tables.sql', 'r') as f:
            schema = f.read()
            
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(schema)
            conn.commit()

    def create_cart(self) -> str:
        """Create a new cart and return its ID"""
        cart_id = str(uuid.uuid4())
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO cart (cart_id) VALUES (%s) RETURNING cart_id",
                    (cart_id,)
                )
                conn.commit()
                return cart_id

    def add_item(self, cart_id: str, item_data: Dict, quantity: int = 1,
                 special_requests: Optional[str] = None) -> Dict:
        """Add or update item in cart"""
        print(f"\nTrying to add item to cart:")
        print(f"Cart ID: {cart_id}")
        print(f"Item Data: {item_data}")
        print(f"Quantity: {quantity}")
        print(f"Special Requests: {special_requests}")
        
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Determine item type
                    item_type = 'deal' if 'deal_id' in item_data else 'menu_item'
                    item_id = item_data.get('deal_id' if item_type == 'deal' else 'item_id')
                    
                    print(f"Item Type: {item_type}")
                    print(f"Item ID: {item_id}")
                    
                    # Check if item exists in cart
                    cur.execute("""
                        SELECT quantity 
                        FROM cart_items 
                        WHERE cart_id = %s AND item_id = %s AND item_type = %s
                    """, (cart_id, item_id, item_type))
                    existing = cur.fetchone()
                    
                    print(f"Existing item in cart: {existing}")
                    
                    try:
                        if existing:
                            # Update existing item
                            new_quantity = existing['quantity'] + quantity
                            print(f"Updating quantity to: {new_quantity}")
                            cur.execute("""
                                UPDATE cart_items 
                                SET quantity = %s, 
                                    special_requests = %s,
                                    unit_price = %s
                                WHERE cart_id = %s AND item_id = %s AND item_type = %s
                            """, (new_quantity, special_requests, item_data['price'],
                                 cart_id, item_id, item_type))
                        else:
                            # Add new item
                            print("Inserting new item")
                            cur.execute("""
                                INSERT INTO cart_items 
                                    (cart_id, item_id, item_type, quantity, 
                                     unit_price, special_requests)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                RETURNING cart_id, item_id
                            """, (cart_id, item_id, item_type, quantity,
                                 item_data['price'], special_requests))
                            result = cur.fetchone()
                            print(f"Insert result: {result}")
                        
                        conn.commit()
                        print("Transaction committed successfully")
                        
                        # Verify the item was added
                        cur.execute("""
                            SELECT * FROM cart_items 
                            WHERE cart_id = %s AND item_id = %s AND item_type = %s
                        """, (cart_id, item_id, item_type))
                        verification = cur.fetchone()
                        print(f"Verification after commit: {verification}")
                        
                        return {
                            'success': True,
                            'message': f"Added {quantity}x {item_data['item_name']} to cart",
                            'cart_summary': self.get_cart_summary(cart_id)
                        }
                    except Exception as e:
                        print(f"Database error: {str(e)}")
                        conn.rollback()
                        raise
                    
        except Exception as e:
            return {
                'success': False,
                'message': f"Error adding item to cart: {str(e)}",
                'cart_summary': None
            }

    def update_quantity(self, cart_id: str, item_id: int, 
                       item_type: str, new_quantity: int) -> Dict:
        """Update item quantity in cart"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    if new_quantity > 0:
                        cur.execute("""
                            UPDATE cart_items 
                            SET quantity = %s
                            WHERE cart_id = %s AND item_id = %s AND item_type = %s
                        """, (new_quantity, cart_id, item_id, item_type))
                    else:
                        # Remove item if quantity is 0
                        cur.execute("""
                            DELETE FROM cart_items 
                            WHERE cart_id = %s AND item_id = %s AND item_type = %s
                        """, (cart_id, item_id, item_type))
                    
                    conn.commit()
                    
                    return {
                        'success': True,
                        'message': f"Updated quantity to {new_quantity}",
                        'cart_summary': self.get_cart_summary(cart_id)
                    }
        except Exception as e:
            return {
                'success': False,
                'message': f"Error updating quantity: {str(e)}",
                'cart_summary': None
            }

    def get_cart_summary(self, cart_id: str) -> Dict:
        """Get cart summary with all items and total"""
        print(f"\nGetting cart summary for cart: {cart_id}")
        with self.db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # First check if cart exists
                cur.execute("SELECT * FROM cart WHERE cart_id = %s", (cart_id,))
                cart = cur.fetchone()
                print(f"Cart found: {cart}")
                
                # Get all items in cart with details
                print("Fetching cart items...")
                cur.execute("""
                    SELECT 
                        ci.*,
                        CASE 
                            WHEN ci.item_type = 'menu_item' THEN mi.item_name
                            ELSE d.deal_name
                        END as name,
                        CASE 
                            WHEN ci.item_type = 'menu_item' THEN mi.quantity_description
                            ELSE NULL
                        END as quantity_description
                    FROM cart_items ci
                    LEFT JOIN menu_item mi 
                        ON ci.item_id = mi.item_id 
                        AND ci.item_type = 'menu_item'
                    LEFT JOIN deal d 
                        ON ci.item_id = d.deal_id 
                        AND ci.item_type = 'deal'
                    WHERE ci.cart_id = %s
                """, (cart_id,))
                
                rows = cur.fetchall()
                print(f"Found {len(rows)} items in cart")
                
                items = []
                total_price = 0
                
                for row in rows:
                    item_total = float(row['quantity'] * row['unit_price'])
                    total_price += item_total
                    
                    items.append({
                        'item_id': row['item_id'],
                        'item_type': row['item_type'],
                        'item_name': row['name'],
                        'quantity': row['quantity'],
                        'price': float(row['unit_price']),
                        'total': item_total,
                        'special_requests': row['special_requests'],
                        'quantity_description': row['quantity_description']
                    })
                
                return {
                    'cart_id': cart_id,
                    'items': items,
                    'total_items': sum(item['quantity'] for item in items),
                    'total_price': total_price
                }

    def clear_cart(self, cart_id: str) -> Dict:
        """Remove all items from cart"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM cart_items WHERE cart_id = %s",
                        (cart_id,)
                    )
                    conn.commit()
                    
                    return {
                        'success': True,
                        'message': "Cart cleared",
                        'cart_summary': self.get_cart_summary(cart_id)
                    }
        except Exception as e:
            return {
                'success': False,
                'message': f"Error clearing cart: {str(e)}",
                'cart_summary': None
            }