# Personalization Agent — Implementation Plan (v2.0)

**Khadim: AI-Powered Restaurant Automation System**  
**Module:** Personalization & Re-engagement Agent Foundation  
**Date:** March 18, 2026  
**Status:** Ready for Phase 1 Implementation  
**Version:** 2.0 — Enhanced with fallback logic, caching, and production safeguards

---

## Executive Summary

A multi-layer AI recommendation agent that learns user preferences from past interactions and surfaces personalized menu items and deals on the Home screen. It feeds into the future Re-engagement Agent via stored user preference snapshots. This is a **real-world production-ready system** incorporating scoring with time decay, FAISS vector search, collaborative filtering with graceful fallbacks, and LLM reasoning — designed to survive testing constraints and live-demo scenarios.

---

## Overview & Architecture

### Two Separate Recommendation Systems

| System | Purpose | Logic | Status |
|---|---|---|---|
| **Cart Recommender** (existing) | Suggests add-ons based on current cart items | Rule-based | ✓ Already built |
| **Personalization Agent** (new) | Suggests based on past user interactions | AI + RAG + ML + Fallbacks | 🚧 This document |

### Personalization Agent — What It Does

1. **Fetch user signals from DB** — orders, ratings, favourites, soft ratings
2. **Build user preference profile** — scored per item/cuisine/deal-type with time decay
3. **Query vector DB (FAISS)** — find semantically similar items to what user liked
   - Example: User loved "Zinger Burger" → FAISS finds "Chicken Burger", "Crispy Burger", "Zinger Deal"
4. **Collaborative filtering** — find users with similar taste profiles → surface what they liked that this user hasn't tried
5. **Tiered fallback system** — if collab filter weak, use FAISS; if that weak, use popularity
6. **LLM decision layer** — agent reasons over all signals and produces final ranked list with human-readable reasons
7. **Returns cached or fresh recommendations** with explanation tags

---

## Layer 1 — Database Schema

### New Table: `user_profiles`

Stores preprocessed preference data for each user to enable fast recommendation queries.

```sql
CREATE TABLE public.user_profiles (
    profile_id                SERIAL PRIMARY KEY,
    user_id                   UUID NOT NULL UNIQUE REFERENCES auth.app_users(user_id) ON DELETE CASCADE,
    preferred_cuisines        JSONB DEFAULT '[]',     
    -- Example: ["Fast Food", "BBQ", "Asian"]
    -- Updated after every order; tracks cuisine patterns
    
    top_items                 JSONB DEFAULT '[]',      
    -- Example: [
    --   {item_id: 3, item_name: "Zinger Burger", score: 85, order_count: 5, last_ordered: "2026-03-10"},
    --   {item_id: 15, item_name: "Crispy Fries", score: 72, order_count: 3, last_ordered: "2026-03-15"}
    -- ]
    -- Top 10 highest-scoring items for this user (with time decay applied)
    
    top_deals                 JSONB DEFAULT '[]',      
    -- Example: [
    --   {deal_id: 2, deal_name: "Duo Combo", score: 78, selected_count: 4}
    -- ]
    -- Top 5 highest-scoring deals for this user
    
    disliked_items            JSONB DEFAULT '[]',
    -- Items rated 1-2 stars; used for exclusion in recommendations
    -- Example: [1, 8, 19] (item_ids)
    
    preference_vector         JSONB DEFAULT '{}',      
    -- Raw scores map for collaborative filtering
    -- Example: {item_1: 85, item_2: 72, item_3: 45, ...}
    -- All items with their scores (time-decayed)
    
    cached_recommendations    JSONB DEFAULT NULL,
    -- Cached recommendation response to avoid recomputing
    -- Structure: {recommended_items: [...], recommended_deals: [...]}
    -- Set to NULL when cache expires
    
    cached_recommendations_ts TIMESTAMP DEFAULT NULL,
    -- Timestamp when cache was generated
    -- Cache expires after 30 minutes
    
    last_updated              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_profiles_user_id ON user_profiles(user_id);
CREATE INDEX idx_user_profiles_updated ON user_profiles(last_updated);
CREATE INDEX idx_user_profiles_cache_ts ON user_profiles(cached_recommendations_ts);
```

### Existing Tables Used (Read-Only)

| Table | Columns Used | Purpose |
|---|---|---|
| `feedback` | `user_id`, `item_id` or `deal_id`, `rating`, `created_at` | Item/deal ratings with timestamps for time decay |
| `favourites` | `user_id`, `item_id`, `created_at` | Explicit "I like this" signals |
| `order_items` | `user_id`, `item_id`, `order_id`, `created_at` | Purchase history with dates for time decay |
| `orders` | `order_id`, `created_at` | Order timestamps |
| `custom_deal_items` | `soft_rating`, `item_id`, `deal_id` | Soft ratings within custom deals |
| `menu_item` | `item_id`, `item_name`, `category`, `description` | Item details for embeddings |
| `deal` | `deal_id`, `deal_name`, `description` | Deal details for embeddings |

---

## Layer 2 — Preference Score Builder

**File:** `agents/personalization/score_builder.py`

