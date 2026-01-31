import os
import json
import requests

from dotenv import load_dotenv

from database_connection import DatabaseConnection
from redis_connection import RedisConnection
from config import AGENT_TASKS_CHANNEL

load_dotenv()


class UpsellAgent:
    """
    Weather-based upsell agent.

    Uses OpenWeather API + direct database queries to recommend snacks/sides/drinks
    based on current weather (hot / cold / rainy / mild).
    Only suggests snack-type items - no main dishes or breads.
    """

    def __init__(self):
        self.db = DatabaseConnection.get_instance()
        self.openweather_key = os.getenv("OPENWEATHER_KEY")
        if not self.openweather_key:
            print("OPENWEATHER_KEY not set in .env – upsell will use fallback mode.")

    # ---------------------------------------------------------
    # WEATHER FETCH + INTERPRETATION
    # ---------------------------------------------------------
    def get_weather(self, city: str = "Islamabad") -> dict:
        """
        Returns:
        {
            "success": True/False,
            "temp": float,
            "condition": "clouds",
            "category": "hot/cold/rainy/mild"
        }
        """
        if not self.openweather_key:
            return {
                "success": False,
                "temp": None,
                "condition": None,
                "category": "mild",
                "message": "No OPENWEATHER_KEY configured."
            }

        try:
            url = (
                f"https://api.openweathermap.org/data/2.5/weather"
                f"?q={city}&appid={self.openweather_key}&units=metric"
            )
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            data = r.json()

            temp = data["main"]["temp"]
            condition = data["weather"][0]["main"].lower()

            # Weather → category logic
            if "rain" in condition or "drizzle" in condition or "thunder" in condition:
                category = "rainy"
            elif temp <= 18:
                category = "cold"
            elif temp >= 30:
                category = "hot"
            else:
                category = "mild"

            return {
                "success": True,
                "temp": temp,
                "condition": condition,
                "category": category
            }

        except Exception as e:
            print(f"[UpsellAgent] Weather fetch error: {e}")
            return {
                "success": False,
                "temp": None,
                "condition": None,
                "category": "mild",
                "message": str(e)
            }

    # ---------------------------------------------------------
    # DATABASE QUERY HELPER
    # ---------------------------------------------------------
    def _fetch_items(self, sql: str):
        """Execute SQL and return list of item dictionaries with full details."""
        results = []

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall() or []

                if not rows:
                    return []

                colnames = [desc[0] for desc in cur.description]

                for row in rows:
                    row_dict = {colnames[i]: row[i] for i in range(len(colnames))}
                    results.append({
                        "item_id": row_dict.get("item_id"),
                        "item_name": row_dict.get("item_name"),
                        "item_description": row_dict.get("item_description"),
                        "item_price": float(row_dict.get("item_price")) if row_dict.get("item_price") else None,
                        "item_category": row_dict.get("item_category"),
                        "item_cuisine": row_dict.get("item_cuisine"),
                    })

        return results

    # ---------------------------------------------------------
    # WEATHER-BASED RECOMMENDATIONS (snacks/sides/drinks only - NO breads)
    # ---------------------------------------------------------
    def recommend_for_cold(self):
        """
        Cold weather → hot drinks and warm snacks/starters.
        Items: Chai, Green Tea, Hot and Sour Soup, Samosa Platter, etc.
        """
        sql = """
            SELECT item_id, item_name, item_description, item_price, item_category, item_cuisine
            FROM menu_item
            WHERE availability = TRUE
              AND item_category IN ('drink', 'starter', 'side')
              AND item_category != 'bread'
              AND (
                    'hot' = ANY(tags)
                 OR item_name ILIKE '%chai%'
                 OR item_name ILIKE '%tea%'
                 OR item_name ILIKE '%soup%'
                 OR item_name ILIKE '%samosa%'
              )
            ORDER BY item_price ASC
            LIMIT 6;
        """
        return self._fetch_items(sql)

    def recommend_for_hot(self):
        """
        Hot weather → cold drinks and refreshing items (excluding plain water).
        Items: Cola, Lemonade, Mint Margarita, Iced Coffee, Shakes, Juice, etc.
        """
        sql = """
            SELECT item_id, item_name, item_description, item_price, item_category, item_cuisine
            FROM menu_item
            WHERE availability = TRUE
              AND item_category = 'drink'
              AND item_name NOT ILIKE '%water%'
              AND (
                    'cold' = ANY(tags)
                 OR item_name ILIKE '%cola%'
                 OR item_name ILIKE '%lemonade%'
                 OR item_name ILIKE '%margarita%'
                 OR item_name ILIKE '%iced%'
                 OR item_name ILIKE '%shake%'
                 OR item_name ILIKE '%juice%'
              )
            ORDER BY item_price ASC
            LIMIT 6;
        """
        return self._fetch_items(sql)

    def recommend_for_rain(self):
        """
        Rainy weather → fried snacks and comfort sides.
        Items: Fries, Samosa, Spring Rolls, Onion Rings, Nuggets, etc.
        """
        sql = """
            SELECT item_id, item_name, item_description, item_price, item_category, item_cuisine
            FROM menu_item
            WHERE availability = TRUE
              AND item_category IN ('starter', 'side')
              AND item_category != 'bread'
              AND (
                    'fries' = ANY(tags)
                 OR 'snack' = ANY(tags)
                 OR item_name ILIKE '%fries%'
                 OR item_name ILIKE '%samosa%'
                 OR item_name ILIKE '%spring roll%'
                 OR item_name ILIKE '%onion ring%'
                 OR item_name ILIKE '%nugget%'
                 OR item_name ILIKE '%chaat%'
                 OR item_name ILIKE '%cracker%'
              )
            ORDER BY item_price ASC
            LIMIT 6;
        """
        return self._fetch_items(sql)

    def recommend_for_mild(self):
        """
        Mild weather → mix of popular snacks and drinks (no breads, no plain water).
        Items: Various sides, starters, and drinks.
        """
        sql = """
            SELECT item_id, item_name, item_description, item_price, item_category, item_cuisine
            FROM menu_item
            WHERE availability = TRUE
              AND item_category IN ('drink', 'starter', 'side')
              AND item_category != 'bread'
              AND item_name NOT ILIKE '%water%'
            ORDER BY item_price ASC
            LIMIT 6;
        """
        return self._fetch_items(sql)

    # ---------------------------------------------------------
    # PUBLIC API: WEATHER_UPSELL
    # ---------------------------------------------------------
    def weather_upsell(self, city: str = "Islamabad") -> dict:
        wx = self.get_weather(city)

        category = wx.get("category", "mild")

        if category == "cold":
            items = self.recommend_for_cold()
            label = "It’s cold today – here are some hot, comforting items:"
        elif category == "hot":
            items = self.recommend_for_hot()
            label = "It’s hot today – here are some refreshing, cold items:"
        elif category == "rainy":
            items = self.recommend_for_rain()
            label = "It’s rainy – perfect time for comfort and fried items:"
        else:
            items = self.recommend_for_mild()
            label = "Weather is mild – here are some popular options:"

        return {
            "success": True,
            "weather": wx,
            "headline": label,
            "items": items
        }


