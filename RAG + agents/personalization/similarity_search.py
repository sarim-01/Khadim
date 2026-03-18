# Phase 2 - Personalization
"""
SimilaritySearch — Layer 3 of the Personalization Agent.

Uses the existing LangChain FAISS index (built with all-MiniLM-L6-v2)
to find menu items semantically similar to a user's top-scored items.

Follows the same psycopg2 + logging style as score_builder.py.
"""

import logging
from typing import Any, Dict, List, Optional, Set

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

# ── FAISS / embedding imports (lazy - may not be installed) ──────
try:
    from langchain_community.vectorstores import FAISS
    from langchain_huggingface import HuggingFaceEmbeddings

    FAISS_INDEX_PATH = "faiss_index"
    _embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    FAISS_AVAILABLE = True
except Exception as e:
    logger.warning("FAISS dependencies not available: %s", e)
    FAISS_AVAILABLE = False
    _embeddings = None


class SimilaritySearch:
    """Find semantically similar menu items via FAISS vector search."""

    def __init__(self, db_conn):
        """
        Parameters
        ----------
        db_conn : psycopg2 connection
        """
        self.conn = db_conn
        self._vectorstore = None

    # ─────────────────────────────────────────────────────────────
    # Lazy-load FAISS index
    # ─────────────────────────────────────────────────────────────

    def _load_vectorstore(self):
        """Load the LangChain FAISS vectorstore once."""
        if self._vectorstore is not None:
            return
        if not FAISS_AVAILABLE:
            logger.warning("FAISS not available — similarity search disabled")
            return
        try:
            self._vectorstore = FAISS.load_local(
                FAISS_INDEX_PATH,
                _embeddings,
                allow_dangerous_deserialization=True,
            )
            logger.info("FAISS index loaded from %s", FAISS_INDEX_PATH)
        except Exception:
            logger.exception("Failed to load FAISS index")

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def find_similar(
        self,
        user_id: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        For a user's top items, query FAISS for semantically similar
        items that the user has NOT already ordered / disliked.

        Returns a list of dicts:
          [{ item_id, item_name, similarity, source: "faiss_similarity" }, …]

        Never raises — returns [] on any failure.
        """
        try:
            self._load_vectorstore()
            if self._vectorstore is None:
                return []

            # 1. Get user profile (top_items + disliked_items)
            profile = self._fetch_profile(user_id)
            if not profile:
                return []

            top_items = profile.get("top_items") or []
            disliked_ids: Set[int] = set(profile.get("disliked_items") or [])
            already_ordered_ids = self._get_ordered_item_ids(user_id)
            exclude_ids = disliked_ids | already_ordered_ids

            # 2. For each top item, search FAISS for neighbours
            seen: Set[int] = set()
            results: List[Dict[str, Any]] = []

            for ti in top_items[:5]:  # Use top 5 items as seeds
                item_name = ti.get("item_name", "")
                if not item_name:
                    continue

                neighbours = self._query_faiss(item_name, k=top_k)
                for nbr in neighbours:
                    nbr_id = nbr.get("item_id")
                    if nbr_id is None:
                        continue
                    if nbr_id in exclude_ids or nbr_id in seen:
                        continue
                    seen.add(nbr_id)
                    results.append({
                        "item_id": nbr_id,
                        "item_name": nbr.get("item_name", f"Item #{nbr_id}"),
                        "similarity": nbr.get("score", 0),
                        "source": "faiss_similarity",
                        "seed_item": item_name,
                    })

            # Sort by similarity descending, return top_k
            results.sort(key=lambda x: x["similarity"], reverse=True)
            return results[:top_k]

        except Exception:
            logger.exception("Similarity search failed for user %s", user_id)
            return []

    # ─────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────

    def _query_faiss(self, query_text: str, k: int = 10) -> List[Dict[str, Any]]:
        """
        Query the LangChain FAISS vectorstore by text.
        Returns list of {item_id, item_name, score}.
        """
        if self._vectorstore is None:
            return []

        try:
            docs_and_scores = self._vectorstore.similarity_search_with_score(
                query_text, k=k
            )

            results = []
            for doc, score in docs_and_scores:
                # Parse item_id from the document content
                item_info = self._parse_doc_to_item(doc.page_content)
                if item_info:
                    item_info["score"] = round(float(1.0 / (1.0 + score)), 4)  # convert L2 distance → similarity
                    results.append(item_info)
            return results

        except Exception:
            logger.exception("FAISS query failed for: %s", query_text)
            return []

    def _parse_doc_to_item(self, page_content: str) -> Optional[Dict[str, Any]]:
        """
        Try to extract item_id and item_name from the FAISS document
        page_content string. Falls back to DB lookup by name.
        """
        # The page_content is a formatted text block. Try to find the
        # item name from the first line and look it up in DB.
        first_line = page_content.strip().split("\n")[0].strip()
        # Remove common prefixes like "Item: " or "Menu Item: "
        for prefix in ("Item:", "Menu Item:", "Deal:", "-"):
            if first_line.startswith(prefix):
                first_line = first_line[len(prefix):].strip()

        if not first_line:
            return None

        return self._lookup_item_by_name(first_line)

    def _lookup_item_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Search menu_item table for an item matching name (case-insensitive)."""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT item_id, item_name
                      FROM public.menu_item
                     WHERE LOWER(item_name) = LOWER(%s)
                     LIMIT 1
                    """,
                    (name,),
                )
                row = cur.fetchone()
                if row:
                    return {"item_id": row["item_id"], "item_name": row["item_name"]}

                # Fuzzy fallback — LIKE match
                cur.execute(
                    """
                    SELECT item_id, item_name
                      FROM public.menu_item
                     WHERE LOWER(item_name) LIKE LOWER(%s)
                     LIMIT 1
                    """,
                    (f"%{name[:20]}%",),
                )
                row = cur.fetchone()
                if row:
                    return {"item_id": row["item_id"], "item_name": row["item_name"]}
        except Exception:
            logger.exception("DB lookup failed for item name: %s", name)
        return None

    def _fetch_profile(self, user_id: str) -> Optional[dict]:
        """Fetch user_profiles row as dict."""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT top_items, disliked_items
                      FROM public.user_profiles
                     WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                # JSONB columns may already be parsed by psycopg2
                top_items = row["top_items"] if isinstance(row["top_items"], list) else []
                disliked = row["disliked_items"] if isinstance(row["disliked_items"], list) else []
                return {"top_items": top_items, "disliked_items": disliked}
        except Exception:
            logger.exception("Failed to fetch profile for similarity search")
            return None

    def _get_ordered_item_ids(self, user_id: str) -> Set[int]:
        """Return set of item_ids this user has ever ordered."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT oi.item_id
                      FROM public.order_items oi
                      JOIN public.orders o ON o.order_id = oi.order_id
                      JOIN public.cart c   ON c.cart_id  = o.cart_id
                     WHERE c.user_id = %s
                       AND oi.item_type = 'menu_item'
                    """,
                    (user_id,),
                )
                return {r[0] for r in cur.fetchall()}
        except Exception:
            logger.exception("Failed to fetch ordered item ids")
            return set()