Runs per user, produces a scored item map stored in `user_profiles.preference_vector`.

### Scoring Algorithm with Time Decay

For each menu item, calculate a composite score with time decay applied to historical interactions:

```
score = 0
current_date = today

# Explicit feedback signals
IF item is favourited by user:
    score += 40

IF average rating for item >= 4 stars:
    score += 30
ELIF average rating 2-3 stars:
    score += 10
    
IF average rating <= 1 star:
    score -= 40  # Strong negative signal

# Purchase frequency signals WITH TIME DECAY
FOR each order of this item:
    days_ago = current_date - order_date
    
    IF days_ago <= 30 days:
        decay_multiplier = 1.0  # Full weight for recent orders
    ELIF days_ago <= 90 days:
        decay_multiplier = 0.7  # 70% weight for recent-ish orders
    ELIF days_ago <= 180 days:
        decay_multiplier = 0.4  # 40% weight for older orders
    ELSE:
        decay_multiplier = 0.1  # 10% weight for very old orders
    
    IF order_count >= 3:
        score += (20 * decay_multiplier)
    ELIF order_count 1-2:
        score += (10 * decay_multiplier)

# Soft rating signals
IF soft_rating >= 4 in any custom deal:
    score += 15

# Result
store score in user_profiles.preference_vector
```

### Scoring Weights Breakdown

| Signal | Weight | Rationale |
|---|---|---|
| Favourited | +40 | Strongest explicit intent |
| Rating 4-5★ | +30 | Strong satisfaction feedback |
| Rating 1-2★ | -40 | Explicit dissatisfaction; suppress |
| Order 3+ times (time-decayed) | +20 | Repeat purchase = clear preference (recent orders count more) |
| Order 1-2 times (time-decayed) | +10 | Mild preference (recent orders count more) |
| Soft rating ≥4 | +15 | Contextual preference within deals |

### Time Decay Rationale

Users change preferences over time. Zinger Burger ordered 5 times 6 months ago may not be relevant now if they've since discovered BBQ. Time decay ensures:
- Recent orders heavily influence recommendations
- Old orders still matter but with reduced weight
- Gradual drift in user preferences is captured naturally

### Recommendation Prioritization Tiers

Recommendations are ranked in this order:

1. **Tier 1: Favourited + Highly Rated** — Always show first (score 70+)
2. **Tier 2: Highly Rated (4-5★) but not favourited** — Strong suggestions (score 50-69)
3. **Tier 3: Frequently Ordered (Recent), not rated** — Safe repeats (score 30-49)
4. **Tier 4: Same Cuisine as Past Orders** — Discovery within comfort zone (score 20-29)
5. **Tier 5: Never Ordered** — Pure discovery, shown last (score <20)

### Trigger Points

Score builder is called as `BackgroundTask` after:
- `POST /feedback` — user rates an item
- `POST /favourites/toggle` — user adds/removes favourite
- `POST /orders` — new order placed (may contain new items)

```python
# Example trigger in feedback_routes.py
from fastapi import BackgroundTasks

@router.post("/feedback")
async def submit_feedback(feedback: FeedbackRequest, background_tasks: BackgroundTasks):
    # Save feedback to DB
    save_feedback(feedback)
    
    # Invalidate cached recommendations
    invalidate_cache(feedback.user_id)
    
    # Schedule score rebuild
    background_tasks.add_task(
        score_builder.rebuild_user_profile, 
        user_id=feedback.user_id
    )
    
    return {"status": "feedback_received"}
```

---

## Layer 3 — FAISS Similarity Search

**File:** `agents/personalization/similarity_search.py`

Uses your existing FAISS index to find semantically similar items.

### How It Works

1. Extract user's **top scored items** from `user_profiles.top_items`
2. For each top item, get its embedding from FAISS index
3. Query FAISS for **K nearest neighbors** (K=5-10 similar items)
4. Filter out:
   - Items user already ordered
   - Items in disliked_items
5. Return as `similar_items` recommendations

### Example Flow

```
User Profile:
  top_items: [Zinger Burger (score 85), Crispy Fries (score 72)]

FAISS Query for "Zinger Burger":
  → Returns: [Chicken Burger, Crispy Burger, Zinger Deal, Beef Burger, Spicy Burger]
  
Filter (remove already ordered):
  → Remove: Zinger Burger (already has it)
  
Result: [Chicken Burger, Crispy Burger, Zinger Deal, Beef Burger, Spicy Burger]
```

### Integration with Existing FAISS

Your FAISS index is already built with menu item embeddings. The similarity search simply queries it with a similarity metric (cosine or L2).

**Existing path:** `faiss_index/menu_embeddings.index`  
**Existing vectors:** Item descriptions embedded via your existing pipeline

### FAISS Index Staleness Handling

When new menu items are added:
- Hook into admin menu management flow
- On `POST /admin/menu_items`, rebuild FAISS index asynchronously
- Use versioning to track index age; warn if index is >7 days old

---

## Layer 4 — Collaborative Filtering with Tiered Fallback

**File:** `agents/personalization/collaborative_filter.py`

Finds users with similar taste profiles and surfaces items they liked. **Includes graceful fallback when sparse data.**

