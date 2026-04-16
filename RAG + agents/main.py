# main.py

import os
import uuid
import json
import time as _time
import asyncio
from types import SimpleNamespace
import redis as redis_lib
from auth.auth_routes import router as auth_router
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, Any

# Voice transcription is optional - will be added later
try:
    from voice.transcribe import transcribe_audio, warmup_transcriber
    VOICE_ENABLED = True
except Exception as e:
    print(f"[WARNING] Voice transcription disabled: {e}")
    transcribe_audio = None
    warmup_transcriber = None
    VOICE_ENABLED = False

from chat.chat_agent import get_ai_response
from voice.urdu_translator import translate_urdu_to_english
from dotenv import load_dotenv
from sqlalchemy import text
import logging
import re


from cart.cart_routes import router as cart_router
from orders.order_routes import router as order_router
from feedback.feedback_routes import router as feedback_router
from custom_deal.custom_deal_routes import router as custom_deal_router
from favourites.favourites_routes import router as favourites_router
from admin.admin_routes import router as admin_router
from dine_in.dine_in_routes import router as dine_in_router
from admin.table_routes import router as admin_tables_router
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
logger = logging.getLogger("voice_nlp")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

_SESSION_MEMORY: Dict[str, Dict[str, Any]] = {}
_HISTORY_WINDOW = 10
_PEOPLE_WORD_MAP = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "ek": 1, "do": 2, "teen": 3, "chaar": 4, "paanch": 5,
    "چھ": 6, "سات": 7, "آٹھ": 8, "نو": 9, "دس": 10,
    "ایک": 1, "دو": 2, "تین": 3, "چار": 4, "پانچ": 5,
}

