# main.py

import os
import uuid
import json
import time as _time
import redis as redis_lib
from auth.auth_routes import router as auth_router
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, Any

# Voice transcription is optional - will be added later
try:
    from voice.transcribe import transcribe_audio
    VOICE_ENABLED = True
except Exception as e:
    print(f"[WARNING] Voice transcription disabled: {e}")
    transcribe_audio = None
    VOICE_ENABLED = False

from chat.chat_agent import get_ai_response
from dotenv import load_dotenv
from sqlalchemy import text


from cart.cart_routes import router as cart_router
from orders.order_routes import router as order_router
from feedback.feedback_routes import router as feedback_router
from custom_deal.custom_deal_routes import router as custom_deal_router
from favourites.favourites_routes import router as favourites_router
from agents.upsell_agent import UpsellAgent
from personalization.personalization_agent import PersonalizationAgent
from agents.recommender_agent import RecommendationEngine
from agents.custom_deal_agent import CustomDealAgent
from auth.auth_routes import get_current_user
from typing import Dict, List

from infrastructure.db import SQL_ENGINE
from infrastructure.config import AGENT_TASKS_CHANNEL
from infrastructure.database_connection import DatabaseConnection

_REDIS_CLIENT = redis_lib.StrictRedis(host=os.getenv("REDIS_HOST", "localhost"), port=int(os.getenv("REDIS_PORT", 6379)), db=0, decode_responses=True)

upsell_agent = UpsellAgent()
recommendation_engine = RecommendationEngine()
custom_deal_agent = CustomDealAgent()

print("DB URL = ", os.getenv("DATABASE_URL"))


# Initialize AI agent


app = FastAPI()

app.include_router(auth_router)
app.include_router(cart_router)
app.include_router(order_router)
app.include_router(feedback_router)
app.include_router(custom_deal_router)
app.include_router(favourites_router)


# ── Phase 3: LLM-powered Personalization endpoint ─────────────────
@app.get("/personalization/recommendations", tags=["Personalization"])
def get_personalized_recommendations(
    top_k: int = 10,
    current_user: Dict = Depends(get_current_user),
):
    """
    Returns personalised item + deal recommendations for the authenticated user.
    Uses LLM reasoning (Groq llama-3.3-70b) over profile + FAISS + collab signals.
    Falls back to deterministic scoring if LLM is unavailable.
    Results are cached for 30 minutes.
    """
    user_id = str(current_user["user_id"])
    db = DatabaseConnection.get_instance()
    conn = db.get_connection()
    try:
        agent = PersonalizationAgent(conn)
        res = agent.recommend(user_id, top_k=top_k)
        
        # Inject categories for images
        import psycopg2.extras
        with conn.cursor() as cur:
            item_ids = [it.get("item_id") for it in res.get("recommended_items", []) if it.get("item_id")]
            if item_ids:
                cur.execute(
                    "SELECT item_id, item_cuisine FROM public.menu_item WHERE item_id = ANY(%s)",
                    (item_ids,)
                )
                cat_map = {row[0]: row[1] or "fast_food" for row in cur.fetchall()}
                for it in res.get("recommended_items", []):
                    if it.get("item_id") in cat_map:
                        it["category"] = cat_map[it["item_id"]]
            
            deal_ids = [d.get("deal_id") for d in res.get("recommended_deals", []) if d.get("deal_id")]
            if deal_ids:
                cur.execute(
                    """
                    SELECT d.deal_id, 
                           string_agg(di.quantity::text || ' ' || mi.item_name, ', ' ORDER BY mi.item_id) AS items
                    FROM deal d
                    JOIN deal_item di ON di.deal_id = d.deal_id
                    JOIN menu_item mi ON mi.item_id = di.menu_item_id
                    WHERE d.deal_id = ANY(%s)
                    GROUP BY d.deal_id
                    """,
                    (deal_ids,)
                )
                deal_items_map = {row[0]: row[1] or "" for row in cur.fetchall()}
                for d in res.get("recommended_deals", []):
                    d["category"] = "fast_food"
                    d["items"] = deal_items_map.get(d.get("deal_id"), "")
                
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()