### Algorithm

```
Step 1: Build User × Item Rating Matrix
  - Rows: all users
  - Columns: all items
  - Values: rating or 0 (not rated)
  - Result: sparse matrix (handle sparsity)

Step 2: Compute User Similarity
  - For each pair of users, compute cosine similarity
  - Similarity = cos(user_A_ratings, user_B_ratings)
  - Result: similarity scores between -1 and 1

Step 3: Find Similar Users
  - Get top 5-10 users most similar to current user
  - Only include users with similarity > 0.5

Step 4A: Extract Their Preferences
  - IF enough similar users found (≥ 3):
    - Collect items rated 4-5★ by similar users
    - Filter out items current user already ordered
    - Rank by frequency
    - Return as collab_filter_results
  
  ELSE (< 3 similar users found):
    - Set collab_filter_results = EMPTY
    - Caller will use fallback (FAISS similarity)
```

### Implementation Libraries

```python
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
```

### Trigger Points

Recalculated every 10 new feedback entries system-wide (tracked via a counter):

```python
# In score_builder.py after calculating scores
global_feedback_count += 1
if global_feedback_count % 10 == 0:
    collaborative_filter.rebuild_similarity_matrix()
    global_feedback_count = 0
```

Alternative: Cron job runs collaborative filter rebuild daily at off-peak hours (e.g., 2 AM).

### Cold Start & Sparse Data Handling

For new users or systems with sparse data:
- Collaborative filtering may find 0 similar users
- Instead of returning nothing, system falls back to FAISS similarity
- If FAISS is also weak, system falls back to popularity-based recommendations

**This is by design — graceful degradation.**

---

## Layer 4B — Tiered Recommendation Fallback

**File:** `agents/personalization/recommendation_fallback.py`

When collab filter is weak, use this serving order:

```python
def get_recommendations(user_id):
    # Try collab filter first
    collab_results = collaborative_filter.get_suggestions(user_id)
    
    if collab_results and len(collab_results) >= 3:
        # Collab filter worked - use it
        use_results = collab_results
        source = "collaborative_filtering"
    
    elif similarity_results := faiss_similarity.find_similar(user_id):
        # Collab filter weak, use FAISS
        use_results = similarity_results
        source = "faiss_similarity"
    
    else:
        # FAISS also weak, use popularity
        use_results = popularity_based.get_trending(
            cuisine=user_profile.preferred_cuisines[0] if user_profile.preferred_cuisines else None
        )
        source = "popularity_based"
    
    return use_results, source
```

### Recommendation Sources Explained

| Source | When Used | Quality |
|---|---|---|
| Collaborative Filtering | ≥3 similar users found with similarity >0.5 | 🟢 Best (learns from similar users) |
| FAISS Similarity | Collab weak, but top items have similar matches | 🟡 Good (semantic similarity) |
| Popularity-Based | Both above weak (new user, sparse data, edge case) | 🟡 Fair (trending items, safe fallback) |

### Popularity-Based Recommendations

For fallback, calculate weekly popularity:

```sql
SELECT 
    item_id, 
    COUNT(*) as order_count,
    AVG(COALESCE(f.rating, 3)) as avg_rating
FROM order_items oi
LEFT JOIN feedback f ON oi.item_id = f.item_id
WHERE oi.created_at >= NOW() - INTERVAL '7 days'
GROUP BY item_id
ORDER BY order_count DESC, avg_rating DESC
LIMIT 20;
```

---

## Layer 5 — LLM Decision Layer (Agent Brain)

**File:** `agents/personalization/personalization_agent.py`

This is the core AI agent that reasons over all signals and makes final decisions.

### Agent Architecture

Uses LLM (Gemini/GPT) to reason over structured preference data with error handling:

```python
from langchain.agents import Agent, Tool
from langchain.llms import ChatGemini
import json

class PersonalizationAgent:
    def __init__(self, llm):
        self.llm = llm
        self.tools = [
            Tool(name="get_scored_items", func=self.get_scored_items),
            Tool(name="get_similar_items", func=self.get_similar_items),
            Tool(name="get_collab_items", func=self.get_collab_items),
        ]
    
    def recommend(self, user_id: str) -> dict:
        try:
            # Get all signal sources
            scored_items = self.get_scored_items(user_id)
            similar_items = self.get_similar_items(user_id)
            collab_items, source = self.get_collab_items(user_id)
            
            # Call LLM with timeout
            recommendations = self.llm_reason(scored_items, similar_items, collab_items, source)
            
            # Validate LLM output
            recommendations = self.validate_recommendations(recommendations, user_id)
            
            return recommendations
        
        except Exception as e:
            # Fallback to deterministic ranking if LLM fails
            return self.fallback_ranking(user_id)
```

### Agent Task & Reasoning

