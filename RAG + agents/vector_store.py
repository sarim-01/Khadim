import os
from dotenv import load_dotenv
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from search_agent import load_texts

load_dotenv()

FAISS_INDEX_PATH = "faiss_index"
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

def create_and_save_vector_store():
    print("Loading menu data...")
    # 1. Load the list of formatted strings from search_agent
    text_blocks = load_texts()
    
    if not text_blocks:
        print("No texts to process.")
        return

    print(f"Processing {len(text_blocks)} menu items/deals...")

    docs = []
    for block in text_blocks:
        docs.append(Document(page_content=block, metadata={"source": "menu_db"}))

    print("Creating embeddings (1 Vector per Item)...")
    
    # 3. Create FAISS index from these distinct documents
    vectorstore = FAISS.from_documents(docs, embeddings)

    vectorstore.save_local(FAISS_INDEX_PATH)
    print(f"✅ FAISS index saved successfully with {len(docs)} vectors!")

if __name__ == "__main__":
    create_and_save_vector_store()