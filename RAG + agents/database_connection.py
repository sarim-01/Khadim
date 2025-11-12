# Updated database_connection.py - Simplified and clean

import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional

class DatabaseConnection:
    """Singleton database connection class for Khadim restaurant system"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = DatabaseConnection()
        return cls._instance
    
    def __init__(self):
        # Database connection parameters
        # Update these according to your setup
        self.conn_params = {
            'dbname': 'restaurantDB',
            'user': 'postgres', 
            'password': '7980',
            'host': 'localhost',
            'port': '5432'
        }
    
    def get_connection(self):
        """Get database connection"""
        try:
            return psycopg2.connect(**self.conn_params)
        except psycopg2.Error as e:
            print(f"Database connection error: {e}")
            raise
    
    def test_connection(self) -> bool:
        """Test if database connection works"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return True
        except:
            return False

# Test connection when module is imported
if __name__ == "__main__":
    db = DatabaseConnection.get_instance()
    if db.test_connection():
        print("✅ Database connection successful!")
    else:
        print("❌ Database connection failed!")