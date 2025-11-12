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
    if pd.notna(row.item_description):
        text += f"\nDescription: {row.item_description}"
    if pd.notna(row.item_price):
        text += f"\nPrice: {row.item_price}"
    if pd.notna(row.serving_size):
        text += f"\nServing Size: {row.serving_size}"
    if pd.notna(row.quantity_description):
        text += f"\nQuantity Details: {row.quantity_description}"
    if pd.notna(row.prep_time_minutes):
        text += f"\nPrep Time: {row.prep_time_minutes} minutes"
    return text

def format_deal(row):
    text = f"Deal: {row.deal_name}"
    if pd.notna(row.deal_price):
        text += f"\nPrice: {row.deal_price}"
    if pd.notna(row.serving_size):
        text += f"\nServing Size: {row.serving_size}"
    if pd.notna(row.prep_time):
        text += f"\nPrep Time: Approximately {row.prep_time} minutes"
    if pd.notna(row['items']):
        text += f"\nIncludes: {row['items']}"
    return text

def load_texts():
    """
    Connects to the database, runs the menu and deal queries with all required fields,
    formats each row into a text block, and returns a combined list.
    """
    with engine.connect() as conn:
        menu_query = """
        SELECT
          mi.item_id,
          mi.item_name,
          mi.item_description,
          mi.item_price,
          mi.serving_size,
          mi.quantity_description,
          mi.prep_time_minutes
        FROM menu_item mi
        ORDER BY mi.item_id;
        """
        
        # --- query to calculate prep time for deals ---
        deal_query = """
        SELECT
          d.deal_id,
          d.deal_name,
          d.deal_price,
          d.serving_size,
          MAX(mi.prep_time_minutes) AS prep_time,
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


class SearchAgent:
    """Simple Search Agent for matching menu items and deals"""
    def __init__(self):
        self.blocks = load_texts()

    def search(self, term: str):
        """Search for menu items or deals matching the given term"""
        term_lower = term.lower()
        hits = []
        for block in self.blocks:
            if term_lower in block.lower():
                lines = block.splitlines()
                entry = {"raw": block}
                name_line = lines[0]
                if "Menu Item:" in name_line:
                    entry["type"] = "menu_item"
                    entry["item_name"] = name_line.split(":", 1)[1].strip()
                    entry["item_id"] = abs(hash(entry["item_name"])) % 1000
                elif "Deal:" in name_line:
                    entry["type"] = "deal"
                    entry["item_name"] = name_line.split(":", 1)[1].strip()
                    entry["deal_id"] = abs(hash(entry["item_name"])) % 1000
                price = 0.0
                for ln in lines:
                    if ln.lower().startswith("price:"):
                        try:
                            price = float(ln.split(":", 1)[1].strip())
                        except:
                            pass
                        break
                entry["price"] = price
                hits.append(entry)
        return hits

    def get_context_blocks(self):
        """Get all text blocks as a single context string"""
        return "\n\n---\n\n".join(self.blocks)


if __name__ == "__main__":
    texts = load_texts()
    print("Loaded", len(texts), "text blocks for menu and deals.\n")
    if texts:
        print("--- Sample Menu Item Text Block ---")
        print(texts[0], "\n")
        
        # Find a deal to print as a sample
        deal_sample = next((text for text in texts if text.startswith("Deal:")), "No deals found.")
        print("--- Sample Deal Text Block ---")
        print(deal_sample, "\n")