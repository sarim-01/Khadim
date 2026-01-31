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
    from psycopg2.extras import RealDictCursor
    from database_connection import DatabaseConnection
    from redis_connection import RedisConnection
    from config import AGENT_TASKS_CHANNEL
    
    # NEW IMPORTS FOR VECTOR SEARCH
    from langchain_community.embeddings import HuggingFaceEmbeddings
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
            print("[DealAgent] Vector Store Loaded ✅")
        except FileNotFoundError:
            print(f"[DealAgent] ⚠️ Vector Store index not found at '{FAISS_INDEX_PATH}'. Please run 'python vector_store.py' to create it.")
            self.vectorstore = None
        except Exception as e:
            print(f"[DealAgent] ⚠️ Vector Store failed to load: {e}")
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
        - "explicit_items": Extract food item NAMES/KEYWORDS the user specifically mentions. 
          Examples: "biryani and burger" -> ["biryani", "burger"]
                   "chicken items" -> ["chicken"]
                   "fast food" -> [] (this is a category, not an item)
        
        - "num_people": Extract if user mentions "X person deal", "for 3 people", etc. Default: 1
          IMPORTANT: Extract the NUMBER even if user says "for 3 people including..." or "3 people with..."
          Examples: "for 3 people" -> 3
                   "make a deal for 5 people" -> 5
                   "3 people with biryani" -> 3
        
        - "cuisine": Extract cuisine preference if mentioned. Use these exact values:
          "Desi" (for Pakistani/Desi food)
          "Fast Food" (for burgers, fries, etc.)
          "Chinese"
          "BBQ" (for grilled/barbecue items)
          "Drinks"
          
          IMPORTANT: If user says "only" or "including", that's a constraint!
          Examples: "including fast food only" -> cuisine is "Fast Food"
                   "3 people including pakistani" -> cuisine is "Desi"
        
        - "category": Extract category if mentioned: "main", "appetizer", "drinks", etc.
        
        - "needs_clarification": Set to true if request is too vague (e.g., "make me a deal" with no other info)
        
        - "clarification_type": If needs_clarification is true, what to ask about:
          "items" - what items they want
          "cuisine" - what type of food
          "count" - how many people
        
        JSON SCHEMA:
        {{
            "explicit_items": ["item1", "item2"],
            "num_people": 1,
            "cuisine": null,
            "category": null,
            "needs_clarification": false,
            "clarification_type": null
        }}
        
        EXAMPLES:
        Input: "Make me a deal with biryani and burger"
        Output: {{"explicit_items": ["biryani", "burger"], "num_people": 1, "cuisine": null, "category": null, "needs_clarification": false, "clarification_type": null}}
        
        Input: "Create a 3 person deal"
        Output: {{"explicit_items": [], "num_people": 3, "cuisine": null, "category": null, "needs_clarification": true, "clarification_type": "cuisine"}}
        
        Input: "I want a Pakistani food deal"
        Output: {{"explicit_items": [], "num_people": 1, "cuisine": "Desi", "category": null, "needs_clarification": false, "clarification_type": null}}
        
        Input: "make a custom deal for 3 people including fast food only"
        Output: {{"explicit_items": [], "num_people": 3, "cuisine": "Fast Food", "category": null, "needs_clarification": false, "clarification_type": null}}
        
        Input: "make a custom deal for 5 people including pakistani food"
        Output: {{"explicit_items": [], "num_people": 5, "cuisine": "Desi", "category": null, "needs_clarification": false, "clarification_type": null}}
        
        Input: "make a custom deal for 5 people including chinese food"
        Output: {{"explicit_items": [], "num_people": 5, "cuisine": "Chinese", "category": null, "needs_clarification": false, "clarification_type": null}}
        

        Input: "make a custom deal for 5 people including bbq food"
        Output: {{"explicit_items": [], "num_people": 5, "cuisine": "BBQ", "category": null, "needs_clarification": false, "clarification_type": null}}
        
        """
        
        try:
            prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", "{input}")])
            chain = prompt | self.llm
            response = chain.invoke({"input": user_query})
            data = self._extract_json(response.content)
            print(f"[DealAgent] Parsed requirements: {data}")
            return data if data else {"explicit_items": [], "num_people": 1, "needs_clarification": False}
        except Exception as e:
            print(f"[DealAgent] Parse error: {e}")
            return {"explicit_items": [], "num_people": 1, "needs_clarification": False}
    
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
                
                # 1. SPECIFIC NAME SEARCH (HYBRID: Vector + SQL)
                if names:
                    for name in names:
                        item = None
                        
                        # A. Try Vector Search First (Semantic)
                        semantic_matches = self._semantic_search(name, limit=1)
                        if semantic_matches:
                            best_match_name = semantic_matches[0]
                            print(f"[DealAgent] Semantic Match: '{name}' -> '{best_match_name}'")
                            
                            # Fetch the actual item using the name found by Vector DB
                            cur.execute("SELECT * FROM menu_item WHERE item_name = %s AND availability = TRUE", (best_match_name,))
                            item = cur.fetchone()
                        
                        # B. Fallback to SQL ILIKE (Fuzzy) if Vector failed or returned no DB match
                        if not item:
                            print(f"[DealAgent] Vector failed, trying SQL ILIKE for '{name}'...")
                            cur.execute("SELECT * FROM menu_item WHERE item_name ILIKE %s AND availability = TRUE LIMIT 1", (f"%{name}%",))
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

    def _calculate_quantities(self, items_list, num_people):
        import math # Ensure this is imported
        
        # 1. Group items by category
        cat_map = {}
        for item in items_list:
            cat = item.get('item_category', 'main').lower()
            if cat not in cat_map: cat_map[cat] = []
            cat_map[cat].append(item)

        final_list = []

        # 2. Process each category
        for cat, items in cat_map.items():
            count = len(items)
            if count == 0: continue

            # --- DRINKS & BREADS ---
            if cat in ['drink', 'bread']:
                base_qty = num_people // count
                remainder = num_people % count
                for i, item in enumerate(items):
                    qty = base_qty + (1 if i < remainder else 0)
                    final_list.append((item, max(1, qty)))

            # --- MAINS (The Fix) ---
            elif cat == 'main':
                # Target servings per dish (e.g. 3 people / 2 dishes = 1.5 servings each)
                target_servings = num_people / count
                
                for item in items:
                    s_size = int(item.get('serving_size') or 1)
                    # Use math.ceil to round UP. 
                    # 1.5 servings / size 1 = 1.5 -> rounds up to 2 Burgers
                    qty = math.ceil(target_servings / s_size)
                    final_list.append((item, max(1, qty)))

            # --- SIDES ---
            else:
                total_needed = max(1, (num_people + 2) // 3)
                if count >= total_needed:
                    for item in items: final_list.append((item, 1))
                else:
                    base_qty = total_needed // count
                    remainder = total_needed % count
                    for i, item in enumerate(items):
                        qty = base_qty + (1 if i < remainder else 0)
                        final_list.append((item, max(1, qty)))
        
        return final_list

    def create_deal(self, user_query: str):
        try:
            reqs = self._parse_requirements(user_query)
            
            # Normalize cuisine to match database values
            if reqs.get("cuisine"):
                reqs["cuisine"] = self._normalize_cuisine(reqs["cuisine"])
                print(f"[DealAgent] Normalized cuisine to: {reqs['cuisine']}")
            
            # STEP 1: Check if clarification is needed
            if reqs.get("needs_clarification"):
                clarification_type = reqs.get("clarification_type", "items")
                num_people = reqs.get("num_people", 1)
                
                if clarification_type == "cuisine":
                    return {
                        "success": False,
                        "message": f"I'd love to create a custom deal for {num_people} {'person' if num_people == 1 else 'people'}! 🎉\n\nWhat type of food would you like?\n- Pakistani/Desi food (Biryani, Karahi, Kebabs)\n- Fast Food (Burgers, Fries, Wings)\n- Chinese food\n- Or tell me specific items you want!"
                    }
                elif clarification_type == "items":
                    return {
                        "success": False,
                        "message": "I can create a custom deal for you! What items would you like to include?\n\nFor example:\n- 'Biryani and burger'\n- 'Chicken items with rice'\n- 'Pakistani food'\n\nJust let me know your preferences!"
                    }
                elif clarification_type == "count":
                    return {
                        "success": False,
                        "message": "How many people is this deal for? I'll customize the portions accordingly!"
                    }
            
            # STEP 2: Determine target deal size (items per person)
            num_people = reqs.get("num_people", 1)
            
            # Smarter sizing logic:
            # 1 person: 3 items (main + side/bread + drink)
            # 2 people: 5 items (2 mains + bread + side + drink)
            # 3 people: 6 items (2 mains + bread + side + 2 drinks OR extras)
            # 4+ people: 7 items (distribute across categories)
            
            if num_people == 1:
                target_items = 3
            elif num_people == 2:
                target_items = 5
            elif num_people == 3:
                target_items = 6
            else:  # 4+ people
                target_items = min(num_people + 3, 8)  # Scale up but cap at 8
            
            print(f"[DealAgent] Deal for {num_people} people → Target {target_items} items")
            
            selected_items = []
            
            # STEP 3: Fetch explicitly requested items (Hybrid Search)
            if reqs.get("explicit_items"):
                print(f"[DealAgent] Searching for explicit items: {reqs['explicit_items']}")
                selected_items = self._find_items_in_db(names=reqs["explicit_items"])
                
                if not selected_items:
                    items_str = ', '.join(reqs['explicit_items'])
                    print(f"[DealAgent] ERROR: Could not find any of the items: {items_str}")
                    return {
                        "success": False, 
                        "message": f"I couldn't find '{items_str}' on our menu. Could you try different items or let me suggest something?"
                    }
                
                print(f"[DealAgent] Found {len(selected_items)} explicit items: {[i['item_name'] for i in selected_items]}")
            
            # STEP 4: Intelligent Filler Logic - Balanced by Category & People
            if len(selected_items) < target_items:
                needed = target_items - len(selected_items)
                
                # CRITICAL FIX: Determine primary_cuisine correctly
                # Priority: explicit cuisine from user > cuisine from explicit items > default None
                if reqs.get("cuisine"):
                    primary_cuisine = reqs.get("cuisine")
                    print(f"[DealAgent] Using explicit cuisine from user: {primary_cuisine}")
                elif reqs.get("explicit_items") and selected_items:
                    primary_cuisine = selected_items[0].get('item_cuisine')
                    print(f"[DealAgent] Using cuisine from first selected item: {primary_cuisine}")
                else:
                    primary_cuisine = None
                    print(f"[DealAgent] No specific cuisine - using generic approach")
                
                print(f"[DealAgent] Need {needed} more items. Primary cuisine: {primary_cuisine}, Num people: {num_people}")
                
                # Count current items by category
                current_categories = {}
                for item in selected_items:
                    cat = item.get('item_category', 'unknown')
                    current_categories[cat] = current_categories.get(cat, 0) + 1
                
                mains_count = current_categories.get('main', 0)
                bread_count = current_categories.get('bread', 0)
                side_count = current_categories.get('side', 0)
                drink_count = current_categories.get('drink', 0)
                
                print(f"[DealAgent] Current composition - Mains: {mains_count}, Bread: {bread_count}, Sides: {side_count}, Drinks: {drink_count}")
                
                # --- FILLER PRIORITY ORDER (STRICTLY RESPECTS CUISINE) ---
                # Priority 1: Ensure at least 1 bread/naan for Desi cuisine
                if primary_cuisine == "Desi" and bread_count == 0 and needed > 0:
                    bread_fillers = self._find_items_in_db(cuisine="Desi", category="bread", limit=1)
                    for f in bread_fillers:
                        if f['item_id'] not in [x['item_id'] for x in selected_items]:
                            selected_items.append(f)
                            needed -= 1
                            bread_count += 1
                            print(f"[DealAgent] Added Desi bread")
                
                # Priority 2: Ensure mains are balanced per person (at least 1 main per 2 people)
                mains_per_person = max(1, num_people // 2)
                if mains_count < mains_per_person and needed > 0:
                    mains_needed = min(needed, mains_per_person - mains_count)
                    # STRICTLY use primary cuisine if specified
                    if primary_cuisine:
                        main_fillers = self._find_items_in_db(cuisine=primary_cuisine, category="main", limit=mains_needed)
                    else:
                        main_fillers = self._find_items_in_db(category="main", limit=mains_needed)
                    
                    for f in main_fillers:
                        if f['item_id'] not in [x['item_id'] for x in selected_items]:
                            selected_items.append(f)
                            needed -= 1
                            mains_count += 1
                    print(f"[DealAgent] Added {mains_needed} mains")
                
                # Priority 3: Add sides (complements the meal) - STRICT CUISINE ADHERENCE
                if needed > 0 and side_count < 1:
                    # Only add cuisine-specific sides, don't fallback to generic
                    if primary_cuisine:
                        side_fillers = self._find_items_in_db(cuisine=primary_cuisine, category="side", limit=1)
                        print(f"[DealAgent] Searching for {primary_cuisine} sides")
                    else:
                        side_fillers = []
                    
                    if side_fillers:
                        for f in side_fillers:
                            if f['item_id'] not in [x['item_id'] for x in selected_items]:
                                selected_items.append(f)
                                needed -= 1
                                side_count += 1
                        print(f"[DealAgent] Added side dish from {primary_cuisine}")
                    else:
                        print(f"[DealAgent] No {primary_cuisine} sides available, skipping to maintain cuisine purity")
                
                # Priority 4: Add beverages (essential for group meals)
                if needed > 0:
                    beverages_needed = min(needed, max(1, num_people // 2))
                    # Drinks are usually generic/universal
                    drink_fillers = self._find_items_in_db(category="drink", limit=beverages_needed)
                    for f in drink_fillers:
                        if f['item_id'] not in [x['item_id'] for x in selected_items]:
                            selected_items.append(f)
                            needed -= 1
                            drink_count += 1
                    print(f"[DealAgent] Added {beverages_needed} drinks")
                
                # Priority 5: Fill remaining slots with variety (ONLY from primary cuisine)
                if needed > 0 and primary_cuisine:
                    variety_fillers = self._find_items_in_db(cuisine=primary_cuisine, category="appetizer", limit=needed)
                    for f in variety_fillers:
                        if f['item_id'] not in [x['item_id'] for x in selected_items]:
                            selected_items.append(f)
                            needed -= 1
                    if variety_fillers:
                        print(f"[DealAgent] Added appetizers from {primary_cuisine}")
                
                if needed > 0:
                    print(f"[DealAgent] ⚠️ Could only fill {target_items - needed} out of {target_items} target items (cuisine: {primary_cuisine})")

            if not selected_items:
                return {"success": False, "message": "I couldn't create a deal with those requirements. Please try again!"}

            # STEP 5: Calculate Quantities Based on Serving Sizes
            items_with_quantities = self._calculate_quantities(selected_items, num_people)
            
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

            return {
                "success": True,
                "message": msg,
                "deal_data": {
                    "items": final_items,
                    "total_price": deal_price
                }
            }

        except Exception as e:
            print(f"[DealAgent] Logic Error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "message": "Error creating deal. Please try again!"}

def run_deal_agent():
    print("💰 Custom Deal Agent (AI-Powered) is STARTING...")
    try:
        agent = CustomDealAgent()
        redis_conn = RedisConnection.get_instance()
        pubsub = redis_conn.pubsub()
        pubsub.subscribe(AGENT_TASKS_CHANNEL)
        print("✅ Custom Deal Agent LISTENING...")

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
    from agent_lifecycle_manager import wrap_agent
    wrap_agent("custom_deal", run_deal_agent)