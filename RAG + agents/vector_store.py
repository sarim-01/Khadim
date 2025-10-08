import os
import numpy as np
import faiss
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def embed_text(text: str) -> np.ndarray:
    resp = client.embeddings.create(model="text-embedding-ada-002", input=text)
    return np.array(resp.data[0].embedding, dtype=np.float32)

def build_index(texts: list[str]):
    embs = [embed_text(t) for t in texts]
    dim = embs[0].shape[0]
    idx = faiss.IndexFlatL2(dim)
    idx.add(np.stack(embs))
    return idx

def query_index(index, texts, query: str, k=6):
    qv = embed_text(query)
    D, I = index.search(np.array([qv]), k)
    
    # Filter out results that are too dissimilar (high distance means less relevant)
    # Standard threshold for L2 distance in embedding space
    threshold = 0.8
    
    filtered_results = []
    for dist, idx in zip(D[0], I[0]):
        if dist < threshold:  # Only include results that are similar enough
            filtered_results.append(texts[idx])
    
    return filtered_results
