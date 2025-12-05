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

    Uses OpenWeather API + menu_item table to recommend items
    based on current weather (hot / cold / rainy / mild).
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
    # UTILITY: DB QUERY HANDLER
    # ---------------------------------------------------------
    def _fetch_items(self, sql: str, params=None):
        params = params or ()
        results = []

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall() or []

            # If no rows, return empty list early
                if not rows:
                    return []

                colnames = [desc[0] for desc in cur.description]
       
       
        for row in rows:
            row_dict = {colnames[i]: row[i] for i in range(len(colnames))}

            results.append({
                "item_id": row_dict.get("item_id"),
                "item_name": row_dict.get("item_name"),
                "item_price": float(row_dict.get("item_price")) if row_dict.get("item_price") else None,
                "item_category": row_dict.get("item_category"),
                "item_cuisine": row_dict.get("item_cuisine"),
            })

        return results
    # ---------------------------------------------------------
    # CATEGORY: COLD
    # ---------------------------------------------------------
    def recommend_for_cold(self):
        """
        Cold weather → hot drinks, soups, desi items.
        """
        sql = """
            SELECT item_id, item_name, item_price, item_category, item_cuisine
            FROM menu_item
            WHERE availability = TRUE
              AND (
                    'hot' = ANY(tags)
                 OR 'soup' = ANY(tags)
                 OR item_name ILIKE '%soup%'
                 OR item_name ILIKE '%karahi%'
                 OR item_name ILIKE '%handi%'
                 OR item_name ILIKE '%nihari%'
              )
            ORDER BY item_price ASC
            LIMIT 10;
        """
        return self._fetch_items(sql)

    # ---------------------------------------------------------
    # CATEGORY: HOT
    # ---------------------------------------------------------
    def recommend_for_hot(self):
        """
        Hot weather → cold drinks & refreshing items.
        """
        sql = """
            SELECT item_id, item_name, item_price, item_category, item_cuisine
            FROM menu_item
            WHERE availability = TRUE
              AND (
                    'cold' = ANY(tags)
                 OR 'seasonal_summer' = ANY(tags)
                 OR item_cuisine = 'Drinks'
              )
            ORDER BY item_price ASC
            LIMIT 10;
        """
        return self._fetch_items(sql)

    # ---------------------------------------------------------
    # CATEGORY: RAIN
    # ---------------------------------------------------------
    def recommend_for_rain(self):
        """
        Rainy weather → fries, burgers, snacks, soup.
        """
        sql = """
            SELECT item_id, item_name, item_price, item_category, item_cuisine
            FROM menu_item
            WHERE availability = TRUE
              AND (
                    'fries' = ANY(tags)
                 OR 'burger' = ANY(tags)
                 OR 'snack' = ANY(tags)
                 OR item_name ILIKE '%fries%'
                 OR item_name ILIKE '%burger%'
                 OR item_name ILIKE '%samosa%'
                 OR item_name ILIKE '%soup%'
              )
            ORDER BY item_price ASC
            LIMIT 10;
        """
        return self._fetch_items(sql)

    # ---------------------------------------------------------
    # CATEGORY: MILD
    # ---------------------------------------------------------
    def recommend_for_mild(self):
        """
        Mild weather → mix of popular items.
        """
        sql = """
            SELECT item_id, item_name, item_price, item_category, item_cuisine
            FROM menu_item
            WHERE availability = TRUE
              AND (
                    'all_year' = ANY(tags)
                 OR item_cuisine IN ('Fast Food','Chinese','Desi')
              )
            ORDER BY item_price ASC
            LIMIT 10;
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
    run_upsell_agent()