**Input to LLM:**
```
User Profile:
- Favourite items: [Zinger Burger, Crispy Fries]
- Top scored cuisines: [Fast Food, BBQ]
- Disliked items: [Salad]
- Order frequency: ~2x per week, mostly lunch
- Last active: 2 hours ago

Recommendation Source: collaborative_filtering

FAISS Similar Items (to what user liked):
- Chicken Burger (similarity: 0.92)
- Crispy Burger (similarity: 0.88)
- Zinger Deal (similarity: 0.85)

Collaborative Filter Results (users like you enjoyed):
- Spicy Burger (liked by 4 similar users)
- Beef Combo (liked by 3 similar users)

Current time: Lunch hour

---
Task:
"Given this user's preferences and the recommendations above, 
select the best 5 items and 3 deals to display. 
For each recommendation, explain why it matches their preferences.
Exclude disliked items. Prioritize high-confidence matches.
Consider current time (lunch) if relevant.

Output MUST be valid JSON with this exact structure:
{
  \"recommended_items\": [
    {\"item_id\": <int>, \"item_name\": \"<string>\", \"score\": <0-100>, \"reason\": \"<string>\"}
  ],
  \"recommended_deals\": [
    {\"deal_id\": <int>, \"deal_name\": \"<string>\", \"score\": <0-100>, \"reason\": \"<string>\"}
  ]
}
"
```

**LLM Output:**
```json
{
  "recommended_items": [
    {
      "item_id": 3,
      "item_name": "Crispy Burger",
      "score": 92,
      "reason": "Similar to your favourite Zinger Burger with the same crispy texture you love"
    },
    {
      "item_id": 45,
      "item_name": "Chicken Burger",
      "score": 88,
      "reason": "You rated similar items highly; this is a new addition to our Fast Food menu"
    },
    {
      "item_id": 7,
      "item_name": "Spicy Burger",
      "score": 85,
      "reason": "Users with tastes similar to yours highly rated this spicy variant"
    },
    {
      "item_id": 12,
      "item_name": "BBQ Plate",
      "score": 78,
      "reason": "Matches your BBQ cuisine preference"
    },
    {
      "item_id": 20,
      "item_name": "Fries & Dip",
      "score": 75,
      "reason": "A great complement to any burger; you ordered similar items 3+ times"
    }
  ],
  "recommended_deals": [
    {
      "deal_id": 2,
      "deal_name": "Fast Duo",
      "score": 88,
      "reason": "Perfect combo of your two favourite cuisines at a great price"
    },
    {
      "deal_id": 8,
      "deal_name": "Lunch Special",
      "score": 82,
      "reason": "Available now during your usual lunch hour; great value"
    },
    {
      "deal_id": 5,
      "deal_name": "Spicy Challenge",
      "score": 75,
      "reason": "Users similar to you loved this deal; new experience for you"
    }
  ]
}
```

### LLM Integration with Error Handling

```python
from langchain.chat_models import ChatGemini
import json
import re

def get_recommendations(user_id: str):
    # Gather all signals
    scored_items = score_builder.get_user_scores(user_id)
    similar_items = similarity_search.find_similar(user_id)
    collab_items, source = collaborative_filter.get_suggestions(user_id)
    
    # Build context for LLM
    context = build_context(scored_items, similar_items, collab_items, source)
    
    try:
        # LLM reasoning with timeout
        llm = ChatGemini(model_name="gemini-2.0-flash", temperature=0.3)
        prompt = f"""
        You are a restaurant recommendation AI. Analyze this user's preferences:
        
        {context}
        
        Return a JSON with recommended_items (5) and recommended_deals (3).
        Each must include: id, name, score (0-100), reason (human-readable).
        IMPORTANT: Return ONLY valid JSON, no markdown formatting.
        """
        
        response = llm.predict(prompt, timeout=5)
        
        # Try to parse JSON
        try:
            recommendations = json.loads(response)
        except json.JSONDecodeError:
            # If LLM returned markdown or other format, try to extract JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                recommendations = json.loads(json_match.group())
            else:
                raise ValueError("Could not parse LLM response as JSON")
        
        # Validate all item_ids exist in database
        recommendations = validate_item_ids(recommendations, user_id)
        
        return recommendations
    
    except Exception as e:
        # Fallback to deterministic ranking
        logger.warning(f"LLM recommendation failed for user {user_id}: {e}")
        return fallback_ranking(user_id)


def validate_item_ids(recommendations: dict, user_id: str) -> dict:
    """Ensure all recommended item_ids actually exist in database."""
    valid_items = db.query(MenuItem).all()
    valid_item_ids = {item.item_id for item in valid_items}
    valid_deal_ids = {deal.deal_id for deal in db.query(Deal).all()}
    
    # Filter out any items with invalid IDs
    recommendations["recommended_items"] = [
        item for item in recommendations["recommended_items"]
        if item["item_id"] in valid_item_ids
    ]
    recommendations["recommended_deals"] = [
        deal for deal in recommendations["recommended_deals"]
        if deal["deal_id"] in valid_deal_ids
    ]
    
    return recommendations


def fallback_ranking(user_id: str) -> dict:
    """Deterministic ranking when LLM fails - pure score-based."""
    profile = db.query(UserProfile).filter_by(user_id=user_id).first()
    
    if not profile or not profile.top_items:
        # Brand new user - return popularity
        return popularity_based.get_trending()
    
    # Rank by scores from Layer 2
    recommended_items = sorted(profile.top_items, key=lambda x: x["score"], reverse=True)[:5]
    recommended_deals = sorted(profile.top_deals, key=lambda x: x["score"], reverse=True)[:3]
    
    # Add generic reason since no LLM
    for item in recommended_items:
        item["reason"] = f"Based on your preferences (score: {item['score']})"
    for deal in recommended_deals:
        deal["reason"] = f"Based on your preferences (score: {deal['score']})"
    
    return {
        "recommended_items": recommended_items,
        "recommended_deals": recommended_deals,
        "fallback": True
    }
```