def _detect_text_language(text: str, requested_lang: str = "ur") -> str:
    requested = (requested_lang or "ur").strip().lower()
    if requested == "en":
        return "en"
    urdu_chars = sum(1 for c in text if "\u0600" <= c <= "\u06ff")
    alpha_chars = sum(1 for c in text if c.isalpha())
    if urdu_chars > 0 and urdu_chars >= max(1, alpha_chars // 5):
        return "ur"
    return "en"

def _extract_keywords_intent(text: str) -> Dict[str, Any]:
    t = (text or "").lower()
    cuisine = None
    if "chinese" in t:
        cuisine = "chinese"
    elif "fast food" in t or "burger" in t or "zinger" in t:
        cuisine = "fast_food"
    elif "desi" in t or "pakistani" in t:
        cuisine = "desi"
    elif "bbq" in t or "barbeque" in t:
        cuisine = "bbq"

    people = None
    m = re.search(r"\b([1-9][0-9]?)\s*(people|person|log|afrad)?\b", t)
    if m:
        people = int(m.group(1))
    if people is None:
        for word, num in _PEOPLE_WORD_MAP.items():
            if re.search(rf"\b{re.escape(word)}\b", t):
                people = num
                break

    if any(k in t for k in ["deal", "deals"]):
        intent = "search_deal"
    elif any(k in t for k in ["menu", "item", "dish"]):
        intent = "search_menu"
    elif any(k in t for k in ["place order", "confirm order", "checkout"]):
        intent = "place_order"
    else:
        intent = "general_chat"

    return {
        "intent": intent,
        "keywords": {
            "cuisine": cuisine,
            "people": people,
            "query_text": text,
        },
    }

def _remember_context(session_id: str, nlp: Dict[str, Any], turns_limit: int = _HISTORY_WINDOW) -> Dict[str, Any]:
    ctx = _SESSION_MEMORY.get(session_id, {"turns": [], "slots": {}})
    slots = ctx.get("slots", {})
    kws = (nlp or {}).get("keywords", {})
    if kws.get("cuisine"):
        slots["cuisine"] = kws["cuisine"]
    if kws.get("people"):
        slots["people"] = kws["people"]
    if (nlp or {}).get("intent"):
        slots["last_intent"] = nlp["intent"]
    ctx["slots"] = slots
    ctx["turns"].append(nlp)
    if len(ctx["turns"]) > turns_limit:
        ctx["turns"] = ctx["turns"][-turns_limit:]
    _SESSION_MEMORY[session_id] = ctx
    return ctx

def _is_custom_deal_confirmation(text: str) -> bool:
    t = (text or "").strip().lower()
    if re.fullmatch(r"(yes|ok|okay|theek hai|ٹھیک ہے|haan|han|جی|confirm)[.!?]?", t):
        return True
    has_custom_phrase = bool(re.search(r"\b(custom deal|create deal|make deal)\b", t))
    has_affirmation = bool(re.search(r"\b(yes|ok|okay|confirm|haan|han|جی)\b", t))
    return has_custom_phrase and has_affirmation

def _voice_log(session_id: str, stage: str, **fields: Any) -> None:
    lines = [f"[VOICE][{stage}] session={session_id}"]
    for k, v in fields.items():
        lines.append(f"  {k}: {v}")
    logger.info("\n".join(lines))

def _filter_deals_by_people(deals: List[Dict[str, Any]], people: Optional[int]) -> List[Dict[str, Any]]:
    if not people:
        return deals
    exact = [d for d in deals if int(d.get("serving_size") or 0) == people]
    if exact:
        return exact
    # fallback: nearest serving size
    return sorted(deals, key=lambda d: abs(int(d.get("serving_size") or 0) - people))

def _search_deals_from_nlp(nlp: Dict[str, Any], normalized_text: str) -> List[Dict[str, Any]]:
    kws = (nlp or {}).get("keywords", {})
    query = kws.get("cuisine") or normalized_text
    deals = fetch_deals_by_name(query)
    return _filter_deals_by_people(deals, kws.get("people"))

def _build_deal_tool_calls(nlp: Dict[str, Any]) -> List[Dict[str, Any]]:
    kws = (nlp or {}).get("keywords", {})
    args: Dict[str, str] = {}
    if kws.get("cuisine"):
        args["cuisine"] = str(kws["cuisine"])
    if kws.get("people"):
        args["person_count"] = str(kws["people"])
    return [{"name": "search_deal", "args": args}]


def _clean_item_name(raw: str) -> str:
    name = re.sub(r"\b(to|into|in|my|the|a|an|cart|please)\b", " ", raw, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip(" .,!?")
    if name.endswith(" burgers"):
        name = name[:-1]
    return name.title()


def _deterministic_chat_tool_calls(text: str, nlp: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    t = (text or "").strip().lower()
    if not t:
        return None

    if ("ingredient" in t or "allergen" in t or "allergy" in t) and (" for " in t):
        query = t.split(" for ", 1)[1].strip()
        return [{"name": "retrieve_menu_context", "args": {"query": query}}]

    if ("custom deal" in t or "create a custom deal" in t) and not re.search(
        r"\b(yes|ok|okay|theek hai|ٹھیک ہے|haan|han|جی|confirm)\b", t
    ):
        return [{"name": "create_custom_deal", "args": {"query": text}}]

    if nlp.get("intent") == "search_deal":
        return None

    if "my orders" in t or "go to orders" in t or "open orders" in t:
        return [{"name": "navigate_to", "args": {"screen": "orders"}}]

    if "open cart" in t or "show cart" in t:
        return [{"name": "show_cart", "args": {}}]

    m_add = re.search(r"\badd\s+(?:(\d+)\s+)?(.+)$", t)
    if m_add:
        qty = int(m_add.group(1)) if m_add.group(1) else 1
        item = _clean_item_name(m_add.group(2))
        return [{"name": "add_to_cart", "args": {"item_name": item, "quantity": str(qty)}}]

    m_remove = re.search(r"\bremove\s+(.+)$", t)
    if m_remove:
        item = _clean_item_name(m_remove.group(1))
        return [{"name": "remove_from_cart", "args": {"item_name": item}}]

    m_change = re.search(r"\b(?:change|set)\s+(.+?)\s+(?:quantity\s+)?to\s+(\d+)\b", t)
    if m_change:
        item = _clean_item_name(m_change.group(1))
        qty = m_change.group(2)
        return [{"name": "change_quantity", "args": {"item_name": item, "quantity": str(qty)}}]
    m_change_alt = re.search(r"\b(?:change|set)\s+(?:quantity\s+)?(?:of\s+)?(.+?)\s+to\s+(\d+)\b", t)
    if m_change_alt:
        item = _clean_item_name(m_change_alt.group(1))
        qty = m_change_alt.group(2)
        return [{"name": "change_quantity", "args": {"item_name": item, "quantity": str(qty)}}]

    if ("place" in t and "order" in t) or "checkout" in t:
        if any(k in t for k in ["card", "credit", "debit"]):
            pm = "CARD"
        elif any(k in t for k in ["cash", "cod", "delivery"]):
            pm = "COD"
        else:
            pm = "COD"
        return [{"name": "place_order", "args": {"payment_method": pm}}]

    if "what should i eat" in t or "recommend" in t or "suggest" in t:
        return [{"name": "get_recommendations", "args": {}}]

    if "where is my order" in t or "order status" in t or "track my order" in t:
        return [{"name": "get_order_status", "args": {}}]

    if "favourite" in t or "favorite" in t:
        return [{"name": "manage_favourites", "args": {"action": "show"}}]

    return None


def _deal_no_match_reply(cuisine: Optional[str], people: Optional[int], language: str) -> str:
    cuisine_txt = cuisine or ("desired cuisine" if language == "en" else "پسندیدہ کھانے")
    people_txt = str(people) if people else ("your group" if language == "en" else "آپ کے گروپ")
    if language == "en":
        return f"I couldn't find an exact deal for {cuisine_txt} for {people_txt}. Would you like a custom deal?"
    return f"مجھے {cuisine_txt} میں {people_txt} افراد کیلئے بالکل یہی ڈیل نہیں ملی۔ کیا آپ کسٹم ڈیل بنوانا چاہیں گے؟"


def _voice_timeout_reply(language: str, stage: str) -> str:
    if stage == "asr":
        if language == "en":
            return "I couldn't process your voice in time. Please speak a shorter sentence and try again."
        return "میں آپ کی آواز وقت پر پراسیس نہیں کر سکا۔ براہِ کرم چھوٹا جملہ بول کر دوبارہ کوشش کریں۔"
    if language == "en":
        return "I’m a bit slow right now, but I understood your request. Please try again once."
    return "میں ابھی کچھ سست ہوں، مگر آپ کی بات سمجھ گیا ہوں۔ براہِ کرم ایک بار پھر کوشش کریں۔"


def _normalize_history_window(raw_history: Any, limit: int = _HISTORY_WINDOW) -> List[Dict[str, str]]:
    if not isinstance(raw_history, list):
        return []
    normalized: List[Dict[str, str]] = []
    for msg in raw_history:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "")).strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = msg.get("content")
        if content is None:
            content = msg.get("text")
        content_text = str(content or "").strip()
        if not content_text:
            continue
        normalized.append({"role": role, "content": content_text})
    if limit <= 0:
        return normalized
    return normalized[-limit:]


# Initialize AI agent


app = FastAPI()

app.include_router(auth_router)
app.include_router(cart_router)
app.include_router(order_router)
app.include_router(feedback_router)
app.include_router(custom_deal_router)
app.include_router(favourites_router)
app.include_router(admin_router)
app.include_router(dine_in_router)
app.include_router(admin_tables_router)


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
        if warmup_transcriber is None:
            print("Whisper warm-up skipped: transcriber unavailable")
            return

        warmup_transcriber()
        print("Whisper warm-up complete!")

    except Exception as e:
        print("Whisper warm-up failed:", repr(e))

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


def fetch_deals_for_voice(cuisine: str = "") -> List[Dict[str, Any]]:
    cuisine = (cuisine or "").strip()
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
            :cuisine = ''
            OR d.deal_name ILIKE :like_cuisine
            OR mi.item_name ILIKE :like_cuisine
            OR mi.item_category ILIKE :like_cuisine
            OR mi.item_cuisine ILIKE :like_cuisine
        GROUP BY
            d.deal_id,
            d.deal_name,
            d.deal_price,
            d.serving_size,
            d.image_url
        ORDER BY d.deal_id
        LIMIT 50;
    """)

    with SQL_ENGINE.connect() as conn:
        rows = conn.execute(
            query,
            {"cuisine": cuisine, "like_cuisine": f"%{cuisine}%"},
        ).mappings().all()
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
    message: Optional[str] = None
    text: Optional[str] = None
    language: Optional[str] = "ur"   # "ur" or "en"
    lang: Optional[str] = None


@app.post("/chat")
@app.post("/chat/text")
async def chat_text_endpoint(req: TextChatRequest):
    user_text = (req.message or req.text or "").strip()
    session_id = (req.session_id or "text-default").strip()
    language = (req.language or req.lang or "ur").strip().lower()
    if language not in {"ur", "en"}:
        language = "ur"

    if not user_text:
        return {"success": False, "reply": "پیغام خالی ہے", "raw": {}}

    detected_lang = _detect_text_language(user_text, language)
    normalized_text = translate_urdu_to_english(user_text) if detected_lang == "ur" else user_text
    nlp = _extract_keywords_intent(normalized_text)
    mem = _remember_context(session_id, nlp)
    logger.info(
        "[CHAT] session=%s in_lang=%s detected_lang=%s normalized='%s' intent=%s keywords=%s",
        session_id,
        language,
        detected_lang,
        normalized_text,
        nlp["intent"],
        nlp["keywords"],
    )

    if _is_custom_deal_confirmation(normalized_text):
        slots = mem.get("slots", {}) if mem else {}
        if not slots.get("pending_custom_deal") and not (slots.get("cuisine") or slots.get("people")):
            reply_text = (
                "Kis cheez ke liye haan keh rahe hain?"
                if language != "en"
                else "What would you like me to confirm?"
            )
            return {
                "success": True,
                "reply": reply_text,
                "menu_items": [],
                "deals": [],
                "tool_calls": [],
                "nlp": nlp,
                "memory_slots": slots,
                "raw": "confirmation-without-context",
            }
        cuisine_txt = slots.get("cuisine", "")
        people_txt = slots.get("people", "")
        if cuisine_txt and people_txt:
            custom_query = f"create {cuisine_txt} deal for {people_txt} people"
        elif cuisine_txt:
            custom_query = f"create {cuisine_txt} deal"
        else:
            custom_query = normalized_text
        result = custom_deal_agent.create_deal(custom_query)
        slots["pending_custom_deal"] = False
        if mem is not None:
            mem["slots"] = slots
            _SESSION_MEMORY[session_id] = mem
        logger.info("[CHAT] session=%s custom_deal_query='%s' result_success=%s", session_id, custom_query, result.get("success"))
        return {
            "success": True,
            "reply": result.get("message", "Custom deal generated."),
            "menu_items": [],
            "deals": [result] if result.get("success") else [],
            "tool_calls": [],
            "nlp": nlp,
        "memory_slots": slots,
        "raw": result,
    }

    deterministic_calls = _deterministic_chat_tool_calls(normalized_text, nlp)
    if deterministic_calls:
        return {
            "success": True,
            "reply": "Done.",
            "menu_items": [],
            "deals": [],
            "tool_calls": deterministic_calls,
            "nlp": nlp,
            "memory_slots": mem.get("slots", {}) if mem else {},
            "raw": "deterministic-routing",
        }

    # 1) Let LLM decide TOOL_CALLS (intent + query)
    ai_response = get_ai_response(
        user_input=normalized_text,
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

    # Deterministic deal-first path: avoid wrong LLM query opening menu-all view.
    if nlp["intent"] == "search_deal":
        deals = _search_deals_from_nlp(nlp, normalized_text)
        menu_items = []
        tool_calls = _build_deal_tool_calls(nlp)
        used_search_tool = True

    # Deterministic fallback: if deal intent but no deals, ask for custom deal using memory slots.
    if not deals and nlp["intent"] == "search_deal":
        slots = mem.get("slots", {}) if mem else {}
        slots["pending_custom_deal"] = True
        if mem is not None:
            mem["slots"] = slots
            _SESSION_MEMORY[session_id] = mem
        reply_text = _deal_no_match_reply(
            slots.get("cuisine"),
            slots.get("people"),
            language,
        )
        return {
            "success": True,
            "reply": reply_text,
            "menu_items": menu_items,
            "deals": deals,
            "tool_calls": tool_calls,
            "nlp": nlp,
            "memory_slots": slots,
            "raw": ai_response.content if hasattr(ai_response, "content") else str(ai_response),
        }

    # 3) Decide final reply text
    if used_search_tool:
        # Ignore model free-text and build reply ONLY from DB results
        if language == "en":
            reply_text = format_results_response(menu_items, deals, language="en")
        else:
            reply_text = format_items_urdu(menu_items, deals)
    else:
        # No search requested – just use the model's original reply (small talk etc.)
        reply_text = ai_response.content if hasattr(ai_response, "content") else str(ai_response)

    return {
       "success": True,
       "reply": reply_text,
       "menu_items": menu_items,
       "deals": deals,
       "tool_calls": tool_calls,
       "nlp": nlp,
       "memory_slots": mem.get("slots", {}) if mem else {},
       "raw": ai_response.content if hasattr(ai_response, "content") else str(ai_response)
    }



# ------------------------------
# VOICE CHAT ENDPOINT
# ------------------------------

# ------------------------------
# VOICE CHAT ENDPOINT
# ------------------------------
@app.get("/voice/deal_check")
def voice_deal_check(cuisine: str = "", person_count: int = 0):
    cuisine_norm = (cuisine or "").strip().lower()
    all_deals = fetch_deals_for_voice(cuisine_norm)
    available_sizes = sorted(
        {int(d.get("serving_size") or 0) for d in all_deals if int(d.get("serving_size") or 0) > 0}
    )

    exact_deals = all_deals
    if person_count > 0:
        exact_deals = [d for d in all_deals if int(d.get("serving_size") or 0) == person_count]

    if exact_deals:
        if person_count > 0:
            msg_en = f"Great! I found {len(exact_deals)} deal(s) for {person_count} people."
            msg_ur = f"بہترین! مجھے {person_count} افراد کیلئے {len(exact_deals)} ڈیلز مل گئیں۔"
        else:
            msg_en = f"Great! I found {len(exact_deals)} deal(s) for you."
            msg_ur = f"بہترین! مجھے آپ کیلئے {len(exact_deals)} ڈیلز مل گئیں۔"
        return {
            "exists": True,
            "message": msg_ur,
            "message_en": msg_en,
            "deals": exact_deals[:10],
            "suggest_custom": False,
            "available_sizes": available_sizes,
            "custom_query": (
                f"create {cuisine_norm} deal for {person_count} people"
                if cuisine_norm and person_count > 0
                else ""
            ),
        }

    # No exact serving-size match, but same-cuisine deals exist.
    if person_count > 0 and all_deals:
        closest_distance = min(abs(int(d.get("serving_size") or 0) - person_count) for d in all_deals)
        closest_deals = [
            d for d in all_deals if abs(int(d.get("serving_size") or 0) - person_count) == closest_distance
        ]
        closest_sizes = sorted({int(d.get("serving_size") or 0) for d in closest_deals if int(d.get("serving_size") or 0) > 0})
        sizes_txt = ", ".join(str(s) for s in closest_sizes) if closest_sizes else "other sizes"

        msg_en = (
            f"I couldn't find an exact {person_count}-person deal"
            + (f" in {cuisine_norm}" if cuisine_norm else "")
            + f". Closest options serve {sizes_txt}. Would you like one of these or a custom deal?"
        )
        msg_ur = (
            f"مجھے {person_count} افراد کیلئے بالکل یہی ڈیل"
            + (f" {cuisine_norm} میں" if cuisine_norm else "")
            + f" نہیں ملی۔ قریب ترین آپشنز {sizes_txt} افراد کیلئے ہیں۔ کیا آپ یہ لیں گے یا کسٹم ڈیل بنوائیں گے؟"
        )

        return {
            "exists": False,
            "message": msg_ur,
            "message_en": msg_en,
            "deals": closest_deals[:10],
            "suggest_custom": True,
            "available_sizes": available_sizes,
            "custom_query": f"create {cuisine_norm} deal for {person_count} people" if cuisine_norm else f"create deal for {person_count} people",
        }

    if person_count > 0:
        msg_en = (
            f"I couldn't find an exact {person_count}-person deal"
            + (f" in {cuisine_norm}." if cuisine_norm else ".")
            + " Would you like a custom deal?"
        )
        msg_ur = (
            f"مجھے {person_count} افراد کیلئے بالکل یہی ڈیل"
            + (f" {cuisine_norm} میں" if cuisine_norm else "")
            + " نہیں ملی۔ کیا آپ کسٹم ڈیل بنوانا چاہیں گے؟"
        )
    else:
        msg_en = "I couldn't find a matching deal. Would you like a custom deal?"
        msg_ur = "مجھے کوئی میچنگ ڈیل نہیں ملی۔ کیا آپ کسٹم ڈیل بنوانا چاہیں گے؟"

    custom_query = f"create {cuisine_norm} deal for {person_count} people".strip()
    if not cuisine_norm and person_count > 0:
        custom_query = f"create deal for {person_count} people"
    elif cuisine_norm and person_count <= 0:
        custom_query = f"create {cuisine_norm} deal"
    elif not cuisine_norm and person_count <= 0:
        custom_query = "create custom deal"

    return {
        "exists": False,
        "message": msg_ur,
        "message_en": msg_en,
        "deals": [],
        "suggest_custom": True,
        "available_sizes": available_sizes,
        "custom_query": custom_query,
    }


@app.post("/voice_chat")
async def chat_voice_endpoint(
    session_id: str = Form(...),
    language: str = Form("ur"),
    conversation_history: str = Form("[]"),
    file: UploadFile = File(...)
):
    if not VOICE_ENABLED:
        return JSONResponse(
            status_code=503,
            content={"error": "Voice feature is temporarily disabled"}
        )
    os.makedirs("temp_voice", exist_ok=True)
    audio_path = f"temp_voice/{file.filename}"
    req_start = _time.time()

    try:
        with open(audio_path, "wb") as f:
            f.write(await file.read())
        file_size = os.path.getsize(audio_path)
        _voice_log(session_id, "upload", filename=file.filename, bytes=file_size, req_lang=language)

        # Reject clearly unusable recordings early instead of stalling the ASR pipeline.
        if file_size < 2048:
            return JSONResponse(
                status_code=400,
                content={"error": "Audio too short or invalid. Please hold mic longer and try again."},
            )

        # 1) Transcribe audio
        try:
            asr_start = _time.time()
            language_hint = (language or "ur").strip().lower()
            if language_hint not in {"ur", "en"}:
                language_hint = "ur"
            transcript = await asyncio.wait_for(
                run_in_threadpool(transcribe_audio, audio_path, language_hint),
                timeout=60,
            )
            _voice_log(session_id, "asr", asr_ms=int((_time.time() - asr_start) * 1000), transcript=transcript)
        except (asyncio.TimeoutError, TimeoutError):
            response_language = (language or "ur").strip().lower()
            if response_language not in {"ur", "en"}:
                response_language = "ur"
            reply_text = _voice_timeout_reply(response_language, "asr")
            _voice_log(session_id, "asr_timeout", timeout_s=60)
            return {
                "success": False,
                "transcript": "",
                "normalized_text": "",
                "reply": reply_text,
                "menu_items": [],
                "deals": [],
                "tool_calls": [],
                "nlp": {"intent": "general_chat", "keywords": {}},
                "memory_slots": (_SESSION_MEMORY.get(session_id, {}) or {}).get("slots", {}),
                "raw": {"error": "asr_timeout"},
            }
        except Exception:
            return JSONResponse(
                status_code=422,
                content={"error": "Could not process audio format. Please try again."},
            )

        normalized_lang = _detect_text_language(transcript, language)
        normalized_text = transcript if normalized_lang == "en" else translate_urdu_to_english(transcript)
        response_language = (language or "ur").strip().lower()
        if response_language not in {"ur", "en"}:
            response_language = normalized_lang
        nlp = _extract_keywords_intent(normalized_text)
        mem = _remember_context(session_id, nlp)
        _voice_log(
            session_id,
            "nlp",
            detected_lang=normalized_lang,
            normalized=normalized_text,
            intent=nlp["intent"],
            keywords=nlp["keywords"],
        )

        if _is_custom_deal_confirmation(normalized_text):
            slots = mem.get("slots", {}) if mem else {}
            if not slots.get("pending_custom_deal") and not (
                slots.get("cuisine") or slots.get("people")
            ):
                reply_text = _voice_timeout_reply(response_language, "llm")
                if response_language != "en":
                    reply_text = "کس چیز کے لیے ہاں کہہ رہے ہیں؟"
                else:
                    reply_text = "What would you like me to confirm?"
                return {
                    "success": True,
                    "transcript": transcript,
                    "normalized_text": normalized_text,
                    "reply": reply_text,
                    "menu_items": [],
                    "deals": [],
                    "tool_calls": [],
                    "nlp": nlp,
                    "memory_slots": slots,
                    "raw": "confirmation-without-context",
                }
            cuisine_txt = slots.get("cuisine", "")
            people_txt = slots.get("people", "")
            if cuisine_txt and people_txt:
                custom_query = f"create {cuisine_txt} deal for {people_txt} people"
            elif cuisine_txt:
                custom_query = f"create {cuisine_txt} deal"
            else:
                custom_query = normalized_text
            result = custom_deal_agent.create_deal(custom_query)
            slots["pending_custom_deal"] = False
            if mem is not None:
                mem["slots"] = slots
                _SESSION_MEMORY[session_id] = mem
            _voice_log(session_id, "custom_deal", query=custom_query, result_success=result.get("success"))
            return {
                "success": True,
                "transcript": transcript,
                "normalized_text": normalized_text,
                "reply": result.get("message", "Custom deal generated."),
                "menu_items": [],
                "deals": [result] if result.get("success") else [],
                "tool_calls": [],
                "nlp": nlp,
                "memory_slots": slots,
                "raw": result,
            }

        # 2) Parse optional conversation history from client
        try:
            history_raw = json.loads(conversation_history) if conversation_history else []
            history = _normalize_history_window(history_raw)
        except Exception:
            history = []

        # 3) Get AI tool-call response
        try:
            llm_start = _time.time()
            ai_response = await asyncio.wait_for(
                run_in_threadpool(
                    get_ai_response,
                    normalized_text,
                    history,
                    "",
                ),
                timeout=120,
            )
            _voice_log(
                session_id,
                "llm",
                llm_ms=int((_time.time() - llm_start) * 1000),
                tool_calls=getattr(ai_response, "tool_calls", []),
            )
        except (asyncio.TimeoutError, TimeoutError):
            _voice_log(session_id, "llm_timeout", timeout_s=120)
            ai_response = SimpleNamespace(content=_voice_timeout_reply(response_language, "llm"), tool_calls=[])
        except Exception:
            return JSONResponse(
                status_code=500,
                content={"error": "AI processing failed"},
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

        # Deterministic deal-first path: if user asked for deals, do DB deal search from parsed slots.
        if nlp["intent"] == "search_deal":
            deals = _search_deals_from_nlp(nlp, normalized_text)
            menu_items = []
            tool_calls = _build_deal_tool_calls(nlp)
            used_search_tool = True

        # Deterministic fallback: no deal found, continue conversation with memory.
        if not deals and nlp["intent"] == "search_deal":
            slots = mem.get("slots", {}) if mem else {}
            slots["pending_custom_deal"] = True
            if mem is not None:
                mem["slots"] = slots
                _SESSION_MEMORY[session_id] = mem
            reply_text = _deal_no_match_reply(
                slots.get("cuisine"),
                slots.get("people"),
                response_language,
            )
            _voice_log(session_id, "result", total_ms=int((_time.time() - req_start) * 1000), status="fallback-no-deal", deals_found=0)
            return {
                "success": True,
                "transcript": transcript,
                "normalized_text": normalized_text,
                "reply": reply_text,
                "menu_items": menu_items,
                "deals": deals,
                "tool_calls": tool_calls,
                "nlp": nlp,
                "memory_slots": slots,
                "raw": ai_response.content if hasattr(ai_response, "content") else str(ai_response),
            }

        # 4) Format reply text
        if used_search_tool:
            if response_language == "en":
                reply_text = format_results_response(menu_items, deals, language="en")
            else:
                reply_text = format_items_urdu(menu_items, deals)
        else:
            reply_text = ai_response.content if hasattr(ai_response, "content") else str(ai_response)

        _voice_log(
            session_id,
            "result",
            total_ms=int((_time.time() - req_start) * 1000),
            status="ok",
            deals_found=len(deals),
            menu_items_found=len(menu_items),
        )

        return {
            "success": True,
            "transcript": transcript,
            "normalized_text": normalized_text,
            "reply": reply_text,
            "menu_items": menu_items,
            "deals": deals,
            "tool_calls": tool_calls,
            "nlp": nlp,
            "memory_slots": mem.get("slots", {}) if mem else {},
            "raw": ai_response.content if hasattr(ai_response, "content") else str(ai_response),
        }
    finally:
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except Exception:
            pass


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
                       COALESCE(o.order_type, 'delivery') AS order_type,
                       o.round_number,
                       rt.table_number,
                       ds.session_id,
                       COALESCE(NULLIF(u.full_name,''), NULLIF(u.email,''), NULLIF(u.phone,''), 'Unknown') AS customer_name,
                       u.user_id AS customer_id
                FROM kitchen_tasks kt
                LEFT JOIN orders o ON o.order_id = kt.order_id
                LEFT JOIN cart c ON c.cart_id = o.cart_id
                LEFT JOIN auth.app_users u ON u.user_id = c.user_id
                LEFT JOIN public.dine_in_sessions ds ON ds.session_id = o.session_id
                LEFT JOIN public.restaurant_tables rt ON rt.table_id = COALESCE(o.table_id, ds.table_id)
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
                "order_type": row.get("order_type") or "delivery",
                "round_number": row.get("round_number"),
                "table_number": row.get("table_number"),
                "session_id": str(row["session_id"]) if row.get("session_id") else None,
                "customer_name": row["customer_name"],
                "customer_id": str(row["customer_id"]) if row["customer_id"] else "",
            }
        orders[oid]["tasks"].append(dict(row))
        if STATUS_RANK.get(row["status"], 2) < STATUS_RANK.get(orders[oid]["overall_status"], 2):
            orders[oid]["overall_status"] = row["status"]

    return {"orders": list(orders.values())}


@app.get("/kitchen/tables")
def kitchen_get_tables():
    """Return current table states with active session snapshot."""
    db = DatabaseConnection.get_instance()
    import psycopg2.extras
    with db.get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT rt.table_id, rt.table_number, rt.status,
                       ds.session_id, ds.started_at, ds.total_amount,
                       ds.round_count
                FROM public.restaurant_tables rt
                LEFT JOIN public.dine_in_sessions ds
                    ON rt.table_id = ds.table_id
                    AND ds.status NOT IN ('closed')
                ORDER BY rt.table_number
                """
            )
            rows = cur.fetchall()

    tables = []
    for row in rows:
        tables.append(
            {
                "table_id": str(row["table_id"]),
                "table_number": row["table_number"],
                "status": row["status"],
                "session_id": str(row["session_id"]) if row.get("session_id") else None,
                "started_at": row["started_at"].isoformat() if row.get("started_at") else None,
                "total_amount": float(row["total_amount"] or 0),
                "round_count": int(row["round_count"] or 0),
            }
        )
    return {"tables": tables}


