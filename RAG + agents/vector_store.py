import numpy as np
import faiss
import pickle
from openai import OpenAI
import os
from dotenv import load_dotenv

from search_agent import load_texts

# --- CONFIGURATION ---
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
EMBEDDING_MODEL = "text-embedding-3-small"
FAISS_INDEX_PATH = "faiss_index.bin"
TEXT_DATA_PATH = "text_data.pkl"

# --- FUNCTIONS ---

def create_and_save_vector_store(texts: list[str]):
    """
    Takes a list of texts, creates embeddings IN A SINGLE BATCH, builds a FAISS index,
    and saves both the index and the original texts to files.
    """
    if not texts:
        print("No texts to process. Exiting.")
        return

    print(f"Starting embedding process for {len(texts)} text blocks using '{EMBEDDING_MODEL}' in a single batch...")
    
    # 1. Create embeddings for all text blocks in one API call
    response = client.embeddings.create(input=texts, model=EMBEDDING_MODEL)
    embeddings = np.array([item.embedding for item in response.data], dtype='float32')

    print("Embeddings created successfully.")
    
    # 2. Build the FAISS index
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)
    
    print(f"FAISS index with {index.ntotal} vectors created.")
    
    # 3. Save the FAISS index to a file
    faiss.write_index(index, FAISS_INDEX_PATH)
    print(f"FAISS index saved to '{FAISS_INDEX_PATH}'")
    
    # 4. Save the original texts to a corresponding file
    with open(TEXT_DATA_PATH, 'wb') as f:
        pickle.dump(texts, f)
    print(f"Original texts saved to '{TEXT_DATA_PATH}'")
    
    print("\nVector store build process complete!")


if __name__ == "__main__":
    print("Loading menu and deal information from the database...")
    all_texts = load_texts()
    
    create_and_save_vector_store(all_texts)