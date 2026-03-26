# Phase 2 - Personalization
"""
RecommendationFallback — Layer 4B of the Personalization Agent.

Orchestrates the tiered recommendation strategy:
  1. Collaborative Filtering  (best — learns from similar users)
  2. FAISS Similarity Search   (good — semantic similarity)
  3. Popularity-Based          (fair — trending items, always works)

Also handles caching in user_profiles and stale profile recovery.

Uses raw psycopg2 (no ORM). Follows score_builder.py style.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras

from personalization.score_builder import ScoreBuilder
from personalization.similarity_search import SimilaritySearch

logger = logging.getLogger(__name__)

# Cache TTL (30 minutes)
CACHE_TTL_MINUTES = 30
# Profile staleness threshold (24 hours)
STALE_HOURS = 24


class RecommendationFallback:
    """
    Orchestrator — tries collab filter → FAISS → popularity,
    with caching and stale-profile recovery.
    """

    def __init__(self, db_conn):
        """
        Parameters
        ----------
        db_conn : psycopg2 connection
        """
        self.conn = db_conn
        self.score_builder = ScoreBuilder(db_conn)
        self.similarity = SimilaritySearch(db_conn)

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def get_recommendations(
        self,
        user_id: str,
        top_k: int = 10,
    ) -> Dict[str, Any]:
        """
        Main entry point — returns personalised recommendations
        with caching and tiered fallback.

        Returns
        -------
        {
            "recommended_items": [{ item_id, item_name, score/similarity/liked_by_count, source, reason }],
            "recommended_deals": [{ deal_id, deal_name, score, source }],
            "source": "collaborative_filtering" | "faiss_similarity" | "popularity_based" | "score_based",
            "from_cache": bool,
            "generated_at": str (ISO)
        }
        """
        try:
            # 0. Ensure profile exists and is fresh
            self._ensure_fresh_profile(user_id)

            # 1. Check cache
            cached = self._check_cache(user_id)
            if cached is not None:
                return cached

            # 2. Tiered recommendation
            items, source = self._tiered_items(user_id, top_k)

            # 3. Fetch top deals from profile (score-based)
            deals = self._get_top_deals(user_id)

            # 4. Add human-readable reasons
            items = self._add_reasons(items, source)

            result = {
                "recommended_items": items,
                "recommended_deals": deals,
                "source": source,
                "from_cache": False,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

            # 5. Cache result
            self._store_cache(user_id, result)

            return result

        except Exception:
            logger.exception("get_recommendations failed for user %s", user_id)
            # Ultimate fallback — popularity
            return self._popularity_fallback(top_k)

    # ─────────────────────────────────────────────────────────────
    # Tiered item recommendation
    # ─────────────────────────────────────────────────────────────

    def _tiered_items(
        self, user_id: str, top_k: int
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Try FAISS similarity → score-based → popularity.
        Returns (items_list, source_string).
        """
        # Tier 1: FAISS Similarity
        faiss_results = self.similarity.find_similar(user_id, top_k=top_k)
        if faiss_results:
            logger.info("User %s: using FAISS similarity (%d items)", user_id, len(faiss_results))
            return faiss_results, "faiss_similarity"

        # Tier 2: Score-based from profile
        profile_items = self._get_scored_items(user_id, top_k)
        if profile_items:
            logger.info("User %s: using score-based from profile (%d items)", user_id, len(profile_items))
            return profile_items, "score_based"

        # Tier 3: Popularity
        logger.info("User %s: falling back to popularity", user_id)
        pop = self._popularity_items(user_id, top_k)
        return pop, "popularity_based"

    # ─────────────────────────────────────────────────────────────
    # Profile & cache helpers
    # ─────────────────────────────────────────────────────────────

    def _ensure_fresh_profile(self, user_id: str) -> None:
        """Build profile if missing or stale (>24h)."""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT last_updated FROM public.user_profiles WHERE user_id = %s",
                    (user_id,),
                )
                row = cur.fetchone()

            if not row:
                logger.info("No profile for user %s — building now", user_id)
                self.score_builder.build_user_profile(user_id)
                return

            last_updated = row["last_updated"]
            if isinstance(last_updated, str):
                last_updated = datetime.fromisoformat(last_updated)
            # Make timezone-aware if naive
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)

            age = datetime.now(timezone.utc) - last_updated
            if age > timedelta(hours=STALE_HOURS):
                logger.info("Profile stale for user %s (%.1fh) — rebuilding", user_id, age.total_seconds() / 3600)
                self.score_builder.build_user_profile(user_id)

        except Exception:
            logger.exception("ensure_fresh_profile failed for %s", user_id)

    def _check_cache(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Return cached recommendations if valid, else None."""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT cached_recommendations, cached_recommendations_ts
                      FROM public.user_profiles
                     WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()

            if not row or not row["cached_recommendations"] or not row["cached_recommendations_ts"]:
                return None

            ts = row["cached_recommendations_ts"]
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            age = datetime.now(timezone.utc) - ts
            if age < timedelta(minutes=CACHE_TTL_MINUTES):
                cached = row["cached_recommendations"]
                if isinstance(cached, str):
                    cached = json.loads(cached)
                cached["from_cache"] = True
                logger.info("Cache hit for user %s (%.1f min old)", user_id, age.total_seconds() / 60)
                return cached

        except Exception:
            logger.exception("Cache check failed for user %s", user_id)
        return None

    def _store_cache(self, user_id: str, result: Dict[str, Any]) -> None:
        """Store recommendation result in user_profiles cache columns."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.user_profiles
                       SET cached_recommendations    = %s,
                           cached_recommendations_ts = NOW()
                     WHERE user_id = %s
                    """,
                    (json.dumps(result, default=str), user_id),
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            logger.exception("Failed to store cache for user %s", user_id)

    # ─────────────────────────────────────────────────────────────
    # Score-based items from profile
    # ─────────────────────────────────────────────────────────────

    def _get_scored_items(self, user_id: str, limit: int) -> List[Dict[str, Any]]:
        """Return top_items from user_profiles (pre-computed by ScoreBuilder)."""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT top_items FROM public.user_profiles WHERE user_id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
            if not row or not row["top_items"]:
                return []
            items = row["top_items"]
            if isinstance(items, str):
                items = json.loads(items)
            # Add source tag
            for it in items:
                it["source"] = "score_based"
            return items[:limit]
        except Exception:
            return []

    def _get_top_deals(self, user_id: str) -> List[Dict[str, Any]]:
        """Return top_deals from user_profiles."""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT top_deals FROM public.user_profiles WHERE user_id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
            if not row or not row["top_deals"]:
                return []
            deals = row["top_deals"]
            if isinstance(deals, str):
                deals = json.loads(deals)
            for d in deals:
                d["source"] = "score_based"
            return deals
        except Exception:
            return []

    # ─────────────────────────────────────────────────────────────
    # Popularity fallback
    # ─────────────────────────────────────────────────────────────

    def _popularity_items(
        self,
        user_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """
        Return trending items ordered last 7 days.
        Optionally filter to user's preferred cuisine.
        """
        try:
            cuisine_filter = self._get_preferred_cuisine(user_id) if user_id else None

            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if cuisine_filter:
                    cur.execute(
                        """
                        SELECT oi.item_id,
                               mi.item_name,
                               COUNT(*) AS order_count,
                               COALESCE(AVG(f.rating), 3) AS avg_rating
                          FROM public.order_items oi
                          JOIN public.orders o  ON o.order_id = oi.order_id
                          JOIN public.menu_item mi ON mi.item_id = oi.item_id
                     LEFT JOIN public.feedback f ON f.item_id = oi.item_id
                         WHERE oi.item_type = 'menu_item'
                           AND o.created_at >= NOW() - INTERVAL '7 days'
                           AND mi.item_cuisine = %s
                         GROUP BY oi.item_id, mi.item_name
                         ORDER BY order_count DESC, avg_rating DESC
                         LIMIT %s
                        """,
                        (cuisine_filter, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT oi.item_id,
                               mi.item_name,
                               COUNT(*) AS order_count,
                               COALESCE(AVG(f.rating), 3) AS avg_rating
                          FROM public.order_items oi
                          JOIN public.orders o  ON o.order_id = oi.order_id
                          JOIN public.menu_item mi ON mi.item_id = oi.item_id
                     LEFT JOIN public.feedback f ON f.item_id = oi.item_id
                         WHERE oi.item_type = 'menu_item'
                           AND o.created_at >= NOW() - INTERVAL '7 days'
                         GROUP BY oi.item_id, mi.item_name
                         ORDER BY order_count DESC, avg_rating DESC
                         LIMIT %s
                        """,
                        (limit,),
                    )
                rows = cur.fetchall()

            results = []
            for r in rows:
                results.append({
                    "item_id": r["item_id"],
                    "item_name": r["item_name"],
                    "order_count": int(r["order_count"]),
                    "avg_rating": round(float(r["avg_rating"]), 2),
                    "source": "popularity_based",
                })
            return results

        except Exception:
            logger.exception("Popularity fallback failed")
            return []

    def _popularity_fallback(self, top_k: int) -> Dict[str, Any]:
        """Ultimate fallback response — popularity items, no deals."""
        items = self._popularity_items(None, top_k)
        for it in items:
            it["reason"] = "Trending this week"
        return {
            "recommended_items": items,
            "recommended_deals": [],
            "source": "popularity_based",
            "from_cache": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _get_preferred_cuisine(self, user_id: str) -> Optional[str]:
        """Get user's top cuisine from profile."""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT preferred_cuisines FROM public.user_profiles WHERE user_id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
            if row and isinstance(row["preferred_cuisines"], list) and row["preferred_cuisines"]:
                return row["preferred_cuisines"][0]
        except Exception:
            pass
        return None

    # ─────────────────────────────────────────────────────────────
    # Reason generation (deterministic — no LLM)
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _add_reasons(
        items: List[Dict[str, Any]], source: str
    ) -> List[Dict[str, Any]]:
        """Add a human-readable reason string to each item."""
        for item in items:
            if source == "collaborative_filtering":
                count = item.get("liked_by_count", 0)
                item["reason"] = f"Users with similar tastes loved this ({count} similar users)"
            elif source == "faiss_similarity":
                seed = item.get("seed_item", "your favourites")
                item["reason"] = f"Similar to {seed}"
            elif source == "score_based":
                score = item.get("score", 0)
                item["reason"] = f"Based on your preferences (score: {score})"
            elif source == "popularity_based":
                item["reason"] = "Trending this week"
            else:
                item["reason"] = "Recommended for you"
        return items