# CORS for Flutter
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def format_items_urdu(menu_items, deals):
    response_parts = []

    # MENU ITEMS
    if menu_items:
        for item in menu_items:
            response_parts.append(
                f"جی بالکل! {item['item_name']} دستیاب ہے۔\n"
                f"{item['item_description']}۔\n"
                f"ایک پلیٹ تقریباً {item['serving_size']} افراد کیلئے کافی ہوتی ہے۔\n"
                f"قیمت Rs {item['item_price']} ہے۔\n"
            )

    # DEALS
    if deals:
        for deal in deals:
            response_parts.append(
                f"ہمارا شاندار پیکج {deal['deal_name']} بھی موجود ہے۔\n"
                f"اس میں شامل ہیں: {deal['items']}۔\n"
                f"یہ پیکج {deal['serving_size']} افراد کیلئے بہترین ہے۔\n"
                f"کل قیمت Rs {deal['deal_price']} ہے۔\n"
                f"کیا آپ اس ڈیل کو آرڈر میں شامل کرنا چاہیں گے؟\n"
            )

    if not menu_items and not deals:
        return "معذرت، اس نام سے کوئی ڈش یا ڈیل موجود نہیں ہے۔"

    return "\n".join(response_parts)


@app.on_event("startup")
def warmup_whisper():
    if not VOICE_ENABLED:
        print("Whisper warm-up skipped: Voice feature disabled")
        return
    print("Warming up Whisper model...")
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))   # backend/
        project_root = os.path.dirname(base_dir)                # project root
        audio_path = os.path.join(project_root, "voice", "empty.wav")

        if not os.path.exists(audio_path):
            print("Whisper warm-up skipped: empty.wav not found at:", audio_path)
            return

        transcribe_audio(audio_path)
        print("Whisper warm-up complete!")

    except Exception as e:
        print("Whisper warm-up failed:", e)

@app.get("/offers")
def get_offers():
    query = text("""
        SELECT offer_id, title, description, offer_code, validity, category
        FROM offers
        WHERE validity >= CURRENT_DATE
        ORDER BY validity ASC;
    """)

    with SQL_ENGINE.connect() as conn:
        rows = conn.execute(query).mappings().all()

    # Convert RowMapping -> dict for JSON
    return [dict(r) for r in rows]


@app.get("/menu")
def get_full_menu():
    query = text("""
       SELECT 
    item_id,
    item_name,
    item_description,
    item_category,
    item_cuisine,
    item_price,
    quantity_description,
    image_url
FROM menu_item
ORDER BY item_id;


    """)
    with SQL_ENGINE.connect() as conn:
        rows = conn.execute(query).mappings().all()

    return {"menu": list(rows)}


def fetch_menu_items_by_name(name: str):
    query = text("""
        SELECT 
            item_id,
            item_name,
            item_description,
            item_category,
            item_cuisine,
            item_price,
            serving_size,
            quantity_description,
            prep_time_minutes,
            image_url
        FROM menu_item
        WHERE 
            item_name ILIKE :name
            OR item_category ILIKE :name
            OR item_cuisine ILIKE :name
        ORDER BY item_id
        LIMIT 20;
    """)

    with SQL_ENGINE.connect() as conn:
        rows = conn.execute(query, {"name": f"%{name}%"}).mappings().all()

    return [dict(r) for r in rows]


def fetch_deals_by_name(name: str):
    query = text("""
        SELECT 
            d.deal_id, 
            d.deal_name, 
            d.deal_price, 
            d.serving_size,
            d.image_url,
            string_agg(
                di.quantity::text || ' ' || mi.item_name,
                ', ' ORDER BY mi.item_id
            ) AS items
        FROM deal d
        JOIN deal_item di ON di.deal_id = d.deal_id
        JOIN menu_item mi ON mi.item_id = di.menu_item_id
        WHERE 
            d.deal_name ILIKE :name
            OR mi.item_name ILIKE :name
            OR mi.item_category ILIKE :name
            OR mi.item_cuisine ILIKE :name
        GROUP BY 
            d.deal_id, 
            d.deal_name, 
            d.deal_price, 
            d.serving_size,
            d.image_url
        ORDER BY d.deal_id
        LIMIT 20;
    """)

    with SQL_ENGINE.connect() as conn:
        rows = conn.execute(query, {"name": f"%{name}%"}).mappings().all()

    return [dict(r) for r in rows]


# ------------------------------
# TEXT CHAT ENDPOINT
# ------------------------------

