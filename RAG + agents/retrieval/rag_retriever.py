import os
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

load_dotenv()

FAISS_INDEX_PATH = "faiss_index"
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")


class RAGRetriever:
    """Retriever for RAG-based menu context search."""
    
    def __init__(self):
        self.vectorstore = None
        try:
            print("Loading RAG knowledge base from FAISS index...")
            self.vectorstore = FAISS.load_local(
                FAISS_INDEX_PATH,
                embeddings,
                allow_dangerous_deserialization=True
            )
            print("✅ RAG knowledge base loaded successfully.")
        except Exception as e:
            print(f"❌ FATAL: Could not load RAG knowledge base: {e}")
            print("Please ensure you have run 'python vector_store.py' to generate the index.")

    def search(self, query: str, k: int = 5) -> str:
        if self.vectorstore is None:
            return ""
        
        try:
            docs = self.vectorstore.similarity_search(query, k=k)
            results = [doc.page_content for doc in docs]
            return "\n\n---\n\n".join(results)
        except Exception as e:
            print(f"Error during RAG search: {str(e)}")
            return ""
