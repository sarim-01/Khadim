from database_connection import DatabaseConnection
from psycopg2.extras import RealDictCursor

def check_cart_contents():
    db = DatabaseConnection.get_instance()
    with db.get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            print("\n=== Cart Table Contents ===")
            cur.execute("SELECT * FROM cart")
            carts = cur.fetchall()
            for cart in carts:
                print(f"\nCart ID: {cart['cart_id']}")
                print(f"Status: {cart['status']}")
                print(f"Created: {cart['created_at']}")
                
                # Get items in this cart
                cur.execute("""
                    SELECT ci.*, 
                           CASE 
                               WHEN ci.item_type = 'menu_item' THEN mi.item_name 
                               ELSE d.deal_name 
                           END as item_name
                    FROM cart_items ci
                    LEFT JOIN menu_item mi ON ci.item_type = 'menu_item' AND ci.item_id = mi.item_id
                    LEFT JOIN deal d ON ci.item_type = 'deal' AND ci.item_id = d.deal_id
                    WHERE ci.cart_id = %s
                """, (cart['cart_id'],))
                items = cur.fetchall()
                
                if items:
                    print("\nItems in cart:")
                    for item in items:
                        print(f"- {item['quantity']}x {item['item_name']} (Rs. {item['unit_price']} each)")
                        if item['special_requests']:
                            print(f"  Note: {item['special_requests']}")
                else:
                    print("\nNo items in cart")

if __name__ == "__main__":
    check_cart_contents()