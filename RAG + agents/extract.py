import os
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)

def format_menu_item(row):
    text = f"Menu Item: {row.item_name}"
    if pd.notna(row.chefs):
        text += f"\nChefs: {row.chefs}"
    return text

def format_deal(row):
    text = f"Deal: {row.deal_name}"
    if pd.notna(row.deal_price):
        text += f"\nPrice: {row.deal_price}"
    if pd.notna(row.serving_size):
        text += f"\nServing Size: {row.serving_size}"
    if pd.notna(row['items']):
        text += f"\nIncludes: {row['items']}"
    return text

def load_texts():
    """
    Connects to the database, runs the menu and deal queries,
    formats each row into a text block, and returns a combined list.
    """
    with engine.connect() as conn:
        menu_query = """
        SELECT
          mi.item_id,
          mi.item_name,
          STRING_AGG(c.cheff_name, ', ' ORDER BY c.cheff_name) AS chefs
        FROM menu_item_chefs mic
        JOIN menu_item mi ON mi.item_id = mic.menu_item_id
        JOIN chef c ON c.cheff_id = mic.chef_id
        GROUP BY mi.item_id, mi.item_name
        ORDER BY mi.item_id;
        """
        deal_query = """
        SELECT
          d.deal_id,
          d.deal_name,
          d.deal_price,
          d.serving_size,
          string_agg(
            di.quantity::text || ' ' || mi.item_name,
            ', ' ORDER BY di.menu_item_id
          ) AS items
        FROM deal d
        JOIN deal_item di ON di.deal_id = d.deal_id
        JOIN menu_item mi ON mi.item_id = di.menu_item_id
        GROUP BY d.deal_id, d.deal_name, d.deal_price, d.serving_size
        ORDER BY d.deal_id;
        """
        menu_df = pd.read_sql(menu_query, conn)
        deal_df = pd.read_sql(deal_query, conn)

    menu_texts = [format_menu_item(row) for _, row in menu_df.iterrows()]
    deal_texts = [format_deal(row) for _, row in deal_df.iterrows()]

    return menu_texts + deal_texts

if __name__ == "__main__":
    texts = load_texts()
    print("Loaded", len(texts), "text blocks for menu and deals.\n")
    if texts:
        print("Sample Text Block:\n", texts[0], "\n")
