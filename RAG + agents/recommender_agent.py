import json
import os
import random
from dotenv import load_dotenv
from redis_connection import RedisConnection
from config import AGENT_TASKS_CHANNEL

load_dotenv()

class RecommendationEngine:
    """
    A Rule-Based Recommender System.
    Logic: Triggers specific suggestions based on the LAST item added to the cart.
    """
    def __init__(self):
        # The "Knowledge Base" - Hardcoded patterns based on actual menu items
        # Keys are keywords we look for in the user's last order.
        # Values are lists of Item Names that exist in your menu.
        self.pairing_rules = {
            # ===== FAST FOOD PAIRINGS =====
            "cheeseburger": ["Fries", "Cola", "Onion Rings", "Iced Coffee"],
            "chicken burger": ["Fries", "Cola", "Loaded Fries", "Lemonade"],
            "veggie burger": ["Fries", "Cola", "Onion Rings", "Lemonade"],
            "zinger burger": ["Fries", "Cola", "Loaded Fries", "Lemonade"],
            "burger": ["Fries", "Cola", "Onion Rings", "Chicken Nuggets"],
            
            "club sandwich": ["Fries", "Cola", "Iced Coffee", "Lemonade"],
            "fish fillet sandwich": ["Fries", "Cola", "Onion Rings", "Lemonade"],
            "sandwich": ["Fries", "Cola", "Iced Coffee"],
            
            "fries": ["Cola", "Chicken Nuggets", "Lemonade", "Cheeseburger"],
            "loaded fries": ["Cola", "Lemonade", "Zinger Burger"],
            "chicken nuggets": ["Fries", "Cola", "Loaded Fries"],
            "onion rings": ["Cola", "Cheeseburger", "Lemonade"],
            
            # ===== DESI CUISINE PAIRINGS =====
            "chicken karahi": ["Naan", "Garlic Naan", "Roti", "Mint Margarita", "Cola"],
            "karahi": ["Naan", "Garlic Naan", "Roti", "Mint Margarita"],
            
            "chicken handi": ["Naan", "Garlic Naan", "Paratha", "Mint Margarita", "Cola"],
            "handi": ["Naan", "Garlic Naan", "Paratha"],
            
            "beef biryani": ["Cola", "Mint Margarita", "Chana Chaat", "Chai"],
            "biryani": ["Cola", "Mint Margarita", "Chana Chaat"],
            
            "nihari": ["Naan", "Garlic Naan", "Cola", "Chai", "Lemonade"],
            
            "seekh kabab": ["Naan", "Paratha", "Chana Chaat", "Mint Margarita", "Cola"],
            "kabab": ["Naan", "Paratha", "Mint Margarita"],
            
            "daal chawal": ["Aloo Paratha", "Chapatti", "Chai", "Lemonade"],
            "daal": ["Chapatti", "Roti", "Chai"],
            
            "palak paneer": ["Naan", "Garlic Naan", "Roti", "Mint Margarita"],
            "paneer": ["Naan", "Garlic Naan", "Roti"],
            
            "aloo paratha": ["Chai", "Daal Chawal", "Mint Margarita"],
            "paratha": ["Chai", "Mint Margarita"],
            
            "samosa platter": ["Chai", "Chana Chaat", "Mint Margarita", "Green Tea"],
            "samosa": ["Chai", "Chana Chaat", "Mint Margarita"],
            
            "chana chaat": ["Samosa Platter", "Cola", "Lemonade"],
            
            # ===== CHINESE CUISINE PAIRINGS =====
            "kung pao chicken": ["Egg Fried Rice", "Chicken Chow Mein", "Hot and Sour Soup", "Cola"],
            "kung pao": ["Egg Fried Rice", "Cola"],
            
            "sweet and sour chicken": ["Egg Fried Rice", "Chicken Chow Mein", "Cola", "Lemonade"],
            "sweet and sour": ["Egg Fried Rice", "Cola"],
            
            "chicken manchurian": ["Egg Fried Rice", "Chicken Chow Mein", "Hot and Sour Soup", "Cola"],
            "manchurian": ["Egg Fried Rice", "Chicken Chow Mein", "Cola"],
            
            "chicken chow mein": ["Chicken Manchurian", "Hot and Sour Soup", "Vegetable Spring Rolls", "Cola"],
            "chow mein": ["Chicken Manchurian", "Hot and Sour Soup", "Cola"],
            
            "beef with black bean sauce": ["Egg Fried Rice", "Chicken Chow Mein", "Cola"],
            "black bean sauce": ["Egg Fried Rice", "Cola"],
            
            "szechuan beef": ["Egg Fried Rice", "Chicken Chow Mein", "Cola", "Green Tea"],
            "szechuan": ["Egg Fried Rice", "Green Tea"],
            
            "egg fried rice": ["Chicken Manchurian", "Kung Pao Chicken", "Sweet and Sour Chicken", "Cola"],
            
            "vegetable spring rolls": ["Hot and Sour Soup", "Chicken Chow Mein", "Cola"],
            "spring rolls": ["Hot and Sour Soup", "Cola"],
            
            "hot and sour soup": ["Vegetable Spring Rolls", "Chicken Chow Mein", "Fish Crackers", "Green Tea"],
            "soup": ["Vegetable Spring Rolls", "Fish Crackers", "Green Tea"],
            
            "fish crackers": ["Hot and Sour Soup", "Cola", "Green Tea"],
            
            # ===== BBQ CUISINE PAIRINGS =====
            "chicken tikka": ["Naan", "Paratha", "Mint Margarita", "Cola", "Garlic Naan"],
            "tikka": ["Naan", "Paratha", "Mint Margarita"],
            
            "beef boti": ["Naan", "Paratha", "Mint Margarita", "Cola", "Garlic Naan"],
            "boti": ["Naan", "Paratha", "Mint Margarita"],
            
            "malai boti": ["Naan", "Paratha", "Mint Margarita", "Cola", "Garlic Naan"],
            "malai": ["Naan", "Paratha", "Mint Margarita"],
            
            "reshmi kebab": ["Naan", "Paratha", "Mint Margarita", "Cola", "Garlic Naan"],
            "reshmi": ["Naan", "Paratha", "Mint Margarita"],
            
            "grilled fish": ["Naan", "Lemonade", "Mint Margarita", "Paratha"],
            "grilled": ["Naan", "Paratha", "Mint Margarita"],
            
            # ===== DRINKS PAIRINGS =====
            "cola": ["Fries", "Chicken Nuggets", "Onion Rings"],
            "lemonade": ["Fries", "Chicken Burger", "Samosa Platter"],
            "mint margarita": ["Chicken Tikka", "Chicken Karahi", "Beef Boti"],
            "green tea": ["Vegetable Spring Rolls", "Hot and Sour Soup", "Samosa Platter"],
            "chai": ["Samosa Platter", "Aloo Paratha", "Paratha"],
            "iced coffee": ["Club Sandwich", "Chicken Burger", "Fries"],
            "strawberry shake": ["Cheeseburger", "Fries", "Chicken Nuggets"],
            "orange juice": ["Club Sandwich", "Veggie Burger", "Samosa Platter"],
            
            # ===== BREAD PAIRINGS =====
            "naan": ["Chicken Karahi", "Chicken Handi", "Nihari", "Chicken Tikka"],
            "garlic naan": ["Chicken Karahi", "Palak Paneer", "Beef Boti"],
            "roti": ["Chicken Karahi", "Daal Chawal", "Palak Paneer"],
            "chapatti": ["Daal Chawal", "Palak Paneer"],
        }
        
        # Generic Fallbacks if no specific rule matches
        self.category_fallbacks = {
            "main": ["Cola", "Water Bottle"],
            "starter": ["Main Course"],
            "fast food": ["Fries"],
            "desi": ["Naan"]
        }

    def get_recommendation(self, last_item_name: str, current_cart_names: list) -> dict:
        """
        Returns a single best recommendation.
        """
        item_lower = last_item_name.lower()
        candidates = []

        # 1. Search for a specific rule match
        for keyword, matches in self.pairing_rules.items():
            if keyword in item_lower:
                candidates.extend(matches)
                break # Found a specific match, stop looking
        
        # 2. If no specific match, try generic fallbacks (Optional, based on DB category if we had it)
        if not candidates:
             if "chicken" in item_lower or "beef" in item_lower:
                 candidates = ["Cola", "Water Bottle"]

        if not candidates:
            return {"success": False, "message": "No specific pairing found."}

        # 3. FILTER: Remove items user ALREADY has in cart
        # (Don't suggest Fries if they already ordered Fries)
        cart_set = {c.lower() for c in current_cart_names}
        valid_candidates = [c for c in candidates if c.lower() not in cart_set]

        if not valid_candidates:
            return {"success": False, "message": "User has all recommended pairings."}

        # 4. SELECT: Pick the first valid option (Priority is defined by order in the list)
        recommendation = valid_candidates[0]

        return {
            "success": True,
            "recommended_item": recommendation,
            "reason": f"People frequently order {recommendation} with {last_item_name}."
        }

# --- REDIS LISTENER ---

def run_recommender_agent():
    print("Recommender Agent (Cross-Sell) is running...")
    redis_conn = RedisConnection.get_instance()
    pubsub = redis_conn.pubsub()
    pubsub.subscribe(AGENT_TASKS_CHANNEL)

    engine = RecommendationEngine()

    for message in pubsub.listen():
        if message.get('type') != 'message':
            continue

        try:
            data = json.loads(message['data'])
            
            if data.get('agent') != 'recommender':
                continue
            
            command = data.get('command')
            payload = data.get('payload', {})
            response_channel = data.get('response_channel')

            result = {}

            if command == 'get_recommendation':
                # Inputs: The item just added, and the full list of what's already in cart
                rec = engine.get_recommendation(
                    payload.get('last_item_name', ''), 
                    payload.get('current_cart_items', [])
                )
                result = rec
            
            else:
                result = {'success': False, 'message': 'Unknown command'}

            if response_channel:
                redis_conn.publish(response_channel, json.dumps(result))

        except Exception as e:
            print(f"❌ Error in Recommender Agent: {e}")

if __name__ == "__main__":
    run_recommender_agent()