def format_results_response(menu_items, deals, language: str = "ur") -> str:
    """
    Build a user-facing reply strictly from database results.
    No hallucinations – only uses fields from menu_items and deals.
    """
    if not menu_items and not deals:
        if language == "en":
            return "Sorry, we could not find anything matching your request in our menu."
        return "معاف کیجیے، آپ کی درخواست کے مطابق ہمارے مینو میں کچھ نہیں ملا۔"

    lines = []

    # Menu items section
    if menu_items:
        if language == "en":
            lines.append("These items are available:")
        else:
            lines.append("یہ آئٹمز دستیاب ہیں:")

        for item in menu_items[:6]:  # limit to top 6
            name = item.get("item_name", "")
            desc = item.get("item_description", "") or ""
            price = item.get("item_price", 0)
            qty   = item.get("quantity_description", "") or ""
            cuisine = item.get("item_cuisine", "")
            category = item.get("item_category", "")

            if language == "en":
                line = f"- {name} – {desc} ({cuisine}, {category}) – Rs {price} ({qty})"
            else:
                line = f"- {name} – {desc} ({cuisine}, {category}) – قیمت: Rs {price} ({qty})"
            lines.append(line)

    # Deals section
    if deals:
        lines.append("")  # blank line

        if language == "en":
            lines.append("These deals are available:")
        else:
            lines.append("یہ ڈیلز دستیاب ہیں:")

        for deal in deals[:6]:
            name = deal.get("deal_name", "")
            items = deal.get("items", "") or ""
            price = deal.get("deal_price", 0)
            serving = deal.get("serving_size", 0)

            if language == "en":
                line = f"- {name} – {items} – Rs {price} (serves {serving} person)"
            else:
                line = f"- {name} – {items} – قیمت: Rs {price} (تقریباً {serving} افراد کیلئے)"
            lines.append(line)

    return "\n".join(lines)


# ------------------------------
# TEXT CHAT ENDPOINT
# ------------------------------

class TextChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    language: str = "ur"   # "ur" or "en"


@app.post("/chat")
async def chat_text_endpoint(req: TextChatRequest):
    user_text = req.message.strip()

    if not user_text:
        return {"success": False, "reply": "پیغام خالی ہے", "raw": {}}

    # 1) Let LLM decide TOOL_CALLS (intent + query)
    ai_response = get_ai_response(
        user_input=user_text,
        conversation_history=[],
        menu_context=""
    )

    tool_calls = getattr(ai_response, "tool_calls", [])

    menu_items = []
    deals = []
    used_search_tool = False

    # 2) Execute DB searches based on TOOL_CALLs
    for call in tool_calls:
        if call["name"] == "search_menu":
            used_search_tool = True
            query = call["args"].get("query", "")
            menu_items = fetch_menu_items_by_name(query)
            deals = fetch_deals_by_name(query)

    # 3) Decide final reply text
    if used_search_tool:
        # Ignore model free-text and build reply ONLY from DB results
        reply_text = format_results_response(menu_items, deals, language=req.language)
    else:
        # No search requested – just use the model's original reply (small talk etc.)
        reply_text = ai_response.content if hasattr(ai_response, "content") else str(ai_response)

    urdu_reply = format_items_urdu(menu_items, deals) if (menu_items or deals) else reply_text

    return {
       "success": True,
       "reply": urdu_reply,
       "menu_items": menu_items,
       "deals": deals,
       "raw": reply_text
    }



# ------------------------------
# VOICE CHAT ENDPOINT
# ------------------------------