---

## Layer 6 — API Endpoints with Caching

**File:** `agents/personalization/personalization_routes.py`

### GET `/personalization/recommendations`

Fetch personalized recommendations with caching.

```python
@router.get("/personalization/recommendations")
async def get_recommendations(
    user_id: UUID = Depends(get_current_user)
):
    """
    Returns 5 recommended items and 3 recommended deals for the user.
    Uses 30-minute cache to avoid repeated computation.
    
    Response:
    {
      "recommended_items": [...],
      "recommended_deals": [...],
      "generated_at": "2026-03-18T08:00:00Z",
      "from_cache": false
    }
    """
    
    # Check if user profile exists; build if not
    profile = db.query(UserProfile).filter_by(user_id=user_id).first()
    
    if not profile:
        # New user
        score_builder.build_user_profile(user_id)
        profile = db.query(UserProfile).filter_by(user_id=user_id).first()
    
    # Check profile staleness (older than 24 hours → force rebuild)
    if profile.last_updated < datetime.utcnow() - timedelta(hours=24):
        score_builder.build_user_profile(user_id)
        profile = db.query(UserProfile).filter_by(user_id=user_id).first()
    
    # Check cache validity (30 minute TTL)
    if (profile.cached_recommendations and 
        profile.cached_recommendations_ts and
        datetime.utcnow() - profile.cached_recommendations_ts < timedelta(minutes=30)):
        
        recommendations = profile.cached_recommendations
        from_cache = True
    
    else:
        # Cache miss or expired - compute fresh recommendations
        recommendations = personalization_agent.recommend(user_id)
        
        # Store in cache
        profile.cached_recommendations = recommendations
        profile.cached_recommendations_ts = datetime.utcnow()
        db.commit()
        
        from_cache = False
    
    return {
        "recommended_items": recommendations["recommended_items"],
        "recommended_deals": recommendations["recommended_deals"],
        "generated_at": profile.cached_recommendations_ts.isoformat(),
        "from_cache": from_cache
    }
```

### POST `/personalization/refresh` (Internal)

Force-rebuild user profile and invalidate cache.

```python
@router.post("/personalization/refresh")
async def refresh_profile(
    user_id: UUID,
    api_key: str = Header(...),  # Internal API key required
    background: bool = Query(False)
):
    """
    Force rebuild user profile and invalidate cache.
    
    Query params:
    - background: if True, run rebuild asynchronously
    """
    if not validate_internal_api_key(api_key):
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    if background:
        # Run in background
        BackgroundTasks().add_task(
            score_builder.build_user_profile,
            user_id=user_id
        )
        return {"status": "refresh_queued"}
    
    else:
        # Run synchronously
        score_builder.build_user_profile(user_id)
        
        # Invalidate cache
        profile = db.query(UserProfile).filter_by(user_id=user_id).first()
        if profile:
            profile.cached_recommendations = None
            profile.cached_recommendations_ts = None
            db.commit()
        
        return {"status": "profile_refreshed"}
```

### Endpoint Registration

In `main.py`:

```python
from agents.personalization.personalization_routes import router as personalization_router

app.include_router(personalization_router, prefix="/api/v1", tags=["personalization"])
```

---

## Layer 6B — Stale Profile Recovery

**File:** `agents/personalization/stale_profile_handler.py`

Prevents silent data rot — detects and recovers stale profiles:

```python
import logging
from datetime import datetime, timedelta

def check_and_recover_stale_profile(user_id: str, force: bool = False) -> bool:
    """
    Check if user profile is stale. If stale (>24 hours without update),
    force rebuild synchronously before returning recommendations.
    
    Returns: True if profile was rebuilt, False if fresh
    """
    profile = db.query(UserProfile).filter_by(user_id=user_id).first()
    
    if not profile:
        # New user - build profile
        score_builder.build_user_profile(user_id)
        logging.info(f"Built new profile for user {user_id}")
        return True
    
    time_since_update = datetime.utcnow() - profile.last_updated
    stale_threshold = timedelta(hours=24)
    
    if time_since_update > stale_threshold or force:
        logging.warning(
            f"Profile stale for user {user_id} "
            f"({time_since_update.total_seconds() / 3600:.1f} hours old) - force rebuilding"
        )
        score_builder.build_user_profile(user_id)
        return True
    
    return False
```

---

## Layer 7 — Flutter Integration

### Service Layer

**File:** `lib/services/personalization_service.dart`

