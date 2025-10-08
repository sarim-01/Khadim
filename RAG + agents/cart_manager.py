import sqlite3
from datetime import datetime
from typing import Dict, Optional, List
import uuid

class CartManager:
    def __init__(self, db_path: str = "restaurant.db"):
        self.db_path = db_path
        self._initialize_db()

    def _initialize_db(self):
        """Initialize cart tables"""
        with open('database/cart_schema.sql', 'r') as f:
            schema = f.read()
            
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(schema)

    def create_cart(self) -> str:
        """Create a new active cart"""
        cart_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO cart (cart_id) VALUES (?)",
                (cart_id,)
            )
        return cart_id

    def add_item(self, cart_id: str, item_data: Dict, quantity: int = 1,
                 special_requests: Optional[str] = None) -> Dict:
        """Add or update item in cart"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Check if item exists
                cursor = conn.execute(
                    """SELECT quantity FROM cart_items 
                       WHERE cart_id = ? AND item_id = ? AND item_type = ?""",
                    (cart_id, item_data['item_id'], 
                     'deal' if 'deal_id' in item_data else 'menu_item')
                )
                existing = cursor.fetchone()
                
                if existing:
                    # Update quantity of existing item
                    new_quantity = existing[0] + quantity
                    conn.execute(
                        """UPDATE cart_items 
                           SET quantity = ?, special_requests = ?,
                               unit_price = ?
                           WHERE cart_id = ? AND item_id = ? AND item_type = ?""",
                        (new_quantity, special_requests, item_data['price'],
                         cart_id, item_data['item_id'],
                         'deal' if 'deal_id' in item_data else 'menu_item')
                    )
                else:
                    # Add new item
                    conn.execute(
                        """INSERT INTO cart_items 
                           (cart_id, item_id, item_type, quantity, 
                            unit_price, special_requests)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (cart_id, item_data['item_id'],
                         'deal' if 'deal_id' in item_data else 'menu_item',
                         quantity, item_data['price'], special_requests)
                    )
                
                # Update cart timestamp
                conn.execute(
                    "UPDATE cart SET updated_at = CURRENT_TIMESTAMP WHERE cart_id = ?",
                    (cart_id,)
                )
                
                return {
                    'success': True,
                    'message': f"Added {quantity}x {item_data['item_name']} to cart",
                    'cart_summary': self.get_cart_summary(cart_id)
                }
                
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
            with sqlite3.connect(self.db_path) as conn:
                if new_quantity > 0:
                    conn.execute(
                        """UPDATE cart_items 
                           SET quantity = ?
                           WHERE cart_id = ? AND item_id = ? AND item_type = ?""",
                        (new_quantity, cart_id, item_id, item_type)
                    )
                else:
                    # Remove item if quantity is 0
                    conn.execute(
                        """DELETE FROM cart_items 
                           WHERE cart_id = ? AND item_id = ? AND item_type = ?""",
                        (cart_id, item_id, item_type)
                    )
                
                conn.execute(
                    "UPDATE cart SET updated_at = CURRENT_TIMESTAMP WHERE cart_id = ?",
                    (cart_id,)
                )
                
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

    def remove_item(self, cart_id: str, item_id: Optional[int] = None,
                   item_type: Optional[str] = None) -> Dict:
        """Remove item from cart"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """DELETE FROM cart_items 
                       WHERE cart_id = ? AND item_id = ? AND item_type = ?""",
                    (cart_id, item_id, item_type)
                )
                
                conn.execute(
                    "UPDATE cart SET updated_at = CURRENT_TIMESTAMP WHERE cart_id = ?",
                    (cart_id,)
                )
                
                return {
                    'success': True,
                    'message': "Item removed from cart",
                    'cart_summary': self.get_cart_summary(cart_id)
                }
        except Exception as e:
            return {
                'success': False,
                'message': f"Error removing item: {str(e)}",
                'cart_summary': None
            }

    def get_cart_summary(self, cart_id: str) -> Dict:
        """Get cart summary with all items and total"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Get all items in cart with details
            cursor = conn.execute(
                """SELECT ci.*, 
                          CASE 
                              WHEN ci.item_type = 'menu_item' THEN mi.item_name
                              ELSE d.deal_name
                          END as name
                   FROM cart_items ci
                   LEFT JOIN menu_item mi 
                        ON ci.item_id = mi.item_id 
                        AND ci.item_type = 'menu_item'
                   LEFT JOIN deal d 
                        ON ci.item_id = d.deal_id 
                        AND ci.item_type = 'deal'
                   WHERE ci.cart_id = ?""",
                (cart_id,)
            )
            
            items = []
            total_price = 0
            
            for row in cursor.fetchall():
                item_total = row['quantity'] * row['unit_price']
                total_price += item_total
                
                items.append({
                    'item_id': row['item_id'],
                    'item_type': row['item_type'],
                    'item_name': row['name'],
                    'quantity': row['quantity'],
                    'price': row['unit_price'],
                    'total': item_total,
                    'special_requests': row['special_requests']
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
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM cart_items WHERE cart_id = ?", (cart_id,))
                conn.execute(
                    "UPDATE cart SET updated_at = CURRENT_TIMESTAMP WHERE cart_id = ?",
                    (cart_id,)
                )
                
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