# ------------------------------
# VOICE CHAT ENDPOINT
# ------------------------------
@app.post("/voice_chat")
async def chat_voice_endpoint(
    session_id: str = Form(...),
    language: str = Form("ur"),
    file: UploadFile = File(...)
):
    if not VOICE_ENABLED:
        return JSONResponse(
            status_code=503,
            content={"error": "Voice feature is temporarily disabled"}
        )
    os.makedirs("temp_voice", exist_ok=True)
    audio_path = f"temp_voice/{file.filename}"

    with open(audio_path, "wb") as f:
        f.write(await file.read())

    # 1) Transcribe audio
    transcript = transcribe_audio(audio_path)

    # 2) Get AI tool-call response
    ai_response = get_ai_response(
        user_input=transcript,
        conversation_history=[],
        menu_context=""
    )

    tool_calls = getattr(ai_response, "tool_calls", [])

    menu_items = []
    deals = []
    used_search_tool = False

    # 3) Execute tool calls (search)
    for call in tool_calls:
        if call["name"] == "search_menu":
            used_search_tool = True
            query = call["args"].get("query", "")
            menu_items = fetch_menu_items_by_name(query)
            deals = fetch_deals_by_name(query)

    # 4) Format reply text
    if used_search_tool:
        reply_text = format_items_urdu(menu_items, deals)
    else:
        reply_text = ai_response.content if hasattr(ai_response, "content") else str(ai_response)

    return {
        "success": True,
        "transcript": transcript,
        "reply": reply_text,
        "menu_items": menu_items,
        "deals": deals,
        "raw": reply_text,
    }


@app.get("/deals")
def get_all_deals():
    query = text("""
        SELECT 
            d.deal_id, 
            d.deal_name, 
            d.deal_price, 
            d.serving_size,
            d.image_url,
            string_agg(
                di.quantity::text || ' ' || mi.item_name,
                ', ' ORDER BY mi.item_id
            ) AS items
        FROM deal d
        JOIN deal_item di ON di.deal_id = d.deal_id
        JOIN menu_item mi ON mi.item_id = di.menu_item_id
        GROUP BY 
            d.deal_id, 
            d.deal_name, 
            d.deal_price, 
            d.serving_size,
            d.image_url
        ORDER BY d.deal_id;
    """)

    with SQL_ENGINE.connect() as conn:
        rows = conn.execute(query).mappings().all()

    return {"deals": rows}


# ------------------------------
# CUSTOM DEAL ENDPOINT
# ------------------------------

class CustomDealRequest(BaseModel):
    query: str
    user_id: Optional[str] = None


@app.post("/deals/custom")
async def create_custom_deal(req: CustomDealRequest):
    """
    Create a custom deal based on user's natural language query.
    Example queries:
    - "make a deal for 3 people with biryani and burger"
    - "create a Pakistani food deal for 5 people"
    - "I want fast food for 2 people"
    """
    if not req.query.strip():
        return {"success": False, "message": "Please describe what kind of deal you'd like."}
    
    try:
        result = custom_deal_agent.create_deal(req.query)
        return result
    except Exception as e:
        print(f"[CustomDeal] Error: {e}")
        return {"success": False, "message": "Sorry, couldn't create the deal. Please try again."}


@app.get("/upsell")
def get_upsell(city: str = "Islamabad"):
    """Weather-based upsell recommendations. No auth required."""
    return upsell_agent.weather_upsell(city)


@app.get("/cart/{cart_id}/recommendations")
def get_cart_recommendations(
    cart_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Rule-based cross-sell recommendations for items in the cart."""
    with SQL_ENGINE.connect() as conn:
        # Verify cart belongs to requesting user
        cart_row = conn.execute(
            text("SELECT user_id FROM cart WHERE cart_id = :cid LIMIT 1"),
            {"cid": cart_id},
        ).mappings().fetchone()

        if not cart_row or str(cart_row["user_id"]) != str(current_user["user_id"]):
            return {"recommendations": []}

        # Fetch cart items with their menu_item category
        items = conn.execute(
            text("""
                SELECT ci.item_id, ci.item_name, ci.item_type,
                       mi.item_category
                FROM cart_items ci
                LEFT JOIN menu_item mi ON mi.item_id = ci.item_id AND ci.item_type = 'menu_item'
                WHERE ci.cart_id = :cid
            """),
            {"cid": cart_id},
        ).mappings().all()

    if not items:
        return {"recommendations": []}

    all_names = [r["item_name"] for r in items if r["item_name"]]
    exclude_categories = {"drink", "side", "starter", "bread"}

    main_items = [
        r for r in items
        if r["item_type"] == "menu_item"
        and (r["item_category"] or "").lower() not in exclude_categories
    ]

    seen_recommendations: set = set()
    results: List[Dict] = []

    for item in main_items:
        rec = recommendation_engine.get_recommendation(item["item_name"], all_names)
        if not rec.get("success"):
            continue

        rec_name = rec["recommended_item"]
        if rec_name.lower() in seen_recommendations:
            continue
        seen_recommendations.add(rec_name.lower())

        # Look up item_id and price from menu_item table
        with SQL_ENGINE.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT item_id, item_price
                    FROM menu_item
                    WHERE LOWER(item_name) = LOWER(:name)
                    LIMIT 1
                """),
                {"name": rec_name},
            ).mappings().fetchone()

        if not row:
            continue

        results.append({
            "for_item": item["item_name"],
            "recommended_name": rec_name,
            "recommended_item_id": int(row["item_id"]),
            "recommended_price": float(row["item_price"]),
            "reason": rec["reason"],
        })

    return {"recommendations": results}