```dart
class PersonalizationService {
  final ApiClient _apiClient;
  
  PersonalizationService(this._apiClient);
  
  Future<RecommendationResult> getRecommendations() async {
    try {
      final response = await _apiClient.get(
        '/personalization/recommendations',
      );
      return RecommendationResult.fromJson(response.data);
    } catch (e) {
      throw Exception('Failed to fetch recommendations: $e');
    }
  }
}
```

### UI Widget

**File:** `lib/screens/home/widgets/recommended_section.dart`

```dart
class RecommendedForYouSection extends StatefulWidget {
  @override
  State<RecommendedForYouSection> createState() => _RecommendedForYouSectionState();
}

class _RecommendedForYouSectionState extends State<RecommendedForYouSection> {
  late Future<RecommendationResult> _recommendations;
  
  @override
  void initState() {
    super.initState();
    _recommendations = _personalizationService.getRecommendations();
  }
  
  @override
  Widget build(BuildContext context) {
    return FutureBuilder<RecommendationResult>(
      future: _recommendations,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return ShimmerLoading();
        }
        
        if (snapshot.hasError) {
          return SizedBox.shrink();  // Silently fail - no broken UI
        }
        
        final recommendations = snapshot.data!;
        
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                'Recommended For You',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
            ),
            SizedBox(
              height: 200,
              child: ListView.builder(
                scrollDirection: Axis.horizontal,
                itemCount: recommendations.recommendedItems.length,
                itemBuilder: (context, index) {
                  final item = recommendations.recommendedItems[index];
                  return RecommendationCard(
                    item: item,
                    reason: item.reason,
                    onTap: () => _addToCart(item),
                  );
                },
              ),
            ),
          ],
        );
      },
    );
  }
}
```

### Integration in Home Screen

**File:** `lib/screens/home/home_screen.dart`

```dart
@override
Widget build(BuildContext context) {
  return Scaffold(
    body: SingleChildScrollView(
      child: Column(
        children: [
          HeaderSection(),
          CategoriesSection(),
          RecommendedForYouSection(),  // NEW
          PromotionalBanner(),
        ],
      ),
    ),
  );
}
```

---

## Data Flow Summary

```
┌──────────────────────────────────────────────────────┐
│   User Actions (Order, Rate, Favourite)              │
└──────────────────┬─────────────────────────────────┘
                   │
                   ↓
      ┌────────────────────────────────┐
      │ Cache Invalidated              │
      │ Background Rebuild Scheduled   │
      └────────────┬───────────────────┘
                   │
                   ↓
    ┌──────────────────────────────────────┐
    │ Layer 2: Score Builder               │
    │ Apply time decay to all interactions │
    │ Calculate preference scores          │
    │ Store in user_profiles              │
    └────────────┬─────────────────────────┘
                 │
         ┌───────┴───────────────────────┐
         │                               │
         ↓                               ↓
    Layer 3:                        Layer 4:
    FAISS Search                    Collaborative
    Find similar                    Filter
    items (semantic)                (user-based)
         │                               │
         └───────┬───────────────────────┘
                 │
                 ↓
    ┌─────────────────────────────────────────┐
    │ Layer 4B: Tiered Fallback               │
    │ If collab strong → use it              │
    │ Else if FAISS strong → use it          │
    │ Else → use popularity-based            │
    └────────────┬────────────────────────────┘
                 │
                 ↓
    ┌─────────────────────────────────────┐
    │ Layer 5: LLM Agent                  │
    │ Reason over all signals             │
    │ Fallback to deterministic if LLM    │
    │ fails                               │
    │ Validate item_ids                   │
    └────────────┬────────────────────────┘
                 │
                 ↓
    ┌─────────────────────────────────────┐
    │ Layer 6: API Response + Cache       │
    │ Store in cache_recommendations      │
    │ 30-min TTL                          │
    │ GET /personalization/               │
    └────────────┬────────────────────────┘
                 │
                 ↓
    ┌─────────────────────────────────────┐
    │ Layer 7: Flutter UI                 │
    │ Display "Recommended For You"       │
    │ with reason tags                    │
    └─────────────────────────────────────┘
                 │
                 ↓
    ┌─────────────────────────────────────┐
    │ (Future) Re-engagement Agent        │
    │ Reads user_profiles snapshots       │
    │ Sends tailored push notifications   │
    └─────────────────────────────────────┘
```

---

## File Structure

```
khadim/
├── backend/
│   ├── agents/
│   │   └── personalization/
│   │       ├── __init__.py
│   │       ├── score_builder.py               [Layer 2]
│   │       ├── similarity_search.py           [Layer 3]
│   │       ├── collaborative_filter.py        [Layer 4]
│   │       ├── recommendation_fallback.py     [Layer 4B]
│   │       ├── personalization_agent.py       [Layer 5]
│   │       ├── stale_profile_handler.py       [Layer 6B]
│   │       ├── personalization_routes.py      [Layer 6]
│   │       └── seed_fake_users.py             [Seeding]
│   ├── models/
│   │   └── user_profile.py
│   └── main.py (update to register routes)
│
└── mobile/
    └── lib/
        ├── services/
        │   └── personalization_service.dart   [Layer 7]
        └── screens/
            └── home/
                ├── home_screen.dart (update)
                └── widgets/
                    └── recommended_section.dart
```

