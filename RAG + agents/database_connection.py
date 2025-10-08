import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Dict
import os

class DatabaseConnection:
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = DatabaseConnection()
        return cls._instance
    
    def __init__(self):
        self.conn_params = {
            'dbname': 'restaurantDB',
            'user': 'postgres',
            'password': '7980',
            'host': 'localhost',
            'port': '5432'
        }
    
    def get_connection(self):
        return psycopg2.connect(**self.conn_params)