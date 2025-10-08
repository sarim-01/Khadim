import os
import numpy as np
import faiss
from openai import OpenAI
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=API_KEY)

db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)

def embed_text(text):
    # Call OpenAI's embedding API
    response = client.embeddings.create(
        model="text-embedding-ada-002",
        input=text
    )
    # Access the first embedding vector properly
    return np.array(response.data[0].embedding, dtype=np.float32)

# Step 4 functions from before (use your exact function implementations)
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

def create_vector_store(texts):
    embeddings = []
    for text in texts:
        print(f"Embedding text: {text[:30]}...")  # progress output
        emb = embed_text(text)
        embeddings.append(emb)

    dimension = len(embeddings[0])
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings))

    print(f"Added {index.ntotal} vectors to FAISS index.")
    return index, texts

if __name__ == "__main__":
    texts = load_texts()
    print(f"Loaded {len(texts)} documents for embedding.")

    index, docs = create_vector_store(texts)

    # Test search example:
    query = "What dishes are in the Fast Solo A deal?"
    query_vec = embed_text(query)
    D, I = index.search(np.array([query_vec]), k=3)

    print("Top search matches:")
    for i, score in zip(I[0], D[0]):
        print(f"Score: {score:.4f}, Text: {docs[i]}")