---

## Implementation Risks & Mitigations

| Difficulty | Severity | When You'll Hit It | Mitigation Strategy |
|---|---|---|---|
| **Cold start (new users)** | 🔴 High | Day 1 testing | Popularity-based fallback until 3+ orders; don't show empty state |
| **Sparse data for collaborative filtering** | 🔴 High | Early testing | Seed 50-100 fake users with realistic order patterns before demo |
| **FAISS index goes stale** | 🟡 Medium | After menu changes | Hook into admin menu management; rebuild index on menu item create/update |
| **LLM returns malformed JSON** | 🔴 High | Phase 3 testing | Wrap in try/catch; regex extract JSON from markdown; fallback to deterministic ranking |
| **Background task silent failure** | 🟡 Medium | Phase 1 testing | Check profile staleness (>24h) on every request; force rebuild if needed |
| **Score drift (old preferences)** | 🟡 Medium | After extended use | Apply time decay to interactions >30 days old; orders >6 months get 10% weight |
| **Slow home screen loads (6+ seconds)** | 🔴 High | Phase 4 Flutter testing | Cache recommendations for 30 minutes; refresh asynchronously after feedback |
| **Recommendation caching bugs** | 🟡 Medium | Phase 4 testing | Invalidate cache immediately when feedback/favourites posted |
| **Collab filter returns empty** | 🟡 Medium | Sparse user scenarios | Tiered fallback: FAISS → popularity; ensure caller never gets empty |

---

## Fake User Seeding Strategy

**File:** `agents/personalization/seed_fake_users.py`

Seed realistic fake users to provide collaborative filtering with enough signal:

```python
from faker import Faker
from datetime import datetime, timedelta
import random

def seed_fake_users(count: int = 75):
    """
    Create N fake users with realistic order histories.
    Run ONCE before demo day.
    """
    fake = Faker()
    
    for i in range(count):
        # Create user
        user = create_test_user(
            email=f"fakeuser{i}@test.com",
            name=fake.name()
        )
        
        # Create 5-15 orders spread across different cuisines
        order_count = random.randint(5, 15)
        for j in range(order_count):
            order = create_order(
                user_id=user.user_id,
                created_at=datetime.utcnow() - timedelta(days=random.randint(1, 180))
            )
            
            # Add 2-5 random items per order
            items = random.sample(get_all_menu_items(), random.randint(2, 5))
            for item in items:
                order_items.append({
                    "order_id": order.id,
                    "item_id": item.id
                })
            
            # Sometimes add rating (70% of orders)
            if random.random() < 0.7:
                for item in items:
                    create_feedback(
                        user_id=user.user_id,
                        item_id=item.id,
                        rating=random.choice([3, 4, 4, 5, 5])  # Biased towards positive
                    )
        
        # Add 2-5 favourites
        for _ in range(random.randint(2, 5)):
            favourite_item = random.choice(get_all_menu_items())
            create_favourite(user_id=user.user_id, item_id=favourite_item.id)
    
    print(f"Seeded {count} fake users with realistic order histories")

# Run once
if __name__ == "__main__":
    seed_fake_users(count=75)
```

**Duration:** ~5 minutes execution  
**Result:** 75 users × 10 orders × 3 items = 2,250 order items + 1,500+ ratings = sufficient matrix density for collaborative filtering

---

## Implementation Phases

### Phase 1: Foundation (Score Builder + Storage + Time Decay)
**Duration:** ~2-3 days

**Deliverables:**
- [ ] `user_profiles` table with cache columns created
- [ ] `score_builder.py` with time decay algorithm
- [ ] Background task triggers on feedback/favourites
- [ ] Stale profile detection in middleware
- [ ] Cache invalidation on user action
- [ ] No UI yet; validation via database inspection

**Testing:**
- Verify scores calculated with time decay
- Confirm recent orders weighted higher than old
- Test stale profile forces rebuild
- Check cache invalidation works

---

### Phase 2: Similarity + Collaborative Filtering + Fallback
**Duration:** ~3-4 days

**Deliverables:**
- [ ] `similarity_search.py` queries FAISS
- [ ] `collaborative_filter.py` with tiered fallback
- [ ] `recommendation_fallback.py` orchestrates fallback logic
- [ ] Popularity-based recommendations as final fallback
- [ ] API endpoint `/personalization/recommendations` returns combined results
- [ ] Fake user seeding script (`seed_fake_users.py`) ready
- [ ] LLM reasoning layer stubbed (still returns scores without LLM)

**Testing:**
- Run seeding script; verify 75 fake users exist with orders/ratings
- Verify collab filter finds similar users when enough data
- Verify fallback to FAISS when collab weak
- Verify fallback to popularity when both weak
- Check FAISS returns correct neighbors

---

### Phase 3: LLM Agent + Validation + Error Handling
**Duration:** ~2-3 days

**Deliverables:**
- [ ] `personalization_agent.py` with LLM integration
- [ ] Agent reasons over all signals
- [ ] Validates LLM JSON output with regex/exception handling
- [ ] Fallback to deterministic ranking if LLM fails
- [ ] Item ID validation against database
- [ ] API returns ranked recommendations with reasons
- [ ] Timeout handling on LLM calls

