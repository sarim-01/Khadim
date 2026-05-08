import os
import json
import random
import sys
import time
from decimal import Decimal

try:
    from dotenv import load_dotenv
    from langchain_groq import ChatGroq
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.messages import SystemMessage, HumanMessage
    from psycopg2.extras import RealDictCursor
    from infrastructure.database_connection import DatabaseConnection
    from infrastructure.redis_connection import RedisConnection
    from infrastructure.config import AGENT_TASKS_CHANNEL
    
    # NEW IMPORTS FOR VECTOR SEARCH
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document
except ImportError as e:
    print(f"FATAL: Missing library: {e}")
    sys.exit(1)

load_dotenv()

# --- CONFIG FOR VECTOR STORE ---
FAISS_INDEX_PATH = "faiss_index"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

class CustomDealAgent:
    def __init__(self):
        print("[DealAgent] Initializing...")
        self.db = DatabaseConnection.get_instance()
        self.llm = ChatGroq(model="llama-3.1-8b-instant", api_key=os.getenv("GROQ_API_KEY"))
        
        # Initialize Vector Store for Semantic Search
        try:
            self.embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
            self.vectorstore = FAISS.load_local(
                FAISS_INDEX_PATH, 
                self.embeddings, 
                allow_dangerous_deserialization=True
            )
            print("[DealAgent] Vector Store Loaded (OK)")
        except FileNotFoundError:
            print(f"[DealAgent] WARN: Vector Store index not found at '{FAISS_INDEX_PATH}'. Please run 'python vector_store.py' to create it.")
            self.vectorstore = None
        except Exception as e:
            print(f"[DealAgent] WARN: Vector Store failed to load: {e}")
            print("[DealAgent] Falling back to SQL search only. Run 'python vector_store.py' to fix semantic search.")
            self.vectorstore = None

    def _extract_json(self, text):
        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != -1:
                return json.loads(text[start:end])
            return json.loads(text)
        except Exception:
            return None

    def _parse_requirements(self, user_query: str):
        print(f"[DealAgent] Parsing query: {user_query}")

        system_prompt = """
        You are a Deal Architect. Extract requirements from the user's custom deal request.
        Output ONLY valid JSON.

        EXTRACTION RULES:
        - "explicit_items": Extract food item names/keywords the user specifically mentions.
          Examples:
          "biryani and burger" -> ["biryani", "burger"]
          "burger deal for 2" -> ["burger"]
          "zinger combo for 3" -> ["zinger"]
          "chicken items" -> ["chicken"]
          "fast food" -> []

        - "num_people": Extract if user mentions "X person deal", "for 3 people", "for 2", etc.
          Default: 1

        - "cuisine": Extract cuisine preference if mentioned or strongly implied.
          Use these exact values:
          "Desi"
          "Fast Food"
          "Chinese"
          "BBQ"
          "Drinks"

          IMPORTANT INFERENCE RULES:
          - burger, zinger, fries, pizza, wings, sandwich -> "Fast Food"
          - biryani, karahi, handi, naan, roti, desi, pakistani -> "Desi"
          - bbq, tikka, boti, kebab, grilled -> "BBQ"
          - chowmein, fried rice, manchurian -> "Chinese"

        - "category": Extract category if directly mentioned: "main", "appetizer", "drinks", etc.

        - "needs_clarification": true only if the request is too vague to build a deal.
          If user provides both an item/cuisine hint and person count, DO NOT ask for clarification.

        - "clarification_type": one of:
          "items"
          "cuisine"
          "count"

        JSON SCHEMA:
        {
            "explicit_items": ["item1", "item2"],
            "num_people": 1,
            "cuisine": null,
            "category": null,
            "needs_clarification": false,
            "clarification_type": null
        }

        EXAMPLES:

        Input: "Make me a deal with biryani and burger"
        Output: {"explicit_items": ["biryani", "burger"], "num_people": 1, "cuisine": null, "category": null, "needs_clarification": false, "clarification_type": null}

        Input: "Create a 3 person deal"
        Output: {"explicit_items": [], "num_people": 3, "cuisine": null, "category": null, "needs_clarification": true, "clarification_type": "cuisine"}

        Input: "I want a Pakistani food deal"
        Output: {"explicit_items": [], "num_people": 1, "cuisine": "Desi", "category": null, "needs_clarification": false, "clarification_type": null}

        Input: "make a custom deal for 3 people including fast food only"
        Output: {"explicit_items": [], "num_people": 3, "cuisine": "Fast Food", "category": null, "needs_clarification": false, "clarification_type": null}

        Input: "make a custom deal for 5 people including pakistani food"
        Output: {"explicit_items": [], "num_people": 5, "cuisine": "Desi", "category": null, "needs_clarification": false, "clarification_type": null}

        Input: "make a custom deal for 5 people including chinese food"
        Output: {"explicit_items": [], "num_people": 5, "cuisine": "Chinese", "category": null, "needs_clarification": false, "clarification_type": null}

        Input: "make a custom deal for 5 people including bbq food"
        Output: {"explicit_items": [], "num_people": 5, "cuisine": "BBQ", "category": null, "needs_clarification": false, "clarification_type": null}

        Input: "burger deal for 2"
        Output: {"explicit_items": ["burger"], "num_people": 2, "cuisine": "Fast Food", "category": null, "needs_clarification": false, "clarification_type": null}

        Input: "bbq combo for 3"
        Output: {"explicit_items": [], "num_people": 3, "cuisine": "BBQ", "category": null, "needs_clarification": false, "clarification_type": null}

        Input: "Pakistani meal for 4"
        Output: {"explicit_items": [], "num_people": 4, "cuisine": "Desi", "category": null, "needs_clarification": false, "clarification_type": null}
        """

        try:
            # Use direct messages (not ChatPromptTemplate) so that curly braces
            # inside the JSON examples in `system_prompt` are NOT interpreted as
            # template variables. This avoids the "missing variables" runtime error.
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_query),
            ])
            data = self._extract_json(response.content)
            print(f"[DealAgent] Parsed requirements: {data}")

            return data if data else {
                "explicit_items": [],
                "num_people": 1,
                "cuisine": None,
                "category": None,
                "needs_clarification": False,
                "clarification_type": None
            }
        except Exception as e:
            print(f"[DealAgent] Parse error: {e}")
            return {
                "explicit_items": [],
                "num_people": 1,
                "cuisine": None,
                "category": None,
                "needs_clarification": False,
                "clarification_type": None
            }

    def _rule_based_parse(self, user_query: str):
        query = (user_query or "").lower().strip()

        result = {
            "explicit_items": [],
            "num_people": 1,
            "cuisine": None,
            "category": None,
            "needs_clarification": False,
            "clarification_type": None
        }

        import re
        count_match = re.search(r'\b(\d+)\b', query)
        if count_match:
            result["num_people"] = int(count_match.group(1))

        if any(word in query for word in ["pakistani", "desi", "biryani", "karahi", "handi", "naan", "roti"]):
            result["cuisine"] = "Desi"
        elif any(word in query for word in ["burger", "zinger", "pizza", "fries", "wings", "sandwich", "fast food"]):
            result["cuisine"] = "Fast Food"
        elif any(word in query for word in ["bbq", "tikka", "boti", "kebab", "grilled"]):
            result["cuisine"] = "BBQ"
        elif any(word in query for word in ["chinese", "fried rice", "chowmein", "manchurian"]):
            result["cuisine"] = "Chinese"
        elif any(word in query for word in ["drink", "drinks", "beverage", "beverages", "juice", "tea"]):
            result["cuisine"] = "Drinks"

        known_items = [
            "burger", "zinger", "pizza", "biryani", "karahi", "handi",
            "fries", "wings", "sandwich", "tikka", "boti", "kebab",
            "fried rice", "chowmein", "manchurian",
            "shake", "margarita",
        ]
        # Qualifier words the user may have prepended to a dish keyword.
        # When we find one, upgrade the stored phrase so downstream
        # `_find_items_in_db` can ILIKE on the specific variant (e.g.
        # "chicken biryani" → Chicken Biryani, not Beef Biryani).
        qualifier_words = {
            "chicken", "beef", "mutton", "fish", "veggie", "veg",
            "zinger", "crispy", "spicy", "cheese", "cheesy",
            "malai", "tikka", "bbq", "grilled", "fried", "classic",
            "mint", "strawberry", "mango", "chocolate", "vanilla",
            "plain", "garlic", "butter", "paneer", "special",
        }

        import re as _re
        for item in known_items:
            if item not in query:
                continue
            # Look for "<qualifier> <item>" window in the raw query so we
            # can preserve the modifier. Fallback to the bare token.
            pattern = _re.compile(
                r"\b(?P<qual>\w+)\s+" + _re.escape(item) + r"\b"
            )
            m = pattern.search(query)
            if m and m.group("qual") in qualifier_words:
                phrase = f"{m.group('qual')} {item}"
                if phrase not in result["explicit_items"]:
                    # Drop any earlier bare entry for the same dish.
                    result["explicit_items"] = [
                        x for x in result["explicit_items"] if x != item
                    ]
                    result["explicit_items"].append(phrase)
            else:
                # Only add the bare token if no qualified version already
                # exists for the same dish keyword.
                already_qualified = any(
                    x.endswith(f" {item}") for x in result["explicit_items"]
                )
                if not already_qualified and item not in result["explicit_items"]:
                    result["explicit_items"].append(item)

        if result["cuisine"] is None and not result["explicit_items"]:
            result["needs_clarification"] = True
            result["clarification_type"] = "cuisine"

        return result

    def _normalize_cuisine(self, cuisine):
        """Map user-friendly cuisine names to database values."""
        if not cuisine:
            return None
        
        cuisine_lower = cuisine.lower()
        
        # Mapping from common terms to DB values
        cuisine_map = {
            "pakistani": "Desi",
            "desi": "Desi",
            "indian": "Desi",
            "fast food": "Fast Food",
            "fastfood": "Fast Food",
            "burger": "Fast Food",
            "chinese": "Chinese",
            "bbq": "BBQ",
            "barbecue": "BBQ",
            "grilled": "BBQ",
            "drinks": "Drinks",
            "beverages": "Drinks"
        }
        
        return cuisine_map.get(cuisine_lower, cuisine)  # Return original if no mapping found

    # --- NEW: SEMANTIC SEARCH HELPER ---
    def _semantic_search(self, query, limit=1):
        if not self.vectorstore: return []
        
        found_ids = []
        try:
            # Search Vector DB
            docs = self.vectorstore.similarity_search(query, k=limit)
            
            # Extract Item Name from the text block
            for doc in docs:
                text = doc.page_content
                # Parse "Menu Item: Zinger Burger" from the text block
                for line in text.split('\n'):
                    if "Menu Item:" in line:
                        name = line.split("Menu Item:")[1].strip()
                        found_ids.append(name)
                        break
        except Exception as e:
            print(f"[DealAgent] Vector Search Error: {e}")
            
        return found_ids

    def _find_items_in_db(self, names=None, tag=None, cuisine=None, category=None, limit=5):
        found_items = []
        
        with self.db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                
                # 1. SPECIFIC NAME SEARCH (HYBRID: SQL-first for phrases, FAISS fallback)
                #
                # Why SQL first when the name has >=2 words?
                #   The user said "chicken biryani" — an exact phrase. FAISS
                #   semantic search will happily map that to "Beef Biryani"
                #   because all biryanis cluster together in embedding space,
                #   overriding the qualifier the user explicitly gave us.
                #   SQL ILIKE '%chicken biryani%' uniquely hits Chicken
                #   Biryani, which is what the user actually asked for.
                #
                # For single-word tokens ("biryani", "karahi") FAISS is fine
                # as a first pass because there's no qualifier to honour.
                if names:
                    for name in names:
                        item = None
                        is_phrase = len(name.strip().split()) >= 2

                        if is_phrase:
                            # Phrase → try exact+ILIKE against the user's
                            # actual words first.
                            cur.execute(
                                "SELECT * FROM menu_item WHERE item_name ILIKE %s "
                                "AND availability = TRUE "
                                "ORDER BY LENGTH(item_name) ASC LIMIT 1",
                                (f"%{name}%",),
                            )
                            item = cur.fetchone()
                            if item:
                                print(f"[DealAgent] ILIKE Match: '{name}' -> '{item['item_name']}'")

                            # If that missed, FAISS as a safety net — but
                            # we still require the FAISS suggestion to
                            # contain at least one word of the user's
                            # phrase, so it can't return a random neighbour.
                            if not item:
                                semantic_matches = self._semantic_search(name, limit=3)
                                user_words = {w.lower() for w in name.split()}
                                for candidate in semantic_matches:
                                    cand_words = {w.lower() for w in candidate.split()}
                                    if user_words & cand_words:
                                        cur.execute(
                                            "SELECT * FROM menu_item WHERE item_name = %s "
                                            "AND availability = TRUE",
                                            (candidate,),
                                        )
                                        item = cur.fetchone()
                                        if item:
                                            print(f"[DealAgent] FAISS fallback: '{name}' -> '{candidate}'")
                                            break
                        else:
                            # Single-word token → original flow: FAISS first.
                            semantic_matches = self._semantic_search(name, limit=1)
                            if semantic_matches:
                                best_match_name = semantic_matches[0]
                                print(f"[DealAgent] Semantic Match: '{name}' -> '{best_match_name}'")
                                cur.execute(
                                    "SELECT * FROM menu_item WHERE item_name = %s "
                                    "AND availability = TRUE",
                                    (best_match_name,),
                                )
                                item = cur.fetchone()

                            if not item:
                                print(f"[DealAgent] Vector failed, trying SQL ILIKE for '{name}'...")
                                cur.execute(
                                    "SELECT * FROM menu_item WHERE item_name ILIKE %s "
                                    "AND availability = TRUE LIMIT 1",
                                    (f"%{name}%",),
                                )
                                item = cur.fetchone()

                        if item:
                            found_items.append(item)

                # 2. GENERIC FILLER SEARCH (SQL is better for categories)
                if (not names or not found_items) and (tag or cuisine or category):
                    query = "SELECT * FROM menu_item WHERE availability = TRUE"
                    params = []
                    if cuisine:
                        query += " AND item_cuisine = %s"
                        params.append(cuisine)
                    if category:
                        query += " AND item_category = %s"
                        params.append(category)
                    if tag:
                        query += " AND %s = ANY(tags)"
                        params.append(tag)
                    
                    query += " ORDER BY random() LIMIT %s"
                    params.append(limit)
                    cur.execute(query, tuple(params))
                    found_items.extend(cur.fetchall())

        return found_items

    # ----------------------------------------------------------------------
    # CATEGORY-SPECIFIC PICKERS
    # Each picker returns a list of (item_dict, qty) pairs — the quantity is
    # decided at selection time based on num_people and each item's
    # serving_size, so downstream code never has to re-infer it.
    # ----------------------------------------------------------------------

    @staticmethod
    def _serving_size(item):
        try:
            return max(1, int(item.get('serving_size') or 1))
        except (TypeError, ValueError):
            return 1

    def _pick_mains(self, num_people, cuisine, existing_ids):
        """
        Choose main dishes so the sum of (qty * serving_size) meets
        num_people as closely as possible — preferring variety over
        repetition, and never stacking multiple large-serving dishes on top
        of one that already feeds the group.

        Examples (num_people, typical serving sizes):
          3 people / mains s=[4,3,1,1,1] → picks [(handi, 1)]      (s=3 fits)
          3 people / mains s=[1,1,1,1]   → picks 3 distinct mains qty=1 each
          5 people / mains s=[4,3,1,1]   → picks [(karahi,1),(kebab,1)]
          6 people / mains s=[4,3,1]     → picks [(karahi,1),(handi,1)]  (+last boosted)
        """
        import math

        pool_limit = max(12, num_people * 3)
        candidates = self._find_items_in_db(
            cuisine=cuisine, category="main", limit=pool_limit
        ) if cuisine else self._find_items_in_db(category="main", limit=pool_limit)

        candidates = [c for c in candidates if c['item_id'] not in existing_ids]
        if not candidates:
            return []

        # Sort by serving_size DESC so big-group dishes are considered first.
        candidates.sort(key=self._serving_size, reverse=True)

        picks = []
        used = set(existing_ids)
        remaining = num_people

        # Cap variety at num_people so 3 people never end up with 5 dishes.
        max_distinct = max(1, num_people)

        while remaining > 0 and len(picks) < max_distinct:
            chosen = None
            # Preferred: largest dish whose serving_size <= remaining —
            # this avoids overshoot while still picking something substantial.
            for cand in candidates:
                if cand['item_id'] in used:
                    continue
                if self._serving_size(cand) <= remaining:
                    chosen = cand
                    break

            # Fallback: no dish fits exactly — pick the smallest available so
            # we don't balloon the deal. (Only happens when every remaining
            # candidate has serving_size > remaining.)
            if chosen is None:
                unused = [c for c in candidates if c['item_id'] not in used]
                if not unused:
                    break
                chosen = min(unused, key=self._serving_size)

            s_size = self._serving_size(chosen)
            picks.append((chosen, 1))
            used.add(chosen['item_id'])
            remaining -= s_size

        # Edge case: the pool was empty except for oversized dishes AND we
        # picked nothing. Take the single best one and scale it down.
        if not picks and candidates:
            top = candidates[0]
            s_size = self._serving_size(top)
            qty = max(1, math.ceil(num_people / s_size))
            return [(top, qty)]

        # Still unfed (e.g. only one distinct dish in DB)? Bump its qty.
        if remaining > 0 and picks:
            last_item, last_qty = picks[-1]
            s_size = self._serving_size(last_item)
            picks[-1] = (last_item, last_qty + math.ceil(remaining / s_size))

        return picks

    def _pick_drinks(self, num_people, existing_ids):
        """
        Drinks scale 1-per-person. We fetch 2–3 distinct variants (so the
        table gets variety) and distribute num_people cups across them.
        """
        # Decide how many distinct drinks to offer.
        if num_people <= 2:
            variants = 1
        elif num_people <= 5:
            variants = 2
        else:
            variants = 3

        pool = self._find_items_in_db(category="drink", limit=variants * 2)
        pool = [d for d in pool if d['item_id'] not in existing_ids]
        if not pool:
            return []

        chosen = pool[:variants]
        count = len(chosen)
        base, rem = divmod(num_people, count)
        picks = []
        for i, item in enumerate(chosen):
            qty = base + (1 if i < rem else 0)
            picks.append((item, max(1, qty)))
        return picks

    def _pick_sides(self, num_people, cuisine, existing_ids):
        """
        Sides are shareable — we want 2–3 distinct sides for 3+ people,
        just 1 for parties of 1–2. qty is always 1 per side.
        """
        if num_people <= 2:
            variants = 1
        elif num_people <= 5:
            variants = 2
        else:
            variants = 3

        if cuisine:
            pool = self._find_items_in_db(
                cuisine=cuisine, category="side", limit=variants * 2
            )
        else:
            pool = []

        if len(pool) < variants:
            pool += self._find_items_in_db(category="side", limit=variants * 2)

        picks = []
        used = set(existing_ids)
        for item in pool:
            if len(picks) >= variants:
                break
            if item['item_id'] in used:
                continue
            picks.append((item, 1))
            used.add(item['item_id'])
        return picks

    def _pick_bread(self, num_people, cuisine, existing_ids):
        """
        Bread is Desi-only and roughly 1-per-person, split across 1–2
        variants (e.g. naan + paratha).
        """
        if (cuisine or "").lower() != "desi":
            return []

        variants = 1 if num_people <= 2 else 2
        pool = self._find_items_in_db(
            cuisine="Desi", category="bread", limit=variants * 2
        )
        pool = [b for b in pool if b['item_id'] not in existing_ids]
        if not pool:
            return []

        chosen = pool[:variants]
        count = len(chosen)
        base, rem = divmod(num_people, count)
        picks = []
        for i, item in enumerate(chosen):
            qty = base + (1 if i < rem else 0)
            picks.append((item, max(1, qty)))
        return picks

    def _calculate_quantities(self, items_list, num_people):
        """
        Legacy entry point kept for backward compatibility. New flows assemble
        (item, qty) pairs directly via the category pickers above; this
        function now just applies sensible defaults when raw items arrive
        without explicit quantities (e.g. from the explicit-items search).
        """
        import math

        # Group by category so we can apply light serving-size balancing
        # across multiple mains picked without using the dedicated picker.
        cat_map = {}
        for item in items_list:
            cat = (item.get('item_category') or 'main').lower()
            cat_map.setdefault(cat, []).append(item)

        final_list = []

        for cat, items in cat_map.items():
            if cat == 'main':
                # Distribute across mains proportional to serving_size.
                remaining = max(1, num_people)
                ordered = sorted(items, key=self._serving_size, reverse=True)
                for idx, item in enumerate(ordered):
                    s_size = self._serving_size(item)
                    if remaining <= 0:
                        final_list.append((item, 1))
                        continue
                    if idx == len(ordered) - 1:
                        qty = math.ceil(remaining / s_size)
                    else:
                        qty = max(1, remaining // s_size)
                    final_list.append((item, qty))
                    remaining -= qty * s_size

            elif cat in ('drink', 'bread'):
                count = len(items)
                base, rem = divmod(num_people, count)
                for i, item in enumerate(items):
                    qty = base + (1 if i < rem else 0)
                    final_list.append((item, max(1, qty)))

            else:  # sides / appetizers / other — 1 per variant
                for item in items:
                    final_list.append((item, 1))

        return final_list

    def create_deal(self, user_query: str):
        try:
            user_query = (user_query or "").strip()
            if not user_query:
                empty_msg = (
                    "Please tell me what kind of deal you want, for example: "
                    "burger deal for 2 or Pakistani meal for 4."
                )
                return {
                    "success": False,
                    "needs_clarification": True,
                    "clarification_type": "items",
                    "message": empty_msg,
                    "message_en": empty_msg,
                    "message_voice": (
                        "What kind of deal would you like? For example, "
                        "a burger deal for two or a Pakistani meal for four."
                    ),
                }

            rule_reqs = self._rule_based_parse(user_query)
            llm_reqs = self._parse_requirements(user_query)

            # Prefer explicit items the user actually spoke. The translator
            # now hands us qualified phrases like "chicken biryani", so we
            # pick those (longer/more specific) over whatever the LLM guessed.
            merged_items = rule_reqs.get("explicit_items") or llm_reqs.get("explicit_items") or []

            # When the user named dishes, trust the rule parser's cuisine
            # (which is derived from those dish keywords) over the LLM's
            # opinion. The LLM is easily swayed by a mixed-cuisine query
            # like "biryani and burger" and can flip to Fast Food when the
            # user clearly wanted a Desi-led meal.
            if merged_items and rule_reqs.get("cuisine"):
                chosen_cuisine = rule_reqs["cuisine"]
            else:
                chosen_cuisine = llm_reqs.get("cuisine") or rule_reqs.get("cuisine")

            reqs = {
                "explicit_items": merged_items,
                "num_people": llm_reqs.get("num_people") or rule_reqs.get("num_people") or 1,
                "cuisine": chosen_cuisine,
                "category": llm_reqs.get("category") or rule_reqs.get("category"),
                "needs_clarification": llm_reqs.get("needs_clarification", False),
                "clarification_type": llm_reqs.get("clarification_type"),
            }

            if reqs["num_people"] == 1 and rule_reqs.get("num_people", 1) > 1:
                reqs["num_people"] = rule_reqs["num_people"]

            if rule_reqs.get("cuisine") or rule_reqs.get("explicit_items"):
                reqs["needs_clarification"] = False
                reqs["clarification_type"] = None

            print(f"[DealAgent] Final merged requirements: {reqs}")
            
            # Normalize cuisine to match database values
            if reqs.get("cuisine"):
                reqs["cuisine"] = self._normalize_cuisine(reqs["cuisine"])
                print(f"[DealAgent] Normalized cuisine to: {reqs['cuisine']}")
            
            # STEP 1: Check if clarification is needed
            # All three branches now return BOTH a rich markdown `message`
            # (for UI display) and a plain `message_voice` (for TTS). They
            # also carry `needs_clarification: True` so the Flutter client
            # routes the response to the clarification path without relying
            # purely on `success=false`.
            if reqs.get("needs_clarification"):
                clarification_type = reqs.get("clarification_type", "items")
                num_people = reqs.get("num_people", 1)
                people_word = "person" if num_people == 1 else "people"

                if clarification_type == "cuisine":
                    msg = (
                        f"I'd love to create a custom deal for {num_people} "
                        f"{people_word}! What type of food would you like?\n"
                        f"- Pakistani / Desi (Biryani, Karahi, Kebabs)\n"
                        f"- Fast Food (Burgers, Fries, Wings)\n"
                        f"- Chinese\n"
                        f"- BBQ"
                    )
                    voice = (
                        f"Which cuisine would you like for {num_people} "
                        f"{people_word}? Desi, fast food, Chinese, or BBQ?"
                    )
                elif clarification_type == "items":
                    msg = (
                        "I can create a custom deal for you. What items "
                        "would you like to include? For example: 'biryani "
                        "and burger' or 'Pakistani food'."
                    )
                    voice = (
                        "What items would you like in the deal? "
                        "For example, biryani, burger, or Pakistani food."
                    )
                else:  # count
                    msg = (
                        "How many people is this deal for? "
                        "I'll customise the portions accordingly."
                    )
                    voice = "How many people is this deal for?"

                return {
                    "success": False,
                    "needs_clarification": True,
                    "clarification_type": clarification_type,
                    "message": msg,
                    "message_en": msg,
                    "message_voice": voice,
                }
            
            # ──────────────────────────────────────────────────────────
            # STEP 2: Compose the deal, one category at a time
            # ──────────────────────────────────────────────────────────
            # Rules (driven by `num_people`):
            #
            #   MAINS  : enough for everyone, measured by `serving_size`.
            #            e.g. 3 people + karahi(s=3) = 1 karahi, not 3;
            #                 3 people + burger(s=1) = 3 different burgers.
            #   BREAD  : Desi cuisine only. 1 per person, split across
            #            1–2 variants (naan + paratha).
            #   SIDES  : 2–3 distinct sides for 3+ people (qty 1 each),
            #            1 side for ≤2 people.
            #   DRINKS : 1 per person, split across 1–3 variants.
            #
            # `items_with_quantities` accumulates (item_dict, qty) tuples —
            # the quantity is resolved at selection time so we never have to
            # re-infer portions later.
            num_people = max(1, int(reqs.get("num_people", 1) or 1))

            # Pick cuisine the same way as before.
            if reqs.get("cuisine"):
                primary_cuisine = reqs.get("cuisine")
                print(f"[DealAgent] Using explicit cuisine from user: {primary_cuisine}")
            else:
                primary_cuisine = None

            print(f"[DealAgent] Building deal for {num_people} people (cuisine={primary_cuisine})")

            items_with_quantities = []
            existing_ids = set()

            # STEP 2a — explicitly named items first (e.g. "with biryani").
            if reqs.get("explicit_items"):
                print(f"[DealAgent] Searching for explicit items: {reqs['explicit_items']}")
                explicit_items = self._find_items_in_db(names=reqs["explicit_items"])

                if not explicit_items:
                    items_str = ', '.join(reqs['explicit_items'])
                    print(f"[DealAgent] ERROR: Could not find any of the items: {items_str}")
                    miss_msg = (
                        f"I couldn't find '{items_str}' on our menu. "
                        "Could you try different items or let me suggest something?"
                    )
                    return {
                        "success": False,
                        "needs_clarification": True,
                        "clarification_type": "items",
                        "message": miss_msg,
                        "message_en": miss_msg,
                        "message_voice": (
                            f"I couldn't find {items_str} on our menu. "
                            "Would you like to try different items?"
                        ),
                    }

                # Scale the qty of each explicit item by serving_size so
                # "biryani" for 3 people doesn't become 3x biryani when one
                # platter already feeds the group.
                for item in explicit_items:
                    if item['item_id'] in existing_ids:
                        continue
                    s_size = self._serving_size(item)
                    if (item.get('item_category') or '').lower() == 'main':
                        from math import ceil
                        qty = max(1, ceil(num_people / s_size))
                    else:
                        qty = 1
                    items_with_quantities.append((item, qty))
                    existing_ids.add(item['item_id'])

                if not primary_cuisine and items_with_quantities:
                    primary_cuisine = items_with_quantities[0][0].get('item_cuisine')
                    print(f"[DealAgent] Cuisine inferred from explicit item: {primary_cuisine}")

            # STEP 2b — ensure the mains category covers the whole table.
            current_main_servings = sum(
                self._serving_size(it) * qty
                for it, qty in items_with_quantities
                if (it.get('item_category') or '').lower() == 'main'
            )
            if current_main_servings < num_people:
                remaining_people = num_people - current_main_servings
                extra_mains = self._pick_mains(
                    num_people=remaining_people,
                    cuisine=primary_cuisine,
                    existing_ids=existing_ids,
                )
                for item, qty in extra_mains:
                    items_with_quantities.append((item, qty))
                    existing_ids.add(item['item_id'])
                print(f"[DealAgent] Mains picked: {[(i['item_name'], q) for i, q in extra_mains]}")

            # STEP 2c — bread (Desi only, 1-per-person across 1–2 variants).
            has_bread = any(
                (it.get('item_category') or '').lower() == 'bread'
                for it, _ in items_with_quantities
            )
            if not has_bread:
                breads = self._pick_bread(num_people, primary_cuisine, existing_ids)
                for item, qty in breads:
                    items_with_quantities.append((item, qty))
                    existing_ids.add(item['item_id'])
                if breads:
                    print(f"[DealAgent] Bread picked: {[(i['item_name'], q) for i, q in breads]}")

            # STEP 2d — sides (2–3 distinct for 3+ people, qty 1 each).
            has_side = any(
                (it.get('item_category') or '').lower() == 'side'
                for it, _ in items_with_quantities
            )
            if not has_side:
                sides = self._pick_sides(num_people, primary_cuisine, existing_ids)
                for item, qty in sides:
                    items_with_quantities.append((item, qty))
                    existing_ids.add(item['item_id'])
                print(f"[DealAgent] Sides picked: {[(i['item_name'], q) for i, q in sides]}")

            # STEP 2e — drinks (1-per-person, 1–3 variants).
            has_drink = any(
                (it.get('item_category') or '').lower() == 'drink'
                for it, _ in items_with_quantities
            )
            if not has_drink:
                drinks = self._pick_drinks(num_people, existing_ids)
                for item, qty in drinks:
                    items_with_quantities.append((item, qty))
                    existing_ids.add(item['item_id'])
                print(f"[DealAgent] Drinks picked: {[(i['item_name'], q) for i, q in drinks]}")

            if not items_with_quantities:
                none_msg = (
                    "I couldn't create a deal with those requirements. "
                    "Please try again!"
                )
                return {
                    "success": False,
                    "needs_clarification": True,
                    "clarification_type": "items",
                    "message": none_msg,
                    "message_en": none_msg,
                    "message_voice": (
                        "I couldn't build a deal with those requirements. "
                        "Could you try again with different items?"
                    ),
                }

            # Keep `selected_items` for the category-breakdown display below.
            selected_items = [it for it, _qty in items_with_quantities]
            print(f"[DealAgent] Items with quantities: {[(i['item_name'], qty) for i, qty in items_with_quantities]}")

            # STEP 6: Calculate Price with proper scaling for multiple people
            # Price must account for quantities!
            total_standard_price = 0
            for item, qty in items_with_quantities:
                item_price = float(item.get('item_price') or 0)
                total_standard_price += item_price * qty
            
            # Better pricing: 15% discount for custom deals
            deal_price = total_standard_price * 0.85
            savings = total_standard_price - deal_price

            # STEP 7: Distribute Discount for Cart
            discount_ratio = deal_price / total_standard_price if total_standard_price > 0 else 1.0
            
            final_items = []
            for item, qty in items_with_quantities:
                orig_price = float(item.get('item_price') or 0)
                new_price = round(orig_price * discount_ratio, 2)
                
                final_items.append({
                    "item_id": item['item_id'],
                    "item_name": item['item_name'],
                    "price": new_price,
                    "item_price": new_price,
                    "quantity": qty,  # ✅ INCLUDE QUANTITY
                    "item_type": "menu_item"
                })

            # STEP 8: Create response message with category breakdown and quantities
            people_text = f" for {num_people} {'person' if num_people == 1 else 'people'}" if num_people > 1 else ""
            msg = f"✨ **Custom Deal Created{people_text}!**\n\n"
            
            # Show items organized by category with quantities
            items_by_category = {}
            for i in final_items:
                # Find original item to get category
                orig_item = next((si for si in selected_items if si['item_id'] == i['item_id']), None)
                if orig_item:
                    cat = orig_item.get('item_category', 'Other').title()
                    if cat not in items_by_category:
                        items_by_category[cat] = []
                    # Include quantity in display
                    qty = i.get('quantity', 1)
                    display_text = f"{qty}× {i['item_name']}"
                    items_by_category[cat].append(display_text)
            
            # Display items by category
            for category in ["Main", "Bread", "Side", "Appetizer", "Drink", "Other"]:
                if category in items_by_category:
                    msg += f"\n**{category}:**\n"
                    for item_display in items_by_category[category]:
                        msg += f"  • {item_display}\n"
            
            msg += f"\n💰 **Special Price:** Rs. {deal_price:.2f} (Save Rs. {savings:.2f}!)"

            # ─── Voice-friendly (plain text) summary ──────────────────────────
            # Narrated by TTS in the Flutter client; must NOT contain markdown
            # characters (`*`, `#`, `_`) or emojis — those get read as
            # "sitara sitara" / "sharp" / etc. on Urdu TTS engines.
            spoken_items = []
            for cat_label in ["Main", "Bread", "Side", "Appetizer", "Drink", "Other"]:
                for entry in items_by_category.get(cat_label, []):
                    # entry looks like "2× Chicken Karahi" — turn into speech.
                    try:
                        qty_part, name_part = entry.split("×", 1)
                        qty_val = int(qty_part.strip())
                        name_val = name_part.strip()
                        if qty_val <= 1:
                            spoken_items.append(name_val)
                        else:
                            spoken_items.append(f"{qty_val} {name_val}")
                    except Exception:
                        spoken_items.append(entry.replace("×", " "))

            if len(spoken_items) > 1:
                items_spoken = ", ".join(spoken_items[:-1]) + f" and {spoken_items[-1]}"
            else:
                items_spoken = spoken_items[0] if spoken_items else "the selected items"

            people_spoken = (
                f" for {num_people} people" if num_people > 1 else ""
            )
            voice_msg = (
                f"Your custom deal{people_spoken} includes {items_spoken}. "
                f"Total price is {int(round(deal_price))} rupees."
            )

            return {
                "success": True,
                "message": msg,                       # rich markdown for UI
                "message_voice": voice_msg,           # plain text for TTS
                "items": final_items,
                "total_price": round(deal_price, 2),
            }

        except Exception as e:
            print(f"[DealAgent] Logic Error: {e}")
            import traceback
            traceback.print_exc()
            err_msg = "Error creating deal. Please try again!"
            return {
                "success": False,
                "message": err_msg,
                "message_en": err_msg,
                "message_voice": (
                    "Sorry, something went wrong while creating your deal. "
                    "Please try again."
                ),
            }

def run_deal_agent():
    print("[DealAgent] Custom Deal Agent (AI-Powered) is STARTING...")
    try:
        agent = CustomDealAgent()
        redis_conn = RedisConnection.get_instance()
        pubsub = redis_conn.pubsub()
        pubsub.subscribe(AGENT_TASKS_CHANNEL)
        print("[DealAgent] Custom Deal Agent LISTENING (OK)")

        for msg in pubsub.listen():
            if msg.get("type") != "message": continue
            try:
                data = json.loads(msg["data"])
                if data.get("agent") != "deal_agent": continue

                command = data.get("command")
                payload = data.get("payload", {}) or {}
                resp_channel = data.get("response_channel")
                
                print(f"[DealAgent] Processing: {command}")
                
                result = {}
                if command == "create_custom_deal":
                    result = agent.create_deal(payload.get("user_query", ""))
                
                if resp_channel:
                    redis_conn.publish(resp_channel, json.dumps(result, cls=DecimalEncoder))

            except Exception as e:
                print(f"[DealAgent] Loop Error: {e}")

    except Exception as e:
        print(f"FATAL CRASH: {e}")
        time.sleep(10)

if __name__ == "__main__":
    from monitoring.agent_lifecycle_manager import wrap_agent
    wrap_agent("custom_deal", run_deal_agent)