@app.get("/health")
def health():
    return {"status": "ok"}


# =========================================================
# KITCHEN DASHBOARD ENDPOINTS
# =========================================================

@app.get("/kitchen/orders")
def kitchen_get_orders():
    """Return all active kitchen tasks grouped by order_id, with customer info."""
    db = DatabaseConnection.get_instance()
    import psycopg2.extras
    with db.get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT kt.task_id, kt.order_id, kt.item_name, kt.qty, kt.station,
                       kt.assigned_chef, kt.estimated_minutes, kt.status,
                       COALESCE(NULLIF(u.full_name,''), NULLIF(u.email,''), NULLIF(u.phone,''), 'Unknown') AS customer_name,
                       u.user_id AS customer_id
                FROM kitchen_tasks kt
                LEFT JOIN orders o ON o.order_id = kt.order_id
                LEFT JOIN cart c ON c.cart_id = o.cart_id
                LEFT JOIN auth.app_users u ON u.user_id = c.user_id
                WHERE kt.status IN ('QUEUED', 'IN_PROGRESS', 'READY')
                ORDER BY kt.order_id, kt.task_id
            """)
            rows = cur.fetchall()

    # Group by order_id
    STATUS_RANK = {"QUEUED": 0, "IN_PROGRESS": 1, "READY": 2}
    orders: dict = {}
    for row in rows:
        oid = row["order_id"]
        if oid not in orders:
            orders[oid] = {
                "order_id": oid,
                "tasks": [],
                "overall_status": "READY",
                "customer_name": row["customer_name"],
                "customer_id": str(row["customer_id"]) if row["customer_id"] else "",
            }
        orders[oid]["tasks"].append(dict(row))
        if STATUS_RANK.get(row["status"], 2) < STATUS_RANK.get(orders[oid]["overall_status"], 2):
            orders[oid]["overall_status"] = row["status"]

    return {"orders": list(orders.values())}


class KitchenStatusUpdate(BaseModel):
    new_status: str


@app.post("/kitchen/tasks/{task_id}/update-status")
def kitchen_update_task_status(task_id: str, body: KitchenStatusUpdate):
    """Publish update_status command to Redis, wait for response."""
    allowed = {"IN_PROGRESS", "READY", "COMPLETED"}
    if body.new_status not in allowed:
        raise HTTPException(status_code=400, detail=f"new_status must be one of {allowed}")

    response_channel = f"resp_{uuid.uuid4().hex}"
    message = {
        "agent": "kitchen",
        "command": "update_status",
        "payload": {"task_id": task_id, "new_status": body.new_status},
        "response_channel": response_channel,
    }

    pubsub = _REDIS_CLIENT.pubsub()
    pubsub.subscribe(response_channel)
    # Drain the subscribe-confirmation message before publishing
    pubsub.get_message(timeout=0.1)

    _REDIS_CLIENT.publish(AGENT_TASKS_CHANNEL, json.dumps(message))

    # Poll with get_message() so the timeout is actually enforced
    deadline = _time.time() + 5
    result = None
    while _time.time() < deadline:
        msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
        if msg and msg["type"] == "message":
            result = json.loads(msg["data"])
            break
        _time.sleep(0.05)

    pubsub.unsubscribe(response_channel)
    pubsub.close()

    if result is None:
        raise HTTPException(status_code=504, detail="Kitchen agent did not respond in time. Is it running?")
    return result


@app.get("/orders/{order_id}/tracking")
def get_order_tracking(
    order_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Lightweight polling endpoint — returns only status + prep time."""
    with SQL_ENGINE.connect() as conn:
        row = conn.execute(
            text("SELECT order_id, status, estimated_prep_time_minutes FROM orders WHERE order_id = :oid"),
            {"oid": order_id},
        ).mappings().fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "order_id": row["order_id"],
        "status": row["status"],
        "estimated_prep_time_minutes": row["estimated_prep_time_minutes"] or 0,
    }