@app.get("/kitchen/waiter-calls")
def kitchen_get_waiter_calls():
    """Return unresolved waiter calls oldest first."""
    db = DatabaseConnection.get_instance()
    import psycopg2.extras
    with db.get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT wc.call_id, wc.table_id, wc.called_at, wc.resolved,
                       rt.table_number
                FROM public.waiter_calls wc
                JOIN public.restaurant_tables rt ON wc.table_id = rt.table_id
                WHERE wc.resolved = false
                ORDER BY wc.called_at ASC
                """
            )
            rows = cur.fetchall()

    calls = []
    for row in rows:
        calls.append(
            {
                "call_id": str(row["call_id"]),
                "table_id": str(row["table_id"]),
                "table_number": row["table_number"],
                "called_at": row["called_at"].isoformat() if row.get("called_at") else None,
                "resolved": bool(row.get("resolved")),
            }
        )
    return {"calls": calls}


@app.post("/kitchen/sessions/{session_id}/confirm-cash")
def kitchen_confirm_cash_payment(session_id: str):
    """Mark dine-in session paid by cash and move table to cleaning."""
    db = DatabaseConnection.get_instance()
    import psycopg2.extras
    with db.get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE public.orders
                SET payment_status = 'paid'
                WHERE session_id = %s
                """,
                (session_id,),
            )
            cur.execute(
                """
                UPDATE public.dine_in_sessions
                SET status = 'closed', ended_at = NOW(),
                    payment_method = 'cash'
                WHERE session_id = %s
                RETURNING table_id
                """,
                (session_id,),
            )
            session_row = cur.fetchone()
            if not session_row:
                raise HTTPException(status_code=404, detail="Session not found")

            cur.execute(
                """
                UPDATE public.restaurant_tables
                SET status = 'available'
                WHERE table_id = %s
                """,
                (session_row["table_id"],),
            )
            cur.execute(
                """
                UPDATE public.waiter_calls
                SET resolved = true
                WHERE table_id = %s
                  AND resolved = false
                """,
                (session_row["table_id"],),
            )
        conn.commit()

    return {
        "success": True,
        "message": "Cash confirmed. Table is now available.",
        "session_id": session_id,
    }


