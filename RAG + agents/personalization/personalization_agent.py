# Phase 3 - Personalization
"""
PersonalizationAgent — Layer 5 (LLM Decision Layer).

Uses Groq (llama-3.3-70b-versatile) to reason over all preference
signals and produce curated recommendations with human-readable
explanations.

On any LLM failure the agent falls back to the deterministic
RecommendationFallback engine (Layer 4B).

Uses raw psycopg2 (no ORM). Follows score_builder.py style.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import psycopg2
import psycopg2.extras

from personalization.recommendation_fallback import RecommendationFallback
from personalization.similarity_search import SimilaritySearch
from personalization.collaborative_filter import CollaborativeFilter
from personalization.score_builder import ScoreBuilder

logger = logging.getLogger(__name__)

# ── Groq / LangChain import (optional – graceful degradation) ────
try:
    from langchain_groq import ChatGroq
    GROQ_AVAILABLE = True
except ImportError:
    logger.warning("langchain-groq not installed — LLM layer disabled")
    GROQ_AVAILABLE = False
    ChatGroq = None  # type: ignore[assignment,misc]


class PersonalizationAgent:
    """
    LLM-powered recommendation agent.

    Flow:
      1. Gather signals (profile, FAISS, collab)
      2. Build context prompt
      3. Call LLM → parse JSON
      4. Validate item_ids / deal_ids against DB
      5. Return enriched recommendations

    Falls back to RecommendationFallback on ANY failure.
    """

    MODEL = "llama-3.3-70b-versatile"
    TEMPERATURE = 0.3
    TIMEOUT_SECONDS = 5

    def __init__(self, db_conn):
        """
        Parameters
        ----------
        db_conn : psycopg2 connection
        """
        self.conn = db_conn
        self.fallback = RecommendationFallback(db_conn)
        self.similarity = SimilaritySearch(db_conn)
        self.collab = CollaborativeFilter(db_conn)
        self.score_builder = ScoreBuilder(db_conn)

        # Initialise LLM
        self._llm = None
        if GROQ_AVAILABLE:
            api_key = os.getenv("GROQ_API_KEY")
            if api_key:
                try:
                    self._llm = ChatGroq(
                        model=self.MODEL,
                        api_key=api_key,
                        temperature=self.TEMPERATURE,
                        timeout=self.TIMEOUT_SECONDS,
                    )
                    logger.info("PersonalizationAgent: Groq LLM initialised (%s)", self.MODEL)
                except Exception:
                    logger.exception("Failed to initialise Groq LLM")
            else:
                logger.warning("GROQ_API_KEY not set — LLM layer disabled")

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def recommend(self, user_id: str, top_k: int = 10) -> Dict[str, Any]:
        """
        Main entry point — LLM-powered recommendations with fallback.

        Returns same shape as RecommendationFallback.get_recommendations().
        """
        try:
            # 0. Ensure profile exists & fresh
            self.fallback._ensure_fresh_profile(user_id)

            # 1. Check cache first
            cached = self.fallback._check_cache(user_id)
            if cached is not None:
                return cached

            # 2. Gather all signals
            profile = self._fetch_full_profile(user_id)
            faiss_results = self.similarity.find_similar(user_id, top_k=top_k)
            collab_results, collab_source = self.collab.get_suggestions(user_id, limit=top_k)

            # 3. Fetch available menu items and deals for the LLM context
            available_items = self._get_all_menu_items()
            available_deals = self._get_all_deals()

            # 4. Try LLM reasoning
            if self._llm and profile:
                llm_result = self._llm_reason(
                    user_id, profile,
                    faiss_results, collab_results, collab_source,
                    available_items, available_deals,
                )
                if llm_result:
                    # Validate IDs
                    llm_result = self._validate_ids(llm_result, available_items, available_deals)

                    result = {
                        "recommended_items": llm_result.get("recommended_items", []),
                        "recommended_deals": llm_result.get("recommended_deals", []),
                        "source": "llm_personalization",
                        "from_cache": False,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                    }

                    # Cache it
                    self.fallback._store_cache(user_id, result)
                    return result

            # 5. LLM not available or failed — deterministic fallback
            logger.info("LLM unavailable for user %s — using deterministic fallback", user_id)
            return self.fallback.get_recommendations(user_id, top_k=top_k)

        except Exception:
            logger.exception("PersonalizationAgent.recommend failed for user %s", user_id)
            return self.fallback.get_recommendations(user_id, top_k=top_k)

    # ─────────────────────────────────────────────────────────────
    # LLM reasoning
    # ─────────────────────────────────────────────────────────────

    def _llm_reason(
        self,
        user_id: str,
        profile: Dict[str, Any],
        faiss_results: List[Dict[str, Any]],
        collab_results: List[Dict[str, Any]],
        collab_source: str,
        available_items: List[Dict[str, Any]],
        available_deals: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Build prompt → call LLM → parse JSON response.
        Returns parsed dict or None on failure.
        """
        try:
            context = self._build_context(
                profile, faiss_results, collab_results, collab_source,
                available_items, available_deals,
            )

            prompt = f"""You are a restaurant recommendation AI for Khadim restaurant.
Analyze this user's preferences and the recommendation signals below,
then select the best 5 menu items and up to 3 deals to recommend.

{context}

RULES:
- ONLY recommend items/deals from the "Available" lists provided above.
- Use the exact item_id / deal_id from those lists.
- Exclude any items in the user's disliked list.
- For each recommendation, write a short, friendly reason (1 sentence).
- Score each recommendation 0-100 based on confidence.
- Prioritize high-confidence matches.

Output MUST be valid JSON with this EXACT structure (no markdown, no extra text):
{{
  "recommended_items": [
    {{"item_id": <int>, "item_name": "<string>", "score": <0-100>, "reason": "<string>"}}
  ],
  "recommended_deals": [
    {{"deal_id": <int>, "deal_name": "<string>", "score": <0-100>, "reason": "<string>"}}
  ]
}}"""

            response = self._llm.invoke(prompt)  # type: ignore[union-attr]
            raw_text = response.content if hasattr(response, "content") else str(response)

            logger.info("LLM raw response length: %d chars", len(raw_text))

            # Parse JSON
            return self._parse_llm_json(raw_text)

        except Exception:
            logger.exception("LLM reasoning failed for user %s", user_id)
            return None

    # ─────────────────────────────────────────────────────────────
    # Context building
    # ─────────────────────────────────────────────────────────────

    def _build_context(
        self,
        profile: Dict[str, Any],
        faiss_results: List[Dict[str, Any]],
        collab_results: List[Dict[str, Any]],
        collab_source: str,
        available_items: List[Dict[str, Any]],
        available_deals: List[Dict[str, Any]],
    ) -> str:
        """Build structured text context for the LLM prompt."""
        sections = []

        # User profile
        top_items = profile.get("top_items", [])
        cuisines = profile.get("preferred_cuisines", [])
        disliked = profile.get("disliked_items", [])

        sections.append("=== USER PROFILE ===")
        if top_items:
            items_str = ", ".join(
                f"{t.get('item_name', '?')} (score {t.get('score', 0)})"
                for t in top_items[:5]
            )
            sections.append(f"Top items: {items_str}")
        if cuisines:
            sections.append(f"Preferred cuisines: {', '.join(str(c) for c in cuisines)}")
        if disliked:
            sections.append(f"Disliked item IDs (EXCLUDE these): {disliked}")
        sections.append("")

        # FAISS similar items
        if faiss_results:
            sections.append("=== FAISS SIMILAR ITEMS (semantically similar to user's favourites) ===")
            for r in faiss_results[:8]:
                sections.append(
                    f"- {r.get('item_name', '?')} (item_id={r.get('item_id')}, "
                    f"similarity={r.get('similarity', 0)}, seed={r.get('seed_item', '?')})"
                )
            sections.append("")

        # Collab filter results
        if collab_results:
            sections.append(f"=== COLLABORATIVE FILTER ({collab_source}) ===")
            for r in collab_results[:8]:
                sections.append(
                    f"- {r.get('item_name', '?')} (item_id={r.get('item_id')}, "
                    f"liked_by={r.get('liked_by_count', 0)} similar users)"
                )
            sections.append("")

        # Available items (limited to 30 to stay within context)
        sections.append("=== AVAILABLE MENU ITEMS (choose ONLY from these) ===")
        for it in available_items[:30]:
            sections.append(
                f"- item_id={it['item_id']}, name=\"{it['item_name']}\", "
                f"price={it.get('price', '?')}, cuisine={it.get('cuisine', '?')}"
            )
        sections.append("")

        # Available deals
        sections.append("=== AVAILABLE DEALS (choose ONLY from these) ===")
        for d in available_deals[:15]:
            sections.append(
                f"- deal_id={d['deal_id']}, name=\"{d['deal_name']}\", "
                f"price={d.get('price', '?')}"
            )
        sections.append("")

        # Current time hint
        now = datetime.now(timezone.utc)
        hour = now.hour + 5  # PKT rough offset
        if 11 <= hour <= 14:
            sections.append("Current time context: Lunch hour")
        elif 18 <= hour <= 22:
            sections.append("Current time context: Dinner time")
        else:
            sections.append(f"Current time context: {now.strftime('%H:%M')} UTC")

        return "\n".join(sections)

    # ─────────────────────────────────────────────────────────────
    # JSON parsing (with regex fallback)
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_llm_json(raw_text: str) -> Optional[Dict[str, Any]]:
        """
        Try to parse JSON from LLM response.
        Falls back to regex extraction if LLM wrapped it in markdown.
        """
        # Attempt 1: direct parse
        try:
            return json.loads(raw_text.strip())
        except json.JSONDecodeError:
            pass

        # Attempt 2: strip markdown code fences
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (```json or ```)
            first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
            cleaned = cleaned[first_newline + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            try:
                return json.loads(cleaned.strip())
            except json.JSONDecodeError:
                pass

        # Attempt 3: regex — find outermost { … }
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse LLM JSON response")
        return None

    # ─────────────────────────────────────────────────────────────
    # ID validation
    # ─────────────────────────────────────────────────────────────

    def _validate_ids(
        self,
        result: Dict[str, Any],
        available_items: List[Dict[str, Any]],
        available_deals: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Filter out any recommended item_ids / deal_ids that don't
        exist in the database.
        """
        valid_item_ids: Set[int] = {it["item_id"] for it in available_items}
        valid_deal_ids: Set[int] = {d["deal_id"] for d in available_deals}

        rec_items = result.get("recommended_items", [])
        rec_deals = result.get("recommended_deals", [])

        result["recommended_items"] = [
            item for item in rec_items
            if isinstance(item, dict) and item.get("item_id") in valid_item_ids
        ]
        result["recommended_deals"] = [
            deal for deal in rec_deals
            if isinstance(deal, dict) and deal.get("deal_id") in valid_deal_ids
        ]

        # After filtering, add default score if missing
        for item in result["recommended_items"]:
            item.setdefault("score", 50)
            item["source"] = "llm_personalization"
        for deal in result["recommended_deals"]:
            deal.setdefault("score", 50)
            deal["source"] = "llm_personalization"


        return result

    # ─────────────────────────────────────────────────────────────
    # DB helpers
    # ─────────────────────────────────────────────────────────────

    def _fetch_full_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full user profile from user_profiles table."""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT preferred_cuisines, top_items, top_deals,
                           disliked_items, preference_vector
                      FROM public.user_profiles
                     WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
            if not row:
                return None
            # Ensure JSONB fields are lists/dicts
            profile: Dict[str, Any] = {}
            for key in ("preferred_cuisines", "top_items", "top_deals", "disliked_items"):
                val = row.get(key)
                if isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except json.JSONDecodeError:
                        val = []
                profile[key] = val or []
            pv = row.get("preference_vector")
            if isinstance(pv, str):
                try:
                    pv = json.loads(pv)
                except json.JSONDecodeError:
                    pv = {}
            profile["preference_vector"] = pv or {}
            return profile
        except Exception:
            logger.exception("Failed to fetch full profile for user %s", user_id)
            return None

    def _get_all_menu_items(self) -> List[Dict[str, Any]]:
        """Fetch all active menu items (id, name, price, cuisine)."""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT item_id, item_name, item_price AS price,
                           item_cuisine AS cuisine
                      FROM public.menu_item
                     ORDER BY item_id
                    """
                )
                return [dict(r) for r in cur.fetchall()]
        except Exception:
            logger.exception("Failed to fetch menu items")
            return []

    def _get_all_deals(self) -> List[Dict[str, Any]]:
        """Fetch all active deals (id, name, price)."""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT deal_id, deal_name, deal_price AS price
                      FROM public.deal
                     ORDER BY deal_id
                    """
                )
                return [dict(r) for r in cur.fetchall()]
        except Exception:
            logger.exception("Failed to fetch deals")
            return []