# -------------------------------------------------------------
# REDIS LISTENER LOOP
# -------------------------------------------------------------
def run_upsell_agent():
    print("Upsell Agent is running and listening for tasks...")

    upsell = UpsellAgent()
    redis_conn = RedisConnection.get_instance()
    if not redis_conn:
        print("FATAL: Could not connect to Redis. Upsell Agent shutting down.")
        return

    pubsub = redis_conn.pubsub()
    pubsub.subscribe(AGENT_TASKS_CHANNEL)

    for message in pubsub.listen():
        if message.get("type") != "message":
            continue

        try:
            task_data = json.loads(message["data"])
        except Exception as e:
            print(f"[UpsellAgent] JSON decode error: {e}")
            continue

        if task_data.get("agent") != "upsell":
            continue

        command = task_data.get("command")
        payload = task_data.get("payload", {}) or {}
        response_channel = task_data.get("response_channel")

        print(f"[UpsellAgent] Received command: {command}")

        result = {"success": False, "message": "Unknown command."}

        try:
            if command == "weather_upsell":
                city = payload.get("city", "Islamabad")
                result = upsell.weather_upsell(city=city)
            else:
                result = {
                    "success": False,
                    "message": f"Unknown upsell command: {command}"
                }
        except Exception as e:
            print(f"[UpsellAgent] Error while processing: {e}")
            result = {"success": False, "message": f"Upsell error: {str(e)}"}

        if response_channel:
            try:
                redis_conn.publish(response_channel, json.dumps(result))
                print(f"[UpsellAgent] Sent → {response_channel}")
            except Exception as e:
                print(f"[UpsellAgent] Failed to publish response: {e}")


if __name__ == "__main__":
    from agent_lifecycle_manager import wrap_agent
    wrap_agent("upsell", run_upsell_agent)