@app.post("/kitchen/tables/{table_id}/mark-ready")
def kitchen_mark_table_ready(table_id: str):
    """Mark a cleaning table as available."""
    db = DatabaseConnection.get_instance()
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.restaurant_tables
                SET status = 'available'
                WHERE table_id = %s
                """,
                (table_id,),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Table not found")
        conn.commit()

    return {"success": True, "message": "Table is now available", "table_id": table_id}


@app.post("/kitchen/waiter-calls/{call_id}/resolve")
def kitchen_resolve_waiter_call(call_id: str):
    """Resolve an active waiter call."""
    db = DatabaseConnection.get_instance()
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.waiter_calls
                SET resolved = true
                WHERE call_id = %s
                """,
                (call_id,),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Waiter call not found")
        conn.commit()

    return {"success": True, "message": "Waiter call resolved", "call_id": call_id}


class KitchenStatusUpdate(BaseModel):
    new_status: str


@app.post("/kitchen/tasks/{task_id}/update-status")
def kitchen_update_task_status(task_id: str, body: KitchenStatusUpdate):
    """Publish update_status command to Redis, wait for response."""
    allowed = {"IN_PROGRESS", "READY", "COMPLETED"}
    if body.new_status not in allowed:
        raise HTTPException(status_code=400, detail=f"new_status must be one of {allowed}")

    def _direct_db_fallback(reason: str):
        row = None
        with SQL_ENGINE.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT task_id, order_id, status
                    FROM kitchen_tasks
                    WHERE task_id = :task_id
                    """
                ),
                {"task_id": task_id},
            ).mappings().fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Kitchen task not found")

        current_status = (row["status"] or "").upper()
        allowed_flow = {
            "QUEUED": {"IN_PROGRESS"},
            "IN_PROGRESS": {"READY"},
            "READY": {"COMPLETED"},
            "COMPLETED": set(),
        }

        if current_status not in allowed_flow:
            raise HTTPException(status_code=400, detail=f"Unsupported current task status: {current_status}")

        if body.new_status != current_status and body.new_status not in allowed_flow[current_status]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status transition: {current_status} -> {body.new_status}",
            )

        from kitchen.kitchen_agent import update_task_status as _direct_update_task_status
        from kitchen.kitchen_agent import compute_and_sync_order_status as _direct_sync_order_status

        updated = _direct_update_task_status(task_id, body.new_status)
        if not updated:
            raise HTTPException(status_code=404, detail="Kitchen task not found")

        _direct_sync_order_status(row["order_id"])

        return {
            "success": True,
            "task_id": task_id,
            "new_status": body.new_status,
            "mode": "direct-db-fallback",
            "message": reason,
        }

    response_channel = f"resp_{uuid.uuid4().hex}"
    message = {
        "agent": "kitchen",
        "command": "update_status",
        "payload": {"task_id": task_id, "new_status": body.new_status},
        "response_channel": response_channel,
    }

    pubsub = None
    try:
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

        if result is None:
            return _direct_db_fallback(
                "Kitchen agent timeout. Updated task directly in database."
            )
        return result

    except redis_lib.exceptions.ConnectionError:
        # Redis is optional for local testing: fall back to direct DB update.
        return _direct_db_fallback("Redis offline. Updated task directly in database.")
    finally:
        if pubsub is not None:
            try:
                pubsub.unsubscribe(response_channel)
            except Exception:
                pass
            try:
                pubsub.close()
            except Exception:
                pass


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