@app.get("/kitchen/dashboard")
def kitchen_dashboard():
    """Serve the kitchen web dashboard."""
    html_path = os.path.join(os.path.dirname(__file__), "kitchen", "kitchen_dashboard_ui.html")
    return FileResponse(html_path, media_type="text/html")


# ─────────────────────────────────────────────────────────────────
# SAVED CARDS ENDPOINTS
# ─────────────────────────────────────────────────────────────────

class AddCardRequest(BaseModel):
    card_type: str
    last4: str
    cardholder_name: str
    expiry: str


@app.post("/cards/add")
def add_card(
    req: AddCardRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user_id = str(current_user["user_id"])
    db = DatabaseConnection.get_instance()
    import psycopg2.extras
    with db.get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Check if user already has cards — first card becomes default
            cur.execute("SELECT COUNT(*) AS cnt FROM saved_cards WHERE user_id = %s", (user_id,))
            is_first = cur.fetchone()["cnt"] == 0
            cur.execute(
                """
                INSERT INTO saved_cards (user_id, card_type, last4, cardholder_name, expiry, is_default)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING card_id
                """,
                (user_id, req.card_type, req.last4, req.cardholder_name, req.expiry, is_first),
            )
            card_id = cur.fetchone()["card_id"]
        conn.commit()
    return {"success": True, "card_id": card_id, "message": "Card saved successfully"}


@app.get("/cards")
def get_cards(current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    db = DatabaseConnection.get_instance()
    import psycopg2.extras
    with db.get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT card_id, card_type, last4, cardholder_name, expiry, is_default
                FROM saved_cards
                WHERE user_id = %s
                ORDER BY is_default DESC, created_at ASC
                """,
                (user_id,),
            )
            rows = cur.fetchall()
    return {"cards": [dict(r) for r in rows]}


@app.delete("/cards/{card_id}")
def delete_card(
    card_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user_id = str(current_user["user_id"])
    db = DatabaseConnection.get_instance()
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM saved_cards WHERE card_id = %s AND user_id = %s",
                (card_id, user_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Card not found or not yours")
        conn.commit()
    return {"success": True}


# ─────────────────────────────────────────────────────────────────
# MOCK PAYMENT ENDPOINTS
# ─────────────────────────────────────────────────────────────────

class ProcessPaymentRequest(BaseModel):
    cart_id: str
    amount: float
    card_id: int


@app.post("/payment/process")
def process_payment(
    req: ProcessPaymentRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user_id = str(current_user["user_id"])
    db = DatabaseConnection.get_instance()
    import psycopg2.extras
    try:
        with db.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Verify the card belongs to this user
                cur.execute(
                    "SELECT card_id, card_type, last4, cardholder_name FROM saved_cards WHERE card_id = %s AND user_id = %s",
                    (req.card_id, user_id),
                )
                card = cur.fetchone()
                if not card:
                    raise HTTPException(status_code=403, detail="Card not found or does not belong to you")

                transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"

                cur.execute(
                    """
                    INSERT INTO payments
                      (transaction_id, order_id, user_id, card_id, amount, card_last4, card_type, cardholder_name, status)
                    VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, 'SUCCESS')
                    """,
                    (
                        transaction_id, user_id, req.card_id,
                        req.amount, card["last4"], card["card_type"], card["cardholder_name"],
                    ),
                )
            conn.commit()
        return {"success": True, "transaction_id": transaction_id, "message": "Payment processed successfully"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Payment failed. Please try again.")


class LinkOrderRequest(BaseModel):
    order_id: int


@app.put("/payment/{transaction_id}/link-order")
def link_payment_to_order(
    transaction_id: str,
    req: LinkOrderRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user_id = str(current_user["user_id"])
    db = DatabaseConnection.get_instance()
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE payments SET order_id = %s WHERE transaction_id = %s AND user_id = %s",
                (req.order_id, transaction_id, user_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Payment record not found")
            # Also store transaction_id on the order
            cur.execute(
                "UPDATE orders SET transaction_id = %s WHERE order_id = %s",
                (transaction_id, req.order_id),
            )
        conn.commit()
    return {"success": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
