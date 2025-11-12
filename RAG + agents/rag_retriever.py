# rag_retriever.py

import faiss
import pickle
import numpy as np
from openai import OpenAI
import os

# --- CONFIGURATION ---
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
EMBEDDING_MODEL = "text-embedding-3-small"
FAISS_INDEX_PATH = "faiss_index.bin"
TEXT_DATA_PATH = "text_data.pkl"

class RAGRetriever:
    def __init__(self):
        """
        Initializes the retriever by loading the pre-built FAISS index
        and the corresponding text data from disk.
        """
        try:
            print("Loading RAG knowledge base from files...")
            self.index = faiss.read_index(FAISS_INDEX_PATH)
            with open(TEXT_DATA_PATH, 'rb') as f:
                self.texts = pickle.load(f)
            print("RAG knowledge base loaded successfully.")
        except Exception as e:
            print(f"FATAL: Could not load RAG knowledge base: {e}")
            print("Please ensure you have run 'build_vector_store.py' successfully.")
            self.index = None
            self.texts = []

    def _embed_text(self, text: str) -> np.ndarray:
        """Generates an embedding for a given text query."""
        response = client.embeddings.create(input=text, model=EMBEDDING_MODEL)
        return np.array(response.data[0].embedding, dtype='float32')

    def search(self, query: str, k: int = 10) -> str:
        """
        Takes a user query, embeds it, searches the FAISS index for the
        top k most relevant text chunks, and returns them as a single string.
        """
        if self.index is None:
            return "Error: Knowledge base not loaded."

        query_vector = self._embed_text(query).reshape(1, -1)
        
        # Search the index
        distances, indices = self.index.search(query_vector, k)
        
        # Retrieve the corresponding texts
        results = [self.texts[i] for i in indices[0]]
        
        # Combine results into a single context block
        return "\n\n---\n\n".join(results)