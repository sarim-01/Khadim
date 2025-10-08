# Fixed database_utils.py

from typing import Optional, Dict, List
from database_connection import DatabaseConnection
from psycopg2.extras import RealDictCursor

class MenuDatabase:
    def __init__(self):
        self.db = DatabaseConnection.get_instance()

    def get_item_details(self, item_name: str) -> Optional[Dict]:
        """Get item details from the database by name"""
        with self.db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # ✅ FIXED: Removed similarity() function usage
                cursor.execute("""
                SELECT item_id, item_name, item_price, quantity_description
                FROM menu_item
                WHERE item_name ILIKE %s
                LIMIT 1
                """, (f"%{item_name}%",))
                
                row = cursor.fetchone()
                return dict(row) if row else None

    def validate_item(self, item_name: str) -> bool:
        """Check if an item exists in the menu"""
        with self.db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                SELECT COUNT(*)
                FROM menu_item
                WHERE item_name ILIKE %s
                """, (f"%{item_name}%",))
                return cursor.fetchone()[0] > 0

    def get_similar_items(self, item_name: str, limit: int = 5) -> List[str]:
        """Get similar item names from the menu"""
        with self.db.get_connection() as conn:
            with conn.cursor() as cursor:
                # ✅ FIXED: Removed similarity() function usage and duplicate method
                cursor.execute("""
                SELECT item_name
                FROM menu_item
                WHERE item_name ILIKE %s
                LIMIT %s
                """, (f"%{item_name}%", limit))
                return [row[0] for row in cursor.fetchall()]

    def get_deal_details(self, deal_name: str) -> Optional[Dict]:
        """Get deal details from the database by name"""
        with self.db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                SELECT deal_id, deal_name, deal_price, deal_description
                FROM deal
                WHERE deal_name ILIKE %s
                LIMIT 1
                """, (f"%{deal_name}%",))
                
                row = cursor.fetchone()
                return dict(row) if row else None

    def validate_deal(self, deal_name: str) -> bool:
        """Check if a deal exists"""
        with self.db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                SELECT COUNT(*)
                FROM deal
                WHERE deal_name ILIKE %s
                """, (f"%{deal_name}%",))
                return cursor.fetchone()[0] > 0

    def get_similar_deals(self, deal_name: str, limit: int = 5) -> List[str]:
        """Get similar deal names from the database"""
        with self.db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                SELECT deal_name
                FROM deal
                WHERE deal_name ILIKE %s
                LIMIT %s
                """, (f"%{deal_name}%", limit))
                return [row[0] for row in cursor.fetchall()]

# ✅ REMOVED: Duplicate get_similar_items() method and SQLite references