**Testing:**
- Verify LLM receives correct context
- Test JSON parsing with malformed responses
- Verify fallback ranking works
- Check timeout after 5 seconds
- Validate all item_ids exist in DB

---

### Phase 4: Recommendation Caching + Flutter UI
**Duration:** ~1-2 days

**Deliverables:**
- [ ] Cache storage in `user_profiles.cached_recommendations`
- [ ] 30-minute TTL on cache
- [ ] Cache invalidation on feedback/favourites
- [ ] `personalization_service.dart` fetches recommendations
- [ ] `RecommendedForYouSection` widget displays results with reasons
- [ ] Integrated into home screen
- [ ] Loading states (shimmer) and error handling

**Testing:**
- Visual verification on device
- Check cache hit/miss behavior
- Verify cache invalidation works
- Performance: home screen load <1s with cache
- Tap to add to cart works

---

### Phase 5: ML Model (Optional — Future Work)
**Duration:** ~4-5 days

**Deliverables:**
- [ ] Matrix factorization (SVD) implementation
- [ ] Weekly retraining pipeline
- [ ] Model serving layer
- [ ] Performance benchmarks vs Phase 2 collaborative filtering

**Testing:**
- Compare recommendation quality before/after
- Measure training time
- Monitor model drift

---

## Critical Success Factors

1. **Time Decay Scoring** — Must correctly weight recent interactions
2. **Database Indexing** — `user_profiles(user_id)` and cache timestamps indexed
3. **Background Task Reliability** — Score rebuilds must complete even if one user fails
4. **Tiered Fallback** — Never return empty recommendations; graceful degradation
5. **FAISS Performance** — Queries <100ms; index pre-loaded on startup
6. **LLM Error Handling** — Timeout + validation + fallback to deterministic ranking
7. **Cache Invalidation** — Must happen immediately on user action
8. **Fake User Seeding** — Must run before demo to enable collaborative filtering
9. **Real-time Personalization** — Scores update within seconds of feedback
10. **Stale Profile Recovery** — Automatic rebuild if profile >24h old

---

## Testing Strategy

### Unit Tests
- Score builder: verify time decay weights applied correctly
- Score builder: verify old orders weighted lower than recent
- Similarity search: confirm FAISS returns correct neighbors
- Collaborative filter: test with mock rating matrices
- Fallback logic: confirm fallback chain works (collab → FAISS → popularity)
- LLM validation: test JSON parsing with malformed inputs

### Integration Tests
- End-to-end: user rates item → profile updates → cache invalidates → API returns fresh recommendations
- Cold start: new user → popularity fallback recommendations
- Sparse data: few users → collab filter empty → FAISS returns results
- Cache: first request computes; second within 30min returns cached; after 30min recomputes
- Time decay: old orders gradually decrease in score

### Load Tests
- 100 concurrent recommendation requests
- FAISS query latency at scale
- Database query performance with cache hits

### Demo Day Tests
- Fake users seeded (75 users with histories)
- New user cold start experience
- Collab filter working with seeded data
- Fallback chains working end-to-end
- Flutter UI loads with recommendations in <1s (from cache)

---

## Future Enhancements

1. **Time-Based Personalization** — Different recommendations for breakfast vs lunch vs dinner
2. **Group Recommendations** — Family orders → suggest items for multiple people
3. **Seasonal Trends** — Boost seasonal items during relevant months
4. **A/B Testing** — Compare recommendation strategies; measure CTR
5. **Real-time Dashboard** — Admin panel showing recommendation quality metrics
6. **SVD Matrix Factorization** — Phase 5 ML model for improved latent factors
7. **Trending Items** — "What's Hot" category updated hourly
8. **Item Lifecycle** — New items given visibility boost for first 2 weeks

---

## References & Resources

- **FAISS Documentation:** https://github.com/facebookresearch/faiss
- **Scikit-learn Collaborative Filtering:** https://scikit-learn.org/
- **LangChain Agents:** https://docs.langchain.com/docs/modules/agents/
- **Matrix Factorization (SVD):** https://en.wikipedia.org/wiki/Singular_value_decomposition
- **Time Decay in Recommendations:** https://en.wikipedia.org/wiki/Temporal_dynamics
- **Cold Start Problem:** https://en.wikipedia.org/wiki/Cold_start_(recommender_systems)

---

**Document Version:** 2.0  
**Last Updated:** March 18, 2026  
**Status:** Ready for Phase 1 Implementation  
**Key Changes from v1.0:**
- Added time decay scoring algorithm
- Added tiered recommendation fallback (collab → FAISS → popularity)
- Added caching layer with 30-minute TTL
- Added stale profile recovery mechanism
- Added LLM error handling with fallback
- Added fake user seeding strategy
- Added implementation risks table with all 9 mitigations
- Enhanced collaborative filtering with graceful fallback
- Production-ready error handling throughout

**Next Steps:** 
1. Push this MD to repo
2. Run fake user seeding script