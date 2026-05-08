# main.py

import os
import uuid
import json
import time as _time
import asyncio
from difflib import SequenceMatcher
from types import SimpleNamespace
import redis as redis_lib
from auth.auth_routes import router as auth_router
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, Any, Tuple

# Voice transcription is optional - will be added later
try:
    from voice.transcribe import transcribe_audio, warmup_transcriber
    VOICE_ENABLED = True
except Exception as e:
    print(f"[WARNING] Voice transcription disabled: {e}")
    transcribe_audio = None
    warmup_transcriber = None
    VOICE_ENABLED = False

try:
    from voice.text_to_speech import generate_tts
    TTS_ENABLED = True
except Exception as e:
    print(f"[WARNING] Voice TTS disabled: {e}")
    generate_tts = None
    TTS_ENABLED = False

try:
    from voice.intent_pipeline import plan_restaurant_tool_calls
except Exception:
    def plan_restaurant_tool_calls(calls):
        return list(calls or [])

try:
    from chat.chat_agent import get_ai_response, llm as ITEM_NAME_LLM
    from langchain_core.messages import HumanMessage
except Exception:
    from chat.chat_agent import get_ai_response
    ITEM_NAME_LLM = None
    HumanMessage = None
from voice.urdu_translator import (
    translate_urdu_to_english,
    detect_custom_deal_intent,
    detect_info_intent,
    _extract_deal_items,
    _build_deal_query,
)
from voice.cart_voice_heuristics import (
    wants_clear_entire_cart as _wants_clear_entire_cart,
    text_requests_order_tracking as _text_requests_order_tracking,
)
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

_redis_url = os.getenv("REDIS_URL")
if _redis_url:
    _REDIS_CLIENT = redis_lib.StrictRedis.from_url(_redis_url, decode_responses=True)
else:
    _REDIS_CLIENT = redis_lib.StrictRedis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT") or 6379),
        db=0,
        decode_responses=True,
    )

upsell_agent = UpsellAgent()
recommendation_engine = RecommendationEngine()
custom_deal_agent = CustomDealAgent()

print("DB URL = ", os.getenv("DATABASE_URL"))
logger = logging.getLogger("voice_nlp")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Voice flow should stay deterministic unless explicitly enabled.
VOICE_LLM_ENABLED = (
    os.getenv("VOICE_LLM_ENABLED", "0").strip().lower()
    in {"1", "true", "yes", "on"}
)

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

    # People count — must be tied to *people* semantics. The old regex
    # matched any digit 1–9 even when it was a food quantity ("2 naans"),
    # and the word loop matched "two" inside "2 naans" → wrong slots for
    # deals / routing. Only accept:
    #   • "3 people", "for 4 persons", "2 bandon", "do log", etc.
    #   • NOT bare digits or number-words that are clearly item quantities.
    people = None
    m = re.search(
        r"\b(?:for\s+)?(\d{1,2})\s+"
        r"(people|persons|person|bandon|bando|logon|logo|afrad|afraad)\b",
        t,
    )
    if m:
        people = int(m.group(1))
    if people is None:
        m2 = re.search(
            r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s+"
            r"(people|persons|person|bandon|logon|afrad)\b",
            t,
        )
        if m2:
            people = _PEOPLE_WORD_MAP.get(m2.group(1))
    if people is None:
        m3 = re.search(
            r"\b(ek|do|teen|chaar|paanch|chha|saat|aath|nau|das)\s+"
            r"(log|logon|bandon|afraad|afrad)\b",
            t,
        )
        if m3:
            people = _PEOPLE_WORD_MAP.get(m3.group(1))

    mentions_deal = any(k in t for k in ["deal", "deals"])
    mentions_menu = any(k in t for k in ["menu", "item", "dish"])

    if mentions_deal:
        intent = "search_deal"
    elif mentions_menu:
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
        # Signals for multi-topic utterances (e.g. "show deals and menu for fast food").
        # Primary [intent] still picks one branch for routing; orchestration uses these
        # to merge DB results when both topics appear in the same sentence.
        "signals": {
            "mentions_deal": mentions_deal,
            "mentions_menu": mentions_menu,
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

_CUISINE_NORMALIZE = {
    "fast_food": "fast food",
    "fastfood": "fast food",
    "pakistani": "desi",
    "barbeque": "bbq",
    "barbecue": "bbq",
}


def _normalize_cuisine_token(value: Any) -> str:
    s = str(value or "").strip().lower()
    return _CUISINE_NORMALIZE.get(s, s)


def _classify_voice_intent_llm(
    raw_transcript: str,
    normalized_text: str,
    keyword_intent: str,
    slots: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Robust fallback classifier for ambiguous voice utterances.

    Only invoked when the deterministic keyword path is uncertain about whether
    the user wants to CREATE a custom deal or BROWSE existing deals. Returns
    a dict {"intent": "create_custom_deal"|"search_existing_deal"|"other",
    "cuisine": str, "people": int|None} or None on any failure.

    Kept fast (single short LLM call, low temperature, JSON-only output).
    """
    if ITEM_NAME_LLM is None or HumanMessage is None:
        return None

    raw = (raw_transcript or "").strip()
    norm = (normalized_text or "").strip()
    if not raw and not norm:
        return None

    cuisine_hint = _normalize_cuisine_token(slots.get("cuisine"))
    people_hint = slots.get("people")

    prompt = (
        "You classify a single restaurant voice command into ONE intent.\n"
        "The user is in a Pakistani restaurant kiosk and speaks Urdu, Roman Urdu,\n"
        "or English. Their words may have been mistranscribed by ASR.\n\n"
        "Possible intents:\n"
        "  - create_custom_deal: user wants the AI to BUILD a NEW deal for them\n"
        "    (e.g. 'deal bana do', 'make me a deal for 4 people', 'custom deal',\n"
        "     'create a chinese deal for 2', 'مجھے 3 بندوں کیلئے ڈیل بناؤ').\n"
        "  - search_existing_deal: user wants to BROWSE existing menu deals\n"
        "    (e.g. 'show me deals', 'kya deals hain', 'what deals do you have',\n"
        "     'deal dikhao', 'list deals').\n"
        "  - other: anything else (menu search, add to cart, navigation, etc.).\n\n"
        f"Raw transcript: {raw!r}\n"
        f"Normalized: {norm!r}\n"
        f"Slot hints: cuisine={cuisine_hint or 'unknown'}, "
        f"people={people_hint if people_hint else 'unknown'}\n\n"
        "Respond with STRICT JSON only, no prose:\n"
        "{\"intent\": \"create_custom_deal\"|\"search_existing_deal\"|\"other\","
        " \"cuisine\": \"chinese\"|\"desi\"|\"bbq\"|\"fast food\"|\"\","
        " \"people\": <integer or null>}"
    )

    try:
        resp = ITEM_NAME_LLM.invoke([HumanMessage(content=prompt)])
        raw_out = str(getattr(resp, "content", "") or "").strip()
        m = re.search(r"\{.*\}", raw_out, flags=re.DOTALL)
        if not m:
            return None
        parsed = json.loads(m.group(0))
        intent = str(parsed.get("intent") or "").strip().lower()
        if intent not in {"create_custom_deal", "search_existing_deal", "other"}:
            return None
        cuisine = _normalize_cuisine_token(parsed.get("cuisine") or "")
        people_raw = parsed.get("people")
        people = None
        if isinstance(people_raw, int) and people_raw > 0:
            people = people_raw
        elif isinstance(people_raw, str) and people_raw.strip().isdigit():
            people = int(people_raw.strip())
        return {"intent": intent, "cuisine": cuisine, "people": people}
    except Exception as e:
        logger.info(f"[VOICE][llm_classifier_error] {e}")
        return None


def _route_custom_deal(
    raw_transcript: str,
    normalized_text: str,
    nlp: Dict[str, Any],
    slots: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Decide whether this utterance should trigger the custom-deal flow.

    Pipeline:
      1. Fast deterministic check on the RAW transcript (catches Urdu-script
         patterns like 'ڈیل بنا دو' before any normalization loss).
      2. Same check on the NORMALIZED English text (catches Whisper-translated
         phrases like 'create deal for 2 people').
      3. LLM tiebreaker for ambiguous cases — only when the keyword pass said
         "search_deal" but the utterance also contains a create-verb signal,
         OR when slots include a person count + cuisine without a clear "show"
         word. This keeps the fast path fast.

    Returns {"query": str, "cuisine": str, "people": int|None, "source": str}
    if custom deal should fire; otherwise None.
    """
    # Stage 1 + 2 — keyword detector on both texts.
    for label, candidate in (("raw", raw_transcript), ("normalized", normalized_text)):
        hit = detect_custom_deal_intent(candidate)
        if hit and hit.get("is_custom_deal"):
            people_val = None
            if hit.get("people"):
                try:
                    people_val = int(str(hit["people"]).strip())
                except Exception:
                    people_val = None

            # Resolve effective cuisine/people (utterance > explicit keyword NLP
            # > session slots). This matters because the agent's LLM parser
            # needs the cuisine WORD to appear inside `user_query` — otherwise
            # it asks for clarification even when we already know the cuisine.
            nlp_cuisine = _normalize_cuisine_token(
                (nlp or {}).get("keywords", {}).get("cuisine")
            )
            slot_cuisine = _normalize_cuisine_token(slots.get("cuisine"))
            effective_cuisine = (
                _normalize_cuisine_token(hit.get("cuisine"))
                or nlp_cuisine
                or slot_cuisine
                or None
            )
            nlp_people = (nlp or {}).get("keywords", {}).get("people")
            effective_people = people_val or nlp_people or slots.get("people")

            # Collect any explicit dish tokens the user named (karahi, biryani,
            # zinger, etc.) from BOTH the raw and normalized transcript. These
            # must survive into the query string so the deal agent's rule
            # parser picks them up as `explicit_items`. Without this the naive
            # rewrite "create deal for 3 people" throws the dish name away
            # and the agent has no way to honour the user's ask.
            explicit_items: List[str] = []
            seen_items: set = set()
            for src in (hit.get("items") or []):
                token = str(src).strip().lower()
                if token and token not in seen_items:
                    seen_items.add(token)
                    explicit_items.append(token)
            for src_text in (raw_transcript, normalized_text):
                for token in _extract_deal_items(src_text or ""):
                    if token and token not in seen_items:
                        seen_items.add(token)
                        explicit_items.append(token)

            # Rebuild the query in canonical form so `create_deal` always sees
            # an explicit cuisine word when we have one AND any dishes the
            # user named. Fall back to the detector's original query string
            # when we truly know neither.
            if effective_cuisine or effective_people or explicit_items:
                rebuilt_query = _build_deal_query(
                    effective_cuisine or "",
                    str(effective_people) if effective_people else "",
                    explicit_items,
                )
            else:
                rebuilt_query = hit["query"]

            return {
                "query": re.sub(r"\s+", " ", rebuilt_query).strip(),
                "cuisine": effective_cuisine,
                "people": effective_people,
                "items": explicit_items,
                "source": f"keyword:{label}",
            }

    # Stage 3 — LLM tiebreaker. Only invoke when there's enough signal to be
    # worth the latency: the utterance involves "deal" + (a create verb OR
    # a person count). This is exactly the bucket the keyword path misses
    # because Whisper dropped the word "custom".
    combined = f"{(raw_transcript or '').lower()} || {(normalized_text or '').lower()}"
    has_deal_word = bool(re.search(r"\b(deal|deals|ڈیل|ڈیلز)\b", combined))
    has_create_verb = bool(
        re.search(
            r"\b(create|make|build|prepare|generate|want|need|give|"
            r"bana|banao|bana\s*do|banado|bnado|tayyar|tayar|"
            r"بنا|بنوا|تیار)\b",
            combined,
        )
    )
    has_person_count = bool(slots.get("people")) or bool(
        re.search(
            r"\b(\d+\s*(people|person|persons|log|logon|bando|bandon|afrad|افراد|بندوں|لوگوں))\b",
            combined,
        )
    )

    if not has_deal_word:
        return None
    if not (has_create_verb or has_person_count):
        return None

    classifier = _classify_voice_intent_llm(
        raw_transcript=raw_transcript,
        normalized_text=normalized_text,
        keyword_intent=str(nlp.get("intent") or ""),
        slots=slots,
    )
    if not classifier:
        return None
    if classifier.get("intent") != "create_custom_deal":
        return None

    cuisine = _normalize_cuisine_token(classifier.get("cuisine") or slots.get("cuisine"))
    people = classifier.get("people") or slots.get("people")

    # Also preserve any item words the user spoke so the agent parser can
    # treat them as explicit items. Same rationale as the keyword branch.
    explicit_items: List[str] = []
    seen_items: set = set()
    for src_text in (raw_transcript, normalized_text):
        for token in _extract_deal_items(src_text or ""):
            if token and token not in seen_items:
                seen_items.add(token)
                explicit_items.append(token)

    if cuisine or people or explicit_items:
        query = _build_deal_query(
            cuisine or "",
            str(people) if people else "",
            explicit_items,
        )
    else:
        query = (normalized_text or raw_transcript or "create custom deal").strip()

    return {
        "query": re.sub(r"\s+", " ", query).strip(),
        "cuisine": cuisine,
        "people": people,
        "items": explicit_items,
        "source": "llm",
    }


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
    query = (kws.get("cuisine") or "").strip()
    normalized = (normalized_text or "").strip().lower()

    if query:
        deals = fetch_deals_by_name(query)
    elif any(k in normalized for k in ["show deals", "all deals", "deals", "deal"]):
        deals = fetch_deals_for_voice("")
    else:
        deals = fetch_deals_by_name(normalized_text)

    return _filter_deals_by_people(deals, kws.get("people"))

def _build_deal_tool_calls(nlp: Dict[str, Any]) -> List[Dict[str, Any]]:
    kws = (nlp or {}).get("keywords", {})
    args: Dict[str, str] = {}
    if kws.get("cuisine"):
        args["cuisine"] = str(kws["cuisine"])
    if kws.get("people"):
        args["person_count"] = str(kws["people"])
    return [{"name": "search_deal", "args": args}]


def _want_menu_and_deals_together(nlp: Dict[str, Any]) -> bool:
    """True when the user mixed menu + deal language in one utterance (real-life composite queries)."""
    sig = (nlp or {}).get("signals") or {}
    return bool(sig.get("mentions_deal") and sig.get("mentions_menu"))


def _dedupe_menu_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        iid = r.get("item_id")
        if iid in seen:
            continue
        seen.add(iid)
        out.append(r)
    return out


def _dedupe_deal_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        did = r.get("deal_id")
        if did in seen:
            continue
        seen.add(did)
        out.append(r)
    return out


def _combined_search_query(nlp: Dict[str, Any], normalized_text: str) -> str:
    kws = (nlp or {}).get("keywords") or {}
    c = (kws.get("cuisine") or "").strip()
    if c:
        return c
    return (normalized_text or "").strip()


def _merge_menu_and_deal_results(
    nlp: Dict[str, Any],
    normalized_text: str,
    menu_items: List[Dict[str, Any]],
    deals: List[Dict[str, Any]],
    tool_calls: List[Dict[str, Any]],
) -> tuple:
    """If the utterance referenced both deals and the menu, run the second search and merge."""
    if not _want_menu_and_deals_together(nlp):
        return menu_items, deals, tool_calls

    q = _combined_search_query(nlp, normalized_text)
    if not q:
        return menu_items, deals, tool_calls

    intent = (nlp or {}).get("intent") or ""
    tools = list(tool_calls or [])

    if intent == "search_deal" and q:
        extra = fetch_menu_items_by_name(q)
        menu_items = _dedupe_menu_rows((menu_items or []) + extra)
        if not any((c or {}).get("name") == "search_menu" for c in tools):
            tools.append({"name": "search_menu", "args": {"query": str(q)}})
    elif intent == "search_menu" and q:
        extra_deals = _search_deals_from_nlp(nlp, normalized_text)
        deals = _dedupe_deal_rows((deals or []) + extra_deals)
        if not any((c or {}).get("name") == "search_deal" for c in tools):
            tools.extend(_build_deal_tool_calls(nlp))

    return menu_items, deals, tools


def _clean_item_name(raw: str) -> str:
    name = re.sub(r"\b(to|into|in|my|the|a|an|cart|please)\b", " ", raw, flags=re.IGNORECASE)
    # ASR junk tails — "add cola in the cart" / "kula in the bowl" leave
    # trailing phrases that wreck fuzzy matching (e.g. "kula in the bowl"
    # → random menu item).
    name = re.sub(
        r"\b(in the (cart|bowl|order)|to (the )?cart|please)\b.*$",
        " ",
        name,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"\s+", " ", name).strip(" .,!?")
    if name.endswith(" burgers"):
        name = name[:-1]
    return name.title()


_MENU_NAME_CACHE: Dict[str, Any] = {"names": [], "expires_at": 0.0}


def _similarity(a: str, b: str) -> float:
    aa = (a or "").strip().lower()
    bb = (b or "").strip().lower()
    if not aa or not bb:
        return 0.0
    return SequenceMatcher(None, aa, bb).ratio()


def _get_cached_menu_item_names(ttl_seconds: int = 300) -> List[str]:
    now = _time.time()
    names = _MENU_NAME_CACHE.get("names") or []
    expires = float(_MENU_NAME_CACHE.get("expires_at") or 0.0)
    if names and now < expires:
        return names

    query = text("""
        SELECT item_name
        FROM menu_item
        WHERE item_name IS NOT NULL
        ORDER BY item_id
    """)
    with SQL_ENGINE.connect() as conn:
        rows = conn.execute(query).mappings().all()

    fresh_names = [str(r.get("item_name") or "").strip() for r in rows]
    fresh_names = [n for n in fresh_names if n]

    _MENU_NAME_CACHE["names"] = fresh_names
    _MENU_NAME_CACHE["expires_at"] = now + ttl_seconds
    return fresh_names


def _llm_resolve_menu_item_name(spoken_name: str, candidates: List[str]) -> Optional[str]:
    if not ITEM_NAME_LLM or HumanMessage is None:
        return None
    if not candidates:
        return None

    prompt = (
        "You normalize ASR-spoken menu names to an exact restaurant menu item. "
        "Choose ONE name only from the provided candidates. "
        "If uncertain, return null.\n\n"
        f"Spoken item: {spoken_name}\n\n"
        "Candidates:\n- " + "\n- ".join(candidates) + "\n\n"
        "Return strict JSON only: {\"item_name\": \"<exact candidate>\"} or {\"item_name\": null}"
    )

    try:
        response = ITEM_NAME_LLM.invoke([HumanMessage(content=prompt)])
        raw = str(getattr(response, "content", "") or "").strip()
        m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not m:
            return None

        parsed = json.loads(m.group(0))
        chosen = str(parsed.get("item_name") or "").strip()
        if not chosen:
            return None

        candidate_set = {c.lower(): c for c in candidates}
        return candidate_set.get(chosen.lower())
    except Exception:
        return None


def _canonicalize_menu_item_name(raw_name: str, *, voice_strict: bool = False) -> str:
    """Map spoken / ASR text to a DB menu `item_name`.

    When ``voice_strict`` is True (voice add-to-cart path), thresholds are
    higher and we refuse to snap a vague token like ``Chicken`` to the first
    fuzzy hit — that behaviour caused "add chicken" → Chicken Handi and
    nonsense tails like "kula" → Beef Boti when Whisper hallucinated English.
    """
    cleaned = _clean_item_name(raw_name)
    if not cleaned:
        return ""

    min_sql = 0.72 if voice_strict else 0.58
    min_global = 0.82 if voice_strict else 0.72

    cleaned_tokens = cleaned.lower().split()
    is_single_word = len(cleaned_tokens) == 1

    # First pass: SQL ILIKE candidates, then fuzzy rank.
    sql_candidates = fetch_menu_items_by_name(cleaned)
    sql_names = [str(r.get("item_name") or "").strip() for r in sql_candidates]
    sql_names = [n for n in sql_names if n]

    if sql_names:
        ranked = sorted(sql_names, key=lambda n: _similarity(cleaned, n), reverse=True)
        best = ranked[0]
        sim = _similarity(cleaned, best)

        # Voice: a one-word token that matches many rows (e.g. "Chicken")
        # is almost always ambiguous — never auto-pick unless similarity is
        # very high (exact-ish name) or the name equals the token.
        if voice_strict and is_single_word and len(sql_names) >= 5:
            if sim < 0.88 and best.lower() != cleaned.lower():
                # Prefer exact title-case match; else refuse to guess.
                exact = [n for n in sql_names if n.lower() == cleaned.lower()]
                if exact:
                    return exact[0]
                return ""

        if sim >= min_sql:
            return best

    # Second pass: global menu fuzzy candidate shortlist.
    all_names = _get_cached_menu_item_names()
    if not all_names:
        return "" if voice_strict else cleaned

    ranked_global = sorted(all_names, key=lambda n: _similarity(cleaned, n), reverse=True)
    shortlist = ranked_global[:30]
    if shortlist and _similarity(cleaned, shortlist[0]) >= min_global:
        if voice_strict and is_single_word and len(shortlist) > 1:
            top = _similarity(cleaned, shortlist[0])
            second = _similarity(cleaned, shortlist[1])
            if top < 0.9 and (top - second) < 0.06:
                return ""
        return shortlist[0]

    # LLM disambiguation (full menu) when fuzzy match fails.
    # Passed all_names because an Urdu transliteration (e.g. "چاومین") will have
    # 0.0 fuzzy similarity with "Chowmein" and might not make the top-30 shortlist.
    llm_match = _llm_resolve_menu_item_name(cleaned, all_names)
    if llm_match:
        return llm_match

    return "" if voice_strict else cleaned


_DEAL_NAME_CACHE: Dict[str, Any] = {"names": [], "expires_at": 0.0}


def _get_cached_deal_names(ttl_seconds: int = 300) -> List[str]:
    """All distinct catalog deal names — used for global fuzzy matching."""
    now = _time.time()
    names = _DEAL_NAME_CACHE.get("names") or []
    expires = float(_DEAL_NAME_CACHE.get("expires_at") or 0.0)
    if names and now < expires:
        return names

    query = text("""
        SELECT d.deal_name
        FROM deal d
        WHERE d.deal_name IS NOT NULL AND TRIM(d.deal_name) <> ''
        GROUP BY d.deal_name
        ORDER BY MIN(d.deal_id)
    """)
    with SQL_ENGINE.connect() as conn:
        rows = conn.execute(query).mappings().all()

    fresh = [str(r.get("deal_name") or "").strip() for r in rows]
    fresh = [n for n in fresh if n]
    _DEAL_NAME_CACHE["names"] = fresh
    _DEAL_NAME_CACHE["expires_at"] = now + ttl_seconds
    return fresh


def _canonicalize_deal_name(raw_name: str, *, voice_strict: bool = False) -> str:
    """Map spoken text to an exact row in ``deal.deal_name`` (catalog deals).

    Flutter's ``_addTo_cart`` resolves **either** menu items or deals by
    name against ``/menu`` and ``/deals``. The voice pipeline used to call
    :func:`_canonicalize_menu_item_name` only, so phrases like *add the
    family deal* never matched a ``menu_item`` row and the client showed
    *item not found*.
    """
    cleaned = _clean_item_name(raw_name)
    if not cleaned:
        return ""

    min_sql = 0.72 if voice_strict else 0.58
    min_global = 0.82 if voice_strict else 0.72
    cleaned_tokens = cleaned.lower().split()
    is_single_word = len(cleaned_tokens) == 1

    sql_rows = fetch_deals_by_name(cleaned)
    sql_names = []
    seen: set = set()
    for r in sql_rows:
        n = str(r.get("deal_name") or "").strip()
        if n and n.lower() not in seen:
            seen.add(n.lower())
            sql_names.append(n)

    if sql_names:
        ranked = sorted(sql_names, key=lambda n: _similarity(cleaned, n), reverse=True)
        best = ranked[0]
        sim = _similarity(cleaned, best)

        if voice_strict and is_single_word and len(sql_names) >= 4:
            if sim < 0.88 and best.lower() != cleaned.lower():
                exact = [n for n in sql_names if n.lower() == cleaned.lower()]
                if exact:
                    return exact[0]
                return ""

        if sim >= min_sql:
            return best

    all_deal_names = _get_cached_deal_names()
    if not all_deal_names:
        return "" if voice_strict else cleaned

    ranked_global = sorted(
        all_deal_names, key=lambda n: _similarity(cleaned, n), reverse=True
    )
    shortlist = ranked_global[:30]
    if shortlist and _similarity(cleaned, shortlist[0]) >= min_global:
        if voice_strict and is_single_word and len(shortlist) > 1:
            top = _similarity(cleaned, shortlist[0])
            second = _similarity(cleaned, shortlist[1])
            if top < 0.9 and (top - second) < 0.06:
                return ""
        return shortlist[0]

    # LLM disambiguation (full deal catalog) when fuzzy match fails.
    llm_match = _llm_resolve_menu_item_name(cleaned, all_deal_names)
    if llm_match:
        return llm_match

    return "" if voice_strict else cleaned


def _resolve_cart_item_name(raw_name: str, *, voice_strict: bool = False) -> str:
    """Resolve to a ``menu_item.item_name`` OR ``deal.deal_name`` string.

    The app adds catalog deals with ``item_type=deal`` using the exact
    ``deal_name`` from ``/deals``. Prefer deal resolution when the utterance
    clearly refers to a bundle (contains *deal*), otherwise prefer menu
    items and fall back to deals (e.g. *add zinger combo* with no word
    *deal* may still be a deal row only).
    """
    cleaned = _clean_item_name(raw_name)
    if not cleaned:
        return ""

    t = cleaned.lower()
    raw_l = (raw_name or "").lower()
    prefer_deal = (
        "deal" in t
        or "deal" in raw_l
        or "ڈیل" in (raw_name or "")
        or "combo" in t
        or "bundle" in t
        or "meal" in t
    )

    def menu() -> str:
        return _canonicalize_menu_item_name(raw_name, voice_strict=voice_strict)

    def deal() -> str:
        return _canonicalize_deal_name(raw_name, voice_strict=voice_strict)

    if prefer_deal:
        d = deal()
        if d:
            return d
        m = menu()
        return m

    m = menu()
    if m:
        return m
    d = deal()
    return d


_QTY_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    # Roman Urdu number words used in kiosk utterances.
    "ek": 1,
    "do": 2,
    "teen": 3,
    "char": 4,
    "chaar": 4,
    "panch": 5,
    "paanch": 5,
    "che": 6,
    "chay": 6,
    "saat": 7,
    "aath": 8,
    "ath": 8,
    "nau": 9,
    "das": 10,
}


def _split_add_item_chunks(raw: str) -> List[str]:
    text_value = (raw or "").strip().lower()
    if not text_value:
        return []

    # Protect common names that naturally contain "and".
    protected = {
        "fish and chips": "fish __and__ chips",
        "mac and cheese": "mac __and__ cheese",
        "sweet and sour": "sweet __and__ sour",
    }
    for src, dst in protected.items():
        text_value = text_value.replace(src, dst)

    text_value = text_value.replace(" & ", " and ").replace(" plus ", " and ")
    # Roman Urdu connector in multi-item add utterances ("ek X aur do Y").
    text_value = re.sub(r"\s+aur\s+", " and ", text_value, flags=re.IGNORECASE)
    text_value = re.sub(r"\s*[,،]\s*", " and ", text_value)

    chunks = [
        c.strip().replace("__and__", " and ")
        for c in re.split(r"\s+and\s+", text_value)
        if c and c.strip()
    ]
    return chunks


def _parse_qty_token(token: str) -> Optional[int]:
    t = (token or "").strip().lower()
    if not t:
        return None
    if t.isdigit():
        try:
            return int(t)
        except Exception:
            return None
    return _QTY_WORDS.get(t)


# ─────────────────────────────────────────────────────────────────────────────
# URDU TRANSCRIPT  →  DIRECT CART EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────
# ElevenLabs returns correct Urdu (e.g. "دیسی ڈیو کارٹ میں ڈال دو") but the
# static translate_urdu_to_english() often mangles item names into gibberish
# ("Add desi dev cut in the order.").  This layer intercepts the raw Urdu
# transcript BEFORE translation so item names survive intact.

_URDU_ITEM_WORD_MAP: Dict[str, str] = {
    # Cuisine
    "دیسی": "desi", "چائنیز": "chinese", "چاینیز": "chinese",
    "چائینیز": "chinese",
    "بی بی کیو": "bbq",
    # Proteins
    "چکن": "chicken", "مٹن": "mutton", "بیف": "beef", "فش": "fish",
    "پراون": "prawn", "انڈہ": "egg",
    # Dishes — multiple common spellings for each
    "کڑاہی": "karahi", "کڑاھی": "karahi",
    "کڑھائی": "karahi", "کڑہائی": "karahi",   # ← additional spellings
    "کڑھی": "karahi", "قرمہ": "korma",
    "بریانی": "biryani", "برئانی": "biryani",
    "حلیم": "haleem", "نہاری": "nihari", "پلاؤ": "pulao",
    "قورمہ": "korma", "ہنڈی": "handi", "دال": "daal",
    "تکہ": "tikka", "تکا": "tikka", "بوٹی": "boti",
    "سیخ": "seekh", "کباب": "kabab",
    # Breads
    "نان": "naan", "روٹی": "roti", "پراٹھا": "paratha", "کلچہ": "kulcha",
    # Fast food
    "برگر": "burger", "زنگر": "zinger", "پیزا": "pizza",
    "فرائز": "fries", "نگٹس": "nuggets", "رول": "roll",
    "سینڈوچ": "sandwich", "کلب": "club", "ریپ": "wrap",
    # Drinks
    "ڈیو": "dew", "کولا": "cola", "پیپسی": "pepsi",
    "اسپرائٹ": "sprite", "سپرائٹ": "sprite",
    "جوس": "juice", "لسی": "lassi", "چائے": "chai",
    "شیک": "shake", "پانی": "water", "سوپ": "soup", "کافی": "coffee",
    # Qualifiers / deal words
    "فیملی": "family", "سولو": "solo", "ڈیل": "deal",
    "اسپیشل": "special", "ڈبل": "double", "سنگل": "single",
    "میگا": "mega", "باکس": "box", "کومبو": "combo",
    "پارٹی": "party", "ٹاور": "tower", "مکس": "mix",
    # Numbers
    "ایک": "1", "دو": "2", "تین": "3", "چار": "4", "پانچ": "5",
}

_URDU_ADD_PATTERNS: List[str] = [
    # X کارٹ/کاٹ میں ڈال/شامل دو/دیں
    r"^(.+?)\s+(?:کارٹ|کاٹ|کارڈ)\s+میں\s+(?:ڈال|شامل|add|ایڈ)\s*(?:دو|دیں|دیجیے|کریں|کرو|کر\s*دو)?\s*$",
    # Mixed Latin "cart" + Urdu postposition + add (Whisper often does this)
    r"^(.+?)\s+cart\s+میں\s+(?:add|ایڈ)\s*(?:کر\s*دو|کرو|کریں)?\s*$",
    # X ڈال دو / شامل کرو
    r"^(.+?)\s+(?:ڈال\s*دو|ڈال\s*دیں|شامل\s*کرو|شامل\s*کریں|شامل\s*کر\s*دو)\s*$",
    # X add karo/kar do/krdo
    r"^(.+?)\s+(?:add|ایڈ)\s+(?:karo|kar\s*do|krdo|kardo|karein)\s*$",
    # X میں ڈال (short)
    r"^(.+?)\s+میں\s+(?:ڈال|شامل)\s*(?:دو|دیں|کریں)?\s*$",
]

_URDU_QTY_WORDS: Dict[str, int] = {
    "ایک": 1, "دو": 2, "تین": 3, "چار": 4, "پانچ": 5,
    "چھ": 6, "سات": 7, "آٹھ": 8, "نو": 9, "دس": 10,
}


def _translate_urdu_item_phrase(phrase: str) -> str:
    """Word-by-word Urdu → English using the restaurant word map."""
    phrase = (phrase or "").strip()
    if not phrase:
        return ""
    words = phrase.split()
    result: List[str] = []
    i = 0
    while i < len(words):
        if i + 1 < len(words):
            two = words[i] + " " + words[i + 1]
            if two in _URDU_ITEM_WORD_MAP:
                result.append(_URDU_ITEM_WORD_MAP[two])
                i += 2
                continue
        mapped = _URDU_ITEM_WORD_MAP.get(words[i])
        result.append(mapped if mapped else words[i])
        i += 1
    return " ".join(result).strip()


def _extract_urdu_add_to_cart(
    raw_transcript: str,
    *,
    voice_strict: bool = True,
) -> List[Dict[str, Any]]:
    """Detect add-to-cart commands from raw Urdu before translation corrupts them.

    Supports MULTI-ITEM utterances separated by Urdu comma (،), regular
    comma, or اور / and.  Example:
        "تین کولا، ایک چکن کلب سینڈوچ اور دو زنگر برگر کارٹ میں ڈال دو"
        → 3× Cola, 1× Chicken Club Sandwich, 2× Zinger Burger

    Returns resolved add_to_cart tool-call dicts or [] on no match.
    """
    t = (raw_transcript or "").strip()
    if not t:
        return []

    item_phrase_ur: Optional[str] = None
    for pat in _URDU_ADD_PATTERNS:
        m = re.match(pat, t, flags=re.IGNORECASE)
        if m:
            item_phrase_ur = m.group(1).strip()
            break
    if not item_phrase_ur:
        return []

    # Do not split "sweet and sour" / "fish and chips" on the inner " and ".
    _and_shields = (
        ("sweet and sour", "sweet __and__ sour"),
        ("fish and chips", "fish __and__ chips"),
        ("mac and cheese", "mac __and__ cheese"),
    )
    _shielded = item_phrase_ur
    for src, dst in _and_shields:
        _shielded = re.sub(rf"(?i){re.escape(src)}", dst, _shielded)

    # ── Split on Urdu comma (،), regular comma, and اور / and ───────────
    chunks = re.split(r"\s*[،,]\s*|\s+اور\s+|\s+and\s+", _shielded, flags=re.IGNORECASE)
    chunks = [c.strip() for c in chunks if c and c.strip()]
    for _src, _dst in _and_shields:
        chunks = [c.replace(_dst, _src) for c in chunks]
    if not chunks:
        return []

    calls: List[Dict[str, Any]] = []

    for chunk in chunks:
        # Strip leading Urdu/digit quantity from this chunk.
        qty = 1
        qty_m = re.match(
            r"^(ایک|دو|تین|چار|پانچ|چھ|سات|آٹھ|نو|دس|\d+)\s+(.+)$", chunk
        )
        if qty_m:
            qty_tok = qty_m.group(1)
            qty = _URDU_QTY_WORDS.get(
                qty_tok, int(qty_tok) if qty_tok.isdigit() else 1
            )
            chunk = qty_m.group(2).strip()

        translated = _translate_urdu_item_phrase(chunk)

        resolved: Optional[str] = None
        for candidate in [translated, chunk]:
            if not candidate:
                continue
            resolved = _resolve_cart_item_name(candidate, voice_strict=voice_strict)
            if resolved:
                break

        if resolved:
            resolved_id, resolved_type = _lookup_resolved_item_id(resolved)
            args: Dict[str, str] = {"item_name": resolved, "quantity": str(qty)}
            if resolved_id is not None and resolved_type:
                args["item_id"] = str(resolved_id)
                args["item_type"] = resolved_type
            calls.append({"name": "add_to_cart", "args": args})

    return calls


def _detect_urdu_add_to_cart_intent(raw_transcript: str) -> bool:
    """Cheap check: does this Urdu transcript look like an add-to-cart command?

    Only fires on URDU-SCRIPT cart signals (e.g. کارٹ میں, ڈال دو).
    Roman-Urdu / mixed-language utterances like "cart میں add" are intentionally
    left to the deterministic + LLM path which handles them better.
    """
    t = (raw_transcript or "").strip()
    if not t:
        return False
    t_lower = t.lower()
    # Only Urdu-SCRIPT cart verbs — do NOT match Roman "cart" or "add karo".
    urdu_signals = [
        "کارٹ میں", "کاٹ میں",
        "cart میں", "cart mein",  # mixed Latin+Urdu (kiosk ASR)
        "ڈال دو", "ڈال دیں",
        "شامل کرو", "شامل کریں", "شامل کر \u062f\u0648",
        "ایڈ کرو", "ایڈ کریں",
    ]
    for sig in urdu_signals:
        if re.search(r"[a-z]", sig, flags=re.IGNORECASE):
            if sig.lower() in t_lower:
                return True
            continue
        if sig in t:
            return True
    return False


def _lookup_resolved_item_id(
    item_name: str,
) -> tuple:
    """Return (item_id, item_type) for an already-canonicalized item name.

    Tries menu_item first (exact name match) then deal.  Used to pass
    pre-resolved IDs to the Flutter client so it can skip a second HTTP call.
    Returns (None, None) on any miss or error.
    """
    try:
        rows = fetch_menu_items_by_name(item_name)
        for r in rows:
            if str(r.get("item_name") or "").strip().lower() == item_name.strip().lower():
                item_id = r.get("item_id")
                if item_id is not None:
                    return (int(item_id), "menu_item")
        # If ILIKE returned rows but none were exact, first row is still likely
        # correct (the caller already canonicalized the name via fuzzy match).
        if rows:
            item_id = rows[0].get("item_id")
            if item_id is not None:
                return (int(item_id), "menu_item")
    except Exception:
        pass

    try:
        rows = fetch_deals_by_name(item_name)
        for r in rows:
            if str(r.get("deal_name") or "").strip().lower() == item_name.strip().lower():
                deal_id = r.get("deal_id")
                if deal_id is not None:
                    return (int(deal_id), "deal")
        if rows:
            deal_id = rows[0].get("deal_id")
            if deal_id is not None:
                return (int(deal_id), "deal")
    except Exception:
        pass

    return (None, None)


def _build_add_to_cart_calls(
    raw: str,
    leading_qty: Optional[int] = None,
    *,
    voice_strict: bool = False,
) -> List[Dict[str, Any]]:
    chunks = _split_add_item_chunks(raw)
    if not chunks:
        return []

    calls: List[Dict[str, Any]] = []
    qty_pattern = r"(?P<qty>\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)"

    for idx, chunk in enumerate(chunks):
        quantity: Optional[int] = None
        item_part = chunk

        m = re.match(rf"^\s*{qty_pattern}\s+(?P<item>.+)$", chunk, flags=re.IGNORECASE)
        if m:
            quantity = _parse_qty_token(m.group("qty"))
            item_part = m.group("item")

        if quantity is None:
            if idx == 0 and leading_qty and leading_qty > 0:
                quantity = leading_qty
            else:
                quantity = 1

        item_name = _resolve_cart_item_name(item_part, voice_strict=voice_strict)
        if not item_name:
            continue

        # Resolve item_id + item_type so Flutter can skip its own /menu lookup.
        resolved_id, resolved_type = _lookup_resolved_item_id(item_name)

        args: Dict[str, str] = {
            "item_name": item_name,
            "quantity": str(quantity),
        }
        if resolved_id is not None and resolved_type:
            args["item_id"] = str(resolved_id)
            args["item_type"] = resolved_type

        calls.append({"name": "add_to_cart", "args": args})

    return calls


def _strip_leading_qty_token(s: str) -> str:
    """Turn '1 cheese burger' / 'two zinger' into 'cheese burger' / 'zinger'."""
    s = (s or "").strip()
    if not s:
        return s
    m = re.match(
        r"^\s*(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)\s+(.+)$",
        s,
        flags=re.IGNORECASE,
    )
    if m:
        q = m.group(1).lower()
        if q.isdigit() or q in _QTY_WORDS or q in ("a", "an"):
            return m.group(2).strip()
    return s


def _strip_trailing_remove_verbs(s: str) -> str:
    """Drop trailing Roman Urdu noise: remove krdo, karo, nikalo, etc."""
    s = (s or "").strip()
    if not s:
        return s
    s = re.sub(
        r"\s+(krdo|kardo|kar do|karo|karo|do|lo|please|nikalo|nikal do|"
        r"hatao|hata do|hatado|remove)\s*$",
        "",
        s,
        flags=re.IGNORECASE,
    )
    return s.strip(" .,!?").strip()


def _extract_remove_cart_item_text(t: str) -> Optional[str]:
    """Parse utterances like '1 cheese burger remove krdo', 'cart se naan nikalo'.

    Returns the item phrase to pass to :func:`_resolve_cart_item_name` (without
    a leading quantity token when it was only a quantity for the item).
    """
    t = (t or "").strip().lower()
    if not t:
        return None
    # Translator noise guard: "kar 2" should behave like "kar do".
    t = re.sub(r"\bkar\s*2\b", "kar do", t, flags=re.IGNORECASE)
    # ASR typo guard: "card mein/se" in cart edits usually means "cart".
    t = re.sub(r"\bcard(?=\s+(?:mein|me|mai|se)\b)", "cart", t, flags=re.IGNORECASE)

    def _clean_item_phrase(s: str) -> str:
        s = _strip_leading_qty_token(_strip_trailing_remove_verbs(s))
        # Drop transport/payment noise that should never be part of the item.
        s = re.sub(r"\b(?:cart|card)\b", " ", s, flags=re.IGNORECASE)
        s = re.sub(r"\b(?:payment|pay)\b", " ", s, flags=re.IGNORECASE)
        s = re.sub(r"\b(?:mein|me|mai|se|ko)\b", " ", s, flags=re.IGNORECASE)
        s = re.sub(r"\s+", " ", s).strip(" .,!?")
        return s

    # 1) X remove [krdo] — most common Roman Urdu order
    m = re.search(
        r"^(.+?)\s+remove(?:\s+(?:krdo|kardo|kar do|karo|do|please|lagao))?\s*$",
        t,
    )
    if m:
        return _clean_item_phrase(m.group(1))

    # 2) remove X [krdo] (imperative at sentence start)
    m = re.search(r"^(?:please\s+)?remove\s+(.+)$", t)
    if m:
        return _clean_item_phrase(m.group(1))

    # 3) cart se X nikalo / hatao
    m = re.search(
        r"^(?:cart|card)\s+se\s+(.+?)\s+(?:nikalo|nikal do|hatao|hata do|remove)(?:\s|$)",
        t,
    )
    if m:
        return _clean_item_phrase(m.group(1))

    # 4) X nikalo / X hata do / X nikal do (verb at end)
    m = re.search(
        r"^(.+?)\s+(?:nikalo|nikal do|hatao|hata do|hatado|hatado|hata(?:\s|$))(?:\s|$)",
        t,
    )
    if m:
        return _clean_item_phrase(m.group(1))

    # 5) delete / discard X
    m = re.search(r"\b(?:delete|discard)\s+(.+)$", t)
    if m:
        return _clean_item_phrase(m.group(1))

    return None


def _extract_change_quantity_args(t: str) -> Optional[Tuple[str, str]]:
    """Return (item_phrase, qty_str) for change-quantity commands.

    Covers English plus Roman Urdu: 'cheese burger ki quantity 2 kar do'.
    """
    t = (t or "").strip().lower()
    if not t:
        return None

    # English (existing patterns, slightly more flexible)
    m = re.search(
        r"\b(?:change|set)\s+(.+?)\s+(?:quantity\s+)?to\s+(\d+)\b",
        t,
    )
    if m:
        item = _strip_leading_qty_token(_strip_trailing_remove_verbs(m.group(1)))
        return item, m.group(2)

    m = re.search(
        r"\b(?:change|set)\s+(?:quantity\s+)?(?:of\s+)?(.+?)\s+to\s+(\d+)\b",
        t,
    )
    if m:
        item = _strip_leading_qty_token(_strip_trailing_remove_verbs(m.group(1)))
        return item, m.group(2)

    # Urdu / Roman: X ki quantity 2 kar do
    m = re.search(
        r"^(.+?)\s+ki\s+quantity\s+(\d+)(?:\s+kar do|\s+karo|\s+banado|do)?\s*$",
        t,
    )
    if m:
        item = _strip_leading_qty_token(_strip_trailing_remove_verbs(m.group(1)))
        return item, m.group(2)

    # X ki tadad 2 kar do
    m = re.search(
        r"^(.+?)\s+ki\s+(?:tadad|mikdar|count)\s+(\d+)(?:\s+kar do|\s+karo)?\s*$",
        t,
    )
    if m:
        item = _strip_leading_qty_token(_strip_trailing_remove_verbs(m.group(1)))
        return item, m.group(2)

    # quantity X 2 / X quantity 2
    m = re.search(r"^quantity\s+(.+?)\s+(\d+)(?:\s+kar do)?\s*$", t)
    if m:
        item = _strip_leading_qty_token(_strip_trailing_remove_verbs(m.group(1)))
        return item, m.group(2)

    m = re.search(r"^(.+?)\s+quantity\s+(\d+)(?:\s+kar do|\s+karo)?\s*$", t)
    if m:
        item = _strip_leading_qty_token(_strip_trailing_remove_verbs(m.group(1)))
        return item, m.group(2)

    m = re.search(r"^(.+?)\s+ko\s+(\d+)\s+(?:kar do|karo|banado|set)\s*$", t)
    if m:
        item = _strip_leading_qty_token(_strip_trailing_remove_verbs(m.group(1)))
        return item, m.group(2)

    return None


def _deterministic_chat_tool_calls(
    text: str,
    nlp: Dict[str, Any],
    *,
    voice_strict: bool = False,
) -> Optional[List[Dict[str, Any]]]:
    t = (text or "").strip().lower()
    if not t:
        return None
    t = re.sub(r"[\.\!\?۔]+$", "", t).strip()
    t_for_clear = re.sub(
        r"\bcard(?=\s+(?:mein|me|mai|se|میں|سے)\b)",
        "cart",
        t,
        flags=re.IGNORECASE,
    )

    kws = (nlp or {}).get("keywords", {})
    cuisine = (kws.get("cuisine") or "").strip()

    if ("ingredient" in t or "allergen" in t or "allergy" in t) and (" for " in t):
        query = t.split(" for ", 1)[1].strip()
        return [{"name": "retrieve_menu_context", "args": {"query": query}}]

    if ("custom deal" in t or "create a custom deal" in t) and not re.search(
        r"\b(yes|ok|okay|theek hai|ٹھیک ہے|haan|han|جی|confirm)\b", t
    ):
        return [{"name": "create_custom_deal", "args": {"query": text}}]

    # Delivery wording often says "package" instead of "deal".
    if (
        any(k in t for k in ("package", "pkg"))
        and any(k in t for k in ("show", "dikhao", "price", "rate", "available"))
    ):
        q = str((kws.get("query_text") or text)).strip()
        if q:
            return [{"name": "search_deal", "args": {"query": q}}]
        return [{"name": "search_deal", "args": {}}]

    if nlp.get("intent") == "search_deal":
        return None

    # Clear cart must win before the search_menu NLP shortcut mislabels removals.
    if (
        _wants_clear_entire_cart(t)
        or _wants_clear_entire_cart(text)
        or _wants_clear_entire_cart(t_for_clear)
    ):
        return [{"name": "clear_cart", "args": {}}]

    # Order ETA / tracking before search_menu for the same reason.
    if _text_requests_order_tracking(t) or _text_requests_order_tracking(text):
        return [{"name": "get_order_status", "args": {}}]

    # "What is in my cart?" (Urdu/Roman/English) must not be routed as menu search.
    _show_cart_needles = (
        "open cart",
        "show cart",
        "cart dikhao",
        "cart dikhado",
        "my cart",
        "meri cart",
        "mere cart",
        "cart mein kya",
        "cart me kya",
        "cart mai kya",
        "what in my cart",
        "what is in my cart",
        "items in my cart",
        "items in cart",
        "کارٹ میں کیا",
        "cart میں کیا",
    )
    if any(k in t for k in _show_cart_needles):
        return [{"name": "show_cart", "args": {}}]

    # Natural taste/craving asks (Urdu + Roman) should map deterministically.
    if any(k in t for k in ("میٹھا", "میٹھی", "meetha", "meethi", "sweet", "dessert")):
        return [{"name": "search_menu", "args": {"query": "sweet"}}]
    if any(k in t for k in ("spicy", "tikha", "teekha", "chatpata", "masaledar", "تیکھا", "مسالے")):
        return [{"name": "search_menu", "args": {"query": "spicy"}}]
    if any(k in t for k in ("mild", "light", "halka", "halki", "healthy", "diet", "ہلکا", "ہیلتھی")):
        return [{"name": "search_menu", "args": {"query": "light"}}]

    # Weather/cold-drink asks in Urdu/Roman often get normalized as generic
    # "item show". Route them to drinks instead of empty search_menu results.
    if any(k in t for k in ("thanda", "ٹھنڈا", "cold", "chilled", "گرمی")) and any(
        k in t for k in ("drink", "item", "show", "bata", "بتا", "recommend", "suggest")
    ):
        return [{"name": "search_menu", "args": {"query": "drinks"}}]

    if nlp.get("intent") == "search_menu":
        query = cuisine or (kws.get("query_text") or text)
        return [{"name": "search_menu", "args": {"query": str(query)}}]

    # Recommendation/discovery utterances with cuisine should open filtered menu.
    # Example: "mujhe chinese mein acha khana dikhao".
    if cuisine and any(
        k in t
        for k in (
            "suggest",
            "recommend",
            "show",
            "dikhao",
            "dikhado",
            "khana",
            "khaane",
            "eat",
            "eating",
            "for show",
        )
    ):
        if not any(k in t for k in ("deal", "ڈیل", "combo", "bundle")):
            return [{"name": "search_menu", "args": {"query": str(cuisine)}}]

    if any(k in t for k in ["waiter", "call waiter", "need waiter", "service please", "waiter please", "bill waiter"]):
        for_cash = any(k in t for k in ["cash bill", "cash payment", "pay cash"])
        args: Dict[str, str] = {}
        if for_cash:
            args["for_cash_payment"] = "true"
        return [{"name": "call_waiter", "args": args}]

    # Cart edit: change quantity before remove before add (avoids greedy 'add' matches).
    cq = _extract_change_quantity_args(t)
    if cq:
        item_phrase, qty_str = cq
        item = _resolve_cart_item_name(item_phrase, voice_strict=voice_strict)
        if item:
            return [
                {
                    "name": "change_quantity",
                    "args": {"item_name": item, "quantity": str(qty_str)},
                }
            ]

    remove_phrase = _extract_remove_cart_item_text(t)
    if remove_phrase:
        # Whole-cart phrasing should clear cart, not fuzzy-match an item.
        if any(
            k in remove_phrase
            for k in ("sab kuch", "sab", "all", "items", "sare", "saare", "saari", "tamam", "پورا", "سارا")
        ):
            return [{"name": "clear_cart", "args": {}}]
        item = _resolve_cart_item_name(remove_phrase, voice_strict=voice_strict)
        if item:
            # Safety rail: never remove a random fuzzy item in strict voice mode.
            if voice_strict:
                phrase_clean = _clean_item_name(remove_phrase)
                sim = _similarity(phrase_clean, item)
                phrase_tokens = {
                    tok for tok in re.findall(r"[a-z]+", phrase_clean.lower())
                    if len(tok) >= 3 and tok not in {"cart", "card", "payment", "remove"}
                }
                item_tokens = {
                    tok for tok in re.findall(r"[a-z]+", item.lower())
                    if len(tok) >= 3
                }
                if phrase_tokens and not (phrase_tokens & item_tokens) and sim < 0.90:
                    item = ""
                elif sim < 0.80:
                    item = ""
        if item:
            return [{"name": "remove_from_cart", "args": {"item_name": item}}]

    # Payment intent detection.
    # Broadened so "mujhe payment karni hai" / "payment karna hai" /
    # "i want to pay" / "make payment" etc. also trigger the flow. When the
    # user didn't specify card vs cash we emit payment_method="ask" so the
    # client can prompt for one and short-circuit to the chosen method on
    # the next utterance.
    _pay_method_keys = [
        "card payment", "cash payment", "pay by card", "pay by cash",
        "settle payment", "complete payment", "make payment",
        "do payment", "do the payment", "i want to pay",
        "want to pay", "want to make payment", "pay the bill",
        "payment karna", "payment karni", "payment karo",
        "payment krna", "payment krni", "payment krdo",
        "pay karna", "pay karni", "pay krdo",
    ]
    _has_explicit_card = any(
        k in t for k in [
            "card payment", "pay by card", "card se pay", "card se payment",
            "credit card", "debit card", "by card",
        ]
    ) or (
        # Bare 'card'/'credit'/'debit' next to a pay word.
        any(k in t for k in ["card", "credit", "debit"])
        and any(k in t for k in ["pay", "payment"])
    )
    _has_explicit_cash = any(
        k in t for k in [
            "cash payment", "pay by cash", "cash se pay", "cash se payment",
            "by cash", "cash me pay", "cash mein pay",
            "cod", "cash on delivery",
        ]
    ) or (
        any(k in t for k in ["cash", "naqd", "naqad", "cod", "cash on delivery"])
        and any(k in t for k in ["pay", "payment"])
    )
    _mentions_payment = (
        any(k in t for k in _pay_method_keys)
        or (
            # Bare "payment" without an earlier matched action — e.g.
            # "mujhe payment karni hai", "i want to do payment".
            " payment" in f" {t} " or t.startswith("payment")
        )
    )
    _removeish = any(k in t for k in ["remove", "nikal", "hata", "ریمو", "نکال", "ہٹا", "delete", "discard"])
    if _mentions_payment and not _removeish:
        if _has_explicit_card and _has_explicit_cash:
            method = "ask"
        elif _has_explicit_card:
            method = "card"
        elif _has_explicit_cash:
            method = "cash"
        else:
            method = "ask"
        return [{"name": "settle_payment", "args": {"payment_method": method}}]

    if "my orders" in t or "go to orders" in t or "open orders" in t:
        return [{"name": "navigate_to", "args": {"screen": "orders"}}]

    # Order tracking (Roman Urdu / Hinglish) — duplicated heuristics for text
    # paths that skipped the earlier block (e.g. mixed casing).
    if _text_requests_order_tracking(t):
        return [{"name": "get_order_status", "args": {}}]

    if (
        "open cart" in t
        or "show cart" in t
        or "cart dikhao" in t
        or "cart dikhado" in t
    ):
        return [{"name": "show_cart", "args": {}}]

    # Urdu/Roman clauses where item comes BEFORE add/include/shamil command
    # (e.g. "dine in hun, chicken burger apni tray mein add kar do cart").
    add_clause_candidates = [c.strip() for c in re.split(r"[،,]", t) if c and c.strip()]
    if not add_clause_candidates:
        add_clause_candidates = [t]
    _add_pre = None
    for _clause in add_clause_candidates:
        _add_pre = re.search(
            r"^(.+?)\s+(?:add|include|shamil)\s*"
            r"(?:karo|kar\s*do|kar\s*2|krdo|kardo|karein|please)?\s*"
            r"(?:cart|order|tray)?\s*(?:mein|me|mai|میں)?\s*$",
            _clause,
            flags=re.IGNORECASE,
        )
        if _add_pre:
            raw_phrase = (_add_pre.group(1) or "").strip()
            # Remove dine-in/delivery context words; keep probable item tokens.
            raw_phrase = re.sub(
                r"\b(?:yahan|restaurant|table|dine\s*in|hun|hoon|apni|tray|kiosk|"
                r"se|order|abhi|yahi|khaoonga|khaunga|home|delivery|ghar|mangwana|"
                r"wala|wali|walay|ke\s+liye|pe|mein|me|mai|karo|kar|do|krdo|kardo|"
                r"bhi|cod|cash|card|pay|payment|cart|include|shamil|add|"
                r"par|hai|han|ha|ke|liye)\b",
                " ",
                raw_phrase,
                flags=re.IGNORECASE,
            )
            raw_phrase = re.sub(r"\s+", " ", raw_phrase).strip(" .!?-—")
            if raw_phrase:
                calls = _build_add_to_cart_calls(raw_phrase, voice_strict=voice_strict)
                if calls:
                    return calls
        _add_cart_shamil = re.search(
            r"^(.+?)\s+cart\s*(?:mein|me|mai|میں)\s+"
            r"(?:shamil|include)\s*(?:karo|kar\s*do|krdo|kardo)?(?:\s+.*)?$",
            _clause,
            flags=re.IGNORECASE,
        )
        if _add_cart_shamil:
            raw_phrase = (_add_cart_shamil.group(1) or "").strip()
            raw_phrase = re.sub(
                r"\b(?:deliver|delivery|home|ghar|mangwana|dine\s*in|hun|hoon|kiosk|"
                r"restaurant|table|apni|tray|yahan|abhi|yahi|order|cart|bhi|"
                r"cod|cash|card|pay|payment|karo|kar|do|par|hai|han|ha|ke|liye)\b",
                " ",
                raw_phrase,
                flags=re.IGNORECASE,
            )
            raw_phrase = re.sub(r"\s+", " ", raw_phrase).strip(" .!?-—")
            if raw_phrase:
                calls = _build_add_to_cart_calls(raw_phrase, voice_strict=voice_strict)
                if calls:
                    return calls
        _add_put = re.search(
            r"^(.+?)\s+(?:cart|order)\s*(?:mein|me|mai|میں)?\s+"
            r"(?:dal|daal|ڈال)\s*(?:do|karo|krdo|kar\s*do)?\s*(?:cart|order)?\s*$",
            _clause,
            flags=re.IGNORECASE,
        )
        if _add_put:
            raw_phrase = (_add_put.group(1) or "").strip()
            raw_phrase = re.sub(
                r"\b(?:home|delivery|ghar|mangwana|dine\s*in|hun|hoon|kiosk|"
                r"restaurant|table|apni|tray|yahan|abhi|yahi|order|cart|"
                r"par|hai|han|ha|ke|liye)\b",
                " ",
                raw_phrase,
                flags=re.IGNORECASE,
            )
            raw_phrase = re.sub(r"\s+", " ", raw_phrase).strip(" .!?-—")
            if raw_phrase:
                calls = _build_add_to_cart_calls(raw_phrase, voice_strict=voice_strict)
                if calls:
                    return calls

    # Urdu word order but translated (e.g. "3 cola cart mein add karo")
    _cart_ctx = r"(?:cart\s+mein|cart\s+me|cart\s+mai|order\s+mein|cart|کارٹ)\s*(?:mein|میں|mai)\s*"
    m_add_ur = re.search(
        rf"^(.+?)\s+{_cart_ctx}add\s*(?:karo|kar\s*do|kar\s*2|krdo|karein|کر\s*دو|کرو|کر\s*2)?\s*$",
        t,
        flags=re.IGNORECASE,
    )
    if m_add_ur:
        calls = _build_add_to_cart_calls(
            m_add_ur.group(1),
            voice_strict=voice_strict,
        )
        if calls:
            return calls

    m_add = re.search(r"\b(?:add|include|shamil)\s+(?:(\d+)\s+)?(.+)$", t)
    if m_add:
        tail = (m_add.group(2) or "").strip()
        # "cart mein add karo" is not "add <item>" — avoid resolving the
        # imperative verb token itself ("karo") to a random menu item.
        if re.fullmatch(
            r"(?:karo|karein|karain|kar\s*do|kar\s*2|krdo|kardo|kijiye|kijiay|please|2|"
            r"cart|order|tray|cart\s+mein|cart\s+me|cart\s+mai)\s*",
            tail,
            flags=re.IGNORECASE,
        ):
            m_add = None
        # Latin "add" before an Urdu imperative tail (e.g. "... add کر دو") is not
        # "add <item>" — it is cart phrasing; skip so we don't fuzzy-match biryani.
        if re.search(r"[\u0600-\u06FF٫٬،]", tail) and not re.search(
            r"[a-z]{2,}", tail.lower()
        ):
            m_add = None
    if m_add:
        leading_qty = int(m_add.group(1)) if m_add.group(1) else None
        calls = _build_add_to_cart_calls(
            m_add.group(2),
            leading_qty=leading_qty,
            voice_strict=voice_strict,
        )
        if calls:
            return calls

    if any(k in t for k in ["place order", "confirm order", "checkout", "send to kitchen"]):
        _po_card = any(k in t for k in ["card", "credit", "debit"])
        _po_cashish = any(
            k in t for k in ["cash", "cod", "cash on delivery", "naqd", "naqad"]
        )
        if _po_card and _po_cashish:
            pm = "ASK"
        elif _po_card:
            pm = "CARD"
        elif _po_cashish:
            pm = "COD"
        else:
            pm = "COD"
        return [{"name": "place_order", "args": {"payment_method": pm}}]

    if any(k in t for k in ["what should i eat", "recommend", "suggest", "top seller", "popular", "best selling", "trending"]):
        # Natural preference asks should route to concrete menu slices so
        # delivery + dine-in behave consistently without LLM dependency.
        if any(k in t for k in ("thanda", "cold", "chilled", "گرمی", "ٹھنڈا", "ٹھنڈی")):
            return [{"name": "search_menu", "args": {"query": "drinks"}}]
        if any(k in t for k in ("spicy", "tikha", "teekha", "chatpata", "masaledar", "تیکھا", "مسالے")):
            return [{"name": "search_menu", "args": {"query": "spicy"}}]
        if any(k in t for k in ("light", "healthy", "diet", "halka", "halki", "ہلکا", "ہیلتھی")):
            return [{"name": "search_menu", "args": {"query": "light"}}]
        source = "top_sellers" if any(k in t for k in ["top seller", "popular", "best selling", "trending"]) else "general"
        return [{"name": "get_recommendations", "args": {"source": source}}]

    # ── Favourites intent ─────────────────────────────────────────────────────
    # Detect on BOTH normalized text AND raw transcript so the keyword is
    # caught even when the translator leaves it intact (e.g. "favorite").
    _fav_keywords = ("favourite", "favorite", "pasandida", "pasand", "پسندیدہ", "فیورٹ")
    _has_fav = any(k in t for k in _fav_keywords)

    if _has_fav:
        # ─────────────────────────────────────────────────────────────────────
        # ADD pattern — handles all four surface forms of the same command:
        #
        #   Roman Urdu : "cheese burger ko favourite me add krdo"
        #   Mixed      : "fast solo a کو favorite میں add کر 2"   ← real ASR output
        #   English    : "add cheese burger to favourites"
        #   Urdu script: "چیز برگر پسندیدہ میں شامل کرو"
        #
        # Key insight from logs:
        #   • Translator keeps Urdu postpositions as script (کو, میں, کر)
        #   • "دو" (do) is often translated as the digit "2"
        #   • Item name precedes the favourite keyword in Urdu word order
        # ─────────────────────────────────────────────────────────────────────

        # Urdu/mixed word-order: <item> [ko|کو] favourite [mein|میں] add [kar|کر] [do|2|...]
        fav_add_urdu_order = re.search(
            r"^(.+?)\s+"
            r"(?:ko|کو|ka|کا)?\s*"
            r"(?:favourite|favorite|pasandida|pasand|پسندیدہ|فیورٹ)e?s?\s+"
            r"(?:mein|me|میں|main|mai|mein\s+hi)?\s*"
            r"(?:add|shamil|شامل|daal|ڈال|rakh|رکھ|save)\s*"
            r"(?:kar|karo|krdo|kardo|karde|کر|کرو|کردو|kar\s+do|kar\s+dena)?\s*"
            r"(?:do|de|dena|dein|dijiye|دو|دیں|2)?\s*$",
            t,
            re.IGNORECASE,
        )

        # English word-order: "add <item> to favourites" / "save <item> in favourites"
        fav_add_english = re.search(
            r"\b(?:add|save|put|mark)\s+(.+?)\s+"
            r"(?:(?:in|to|as|into)\s+(?:my\s+)?)?(?:favourite|favorite)s?\b",
            t,
            re.IGNORECASE,
        )

        # English reversed: "add to favourites <item>"
        fav_add_english_rev = re.search(
            r"\b(?:add|save)\s+(?:(?:to|in|into)\s+)?(?:my\s+)?(?:favourite|favorite)s?\s+(.+)$",
            t,
            re.IGNORECASE,
        )

        # Pure Urdu-script: "چیز برگر پسندیدہ میں شامل کرو"
        fav_add_ur_script = re.search(
            r"^(.+?)\s+(?:پسندیدہ|فیورٹ)\s*(?:میں|مین)?\s*(?:شامل|ڈال|رکھ)\s*(?:کرو|کریں|کردو|دو|دیں)?\s*$",
            t,
        )

        # ── REMOVE patterns ──────────────────────────────────────────────────
        fav_rem_urdu_order = re.search(
            r"^(.+?)\s+"
            r"(?:ko|کو|ka|کا)?\s*"
            r"(?:favourite|favorite|pasandida|pasand|پسندیدہ|فیورٹ)e?s?\s*"
            r"(?:se|سے)?\s*"
            r"(?:remove|nikal|نکال|hata|ہٹا|delete|ہٹاؤ)\s*"
            r"(?:kar|karo|krdo|kardo|کر|کرو|کردو|kar\s+do)?\s*"
            r"(?:do|de|dena|دو|دیں|2)?\s*$",
            t,
            re.IGNORECASE,
        )

        fav_rem_english = re.search(
            r"\b(?:remove|delete|unmark)\s+(.+?)\s+from\s+(?:my\s+)?(?:favourite|favorite)s?\b",
            t,
            re.IGNORECASE,
        )

        fav_rem_ur_script = re.search(
            r"^(.+?)\s+(?:پسندیدہ|فیورٹ)\s*(?:سے)?\s*(?:ہٹا|نکال|ریموو)\s*(?:دو|دیں|کرو|کریں)?\s*$",
            t,
        )

        # ── Resolve add phrase ────────────────────────────────────────────────
        add_phrase = None
        if fav_add_urdu_order:
            add_phrase = fav_add_urdu_order.group(1).strip()
        elif fav_add_english:
            add_phrase = fav_add_english.group(1).strip()
        elif fav_add_english_rev:
            add_phrase = fav_add_english_rev.group(1).strip()
        elif fav_add_ur_script:
            add_phrase = fav_add_ur_script.group(1).strip()

        if add_phrase:
            # Strip any trailing Urdu/Roman noise the regex captured
            add_phrase = re.sub(
                r"\s+(?:ko|کو|kar|کر|karo|krdo|kardo|do|دو|de|dena|2)\s*$",
                "", add_phrase, flags=re.IGNORECASE,
            ).strip()
            item = _resolve_cart_item_name(add_phrase, voice_strict=voice_strict)
            if item:
                resolved_id, resolved_type = _lookup_resolved_item_id(item)
                fav_args = {"action": "add", "item_name": item}
                if resolved_id is not None and resolved_type:
                    fav_args["item_id"] = str(resolved_id)
                    fav_args["item_type"] = resolved_type
                return [{"name": "manage_favourites", "args": fav_args}]

        # ── Resolve remove phrase ─────────────────────────────────────────────
        rem_phrase = None
        if fav_rem_urdu_order:
            rem_phrase = fav_rem_urdu_order.group(1).strip()
        elif fav_rem_english:
            rem_phrase = fav_rem_english.group(1).strip()
        elif fav_rem_ur_script:
            rem_phrase = fav_rem_ur_script.group(1).strip()

        if rem_phrase:
            item = _resolve_cart_item_name(rem_phrase, voice_strict=voice_strict)
            if item:
                resolved_id, resolved_type = _lookup_resolved_item_id(item)
                fav_args = {"action": "remove", "item_name": item}
                if resolved_id is not None and resolved_type:
                    fav_args["item_id"] = str(resolved_id)
                    fav_args["item_type"] = resolved_type
                return [{"name": "manage_favourites", "args": fav_args}]

        # Default: show favourites screen
        return [{"name": "manage_favourites", "args": {"action": "show"}}]

    return None




def _safe_domain_reply(language: str) -> str:
    if language == "en":
        return "I can help with menu, deals, cart, order, payment, waiter, and order tracking."
    return "میں مینو، ڈیلز، کارٹ، آرڈر، ادائیگی، ویٹر کال اور آرڈر ٹریکنگ میں مدد کر سکتا ہوں۔"


# ──────────────────────────────────────────────────────────────
# CONVERSATIONAL WAITER (natural-language fallback)
# ──────────────────────────────────────────────────────────────
#
# When the user asks something the deterministic router can't answer as a
# discrete action — e.g. "mujhe kuch spicy chahiye, kya available hai?",
# "thanday mein kya hai?", "kuch mild recommend karo", "what's good
# today?" — we don't want to fall back to the canned domain string.
#
# Instead we act like a human waiter: ground the LLM in the ACTUAL menu
# catalog (so it can't hallucinate dishes), and let it answer naturally
# while recommending 1-3 real items that match the user's vibe.
#
# Kept cheap: the menu catalog is cached in-process and the prompt is
# short (~40 items × 1 line each).

_MENU_CATALOG_CACHE: Dict[str, Any] = {"items": None, "deals": None, "ts": 0.0}
_MENU_CATALOG_TTL_S: float = 120.0  # refresh every 2 minutes

# Trigger words that strongly suggest a conversational/recommendation
# question rather than a literal "search item X" lookup. Kept in lowercase
# and covers English + Roman Urdu + common Urdu-script forms.
_CONVERSATIONAL_TRIGGERS: tuple = (
    # spice / flavour
    "spicy", "mild", "hot", "tikha", "teekha", "chatpata", "chatpatta",
    "garam masala", "masaledar", "kam tikha", "kam teekha", "cheeni",
    "meetha", "meethi", "sweet", "sour", "khatta", "khatti", "karwa",
    "bitter", "namkeen", "salty",
    # temperature
    "thanda", "thandi", "thande", "thand", "cold", "chilled", "garam",
    "garma garam", "garmi", "hot drink", "garam cheez",
    # weight / diet
    "light", "halka", "halki", "healthy", "diet", "zyada bhari", "heavy",
    "filling", "bhari",
    # kid/veg
    "kids", "bachon", "bachchon", "veg", "vegetarian", "no meat",
    "bina gosht", "gosht ke bina",
    # generic asking
    "what do you recommend", "kya recommend", "kya suggest", "suggest karo",
    "recommend karo", "batao kya acha", "what's good", "whats good",
    "kya aacha", "kya acha hai", "aap kya", "what should",
    "kuch acha", "something nice", "something good",
    # availability-style probes
    "kya available", "kya hai aaj", "aaj kya", "what's available",
    "whats available", "what is available",
)

_CONVERSATIONAL_TRIGGERS_UR: tuple = (
    "تیکھا", "مسالے", "مسالا", "مسالے دار", "گرم", "ٹھنڈا", "ٹھنڈی",
    "ٹھنڈے", "میٹھا", "میٹھی", "کھٹا", "کھٹی", "نمکین", "ہلکا", "ہلکی",
    "بھاری", "ڈائٹ", "ہیلتھی", "تجویز", "سفارش", "کیا اچھا", "کیا ملتا",
    "کیا ہے", "کون سا",
)


def _is_conversational_query(
    raw_transcript: str,
    normalized_text: str,
    nlp: Dict[str, Any],
) -> bool:
    """Heuristic: does this utterance read like a chit-chat / taste-based
    question that deserves a waiter-style answer instead of a literal
    action?

    We return True only when NO concrete action intent is set (so real
    commands like "add biryani to cart", "show deals", "place order" still
    take the deterministic path). We also short-circuit on a short list of
    flavour / temperature / recommendation keywords that are reliable
    signals.
    """
    raw_l = (raw_transcript or "").lower()
    norm_l = (normalized_text or "").lower()

    # Never hijack a real action intent.
    intent = (nlp or {}).get("intent") or ""
    if intent in {"place_order", "search_deal"}:
        return False

    # Urdu-script triggers (raw transcript only).
    for kw in _CONVERSATIONAL_TRIGGERS_UR:
        if kw in raw_transcript:
            return True

    # Latin triggers on either form.
    for kw in _CONVERSATIONAL_TRIGGERS:
        if kw in raw_l or kw in norm_l:
            return True

    return False


def _load_menu_catalog_for_prompt(max_items: int = 50) -> List[Dict[str, Any]]:
    """Return a compact, cached list of menu rows for prompt grounding.

    We cache for ~2 min to avoid hitting Postgres on every utterance. Only
    fields useful to the LLM are kept: name, description, category,
    cuisine, price.
    """
    now = _time.time()
    cached = _MENU_CATALOG_CACHE.get("items")
    cached_ts = _MENU_CATALOG_CACHE.get("ts") or 0.0
    if cached is not None and (now - cached_ts) < _MENU_CATALOG_TTL_S:
        return cached[:max_items]

    try:
        q = text("""
            SELECT item_name, item_description, item_category,
                   item_cuisine, item_price
            FROM menu_item
            ORDER BY item_id
            LIMIT 200;
        """)
        with SQL_ENGINE.connect() as conn:
            rows = conn.execute(q).mappings().all()
        items = [dict(r) for r in rows]
    except Exception as e:
        logger.info(f"[CONVO][catalog_load_error] {e}")
        items = []

    _MENU_CATALOG_CACHE["items"] = items
    _MENU_CATALOG_CACHE["ts"] = now
    return items[:max_items]


def _format_catalog_for_prompt(items: List[Dict[str, Any]]) -> str:
    """Compact bullet list. Description is trimmed to keep tokens low."""
    if not items:
        return "(menu currently empty)"
    lines: List[str] = []
    for it in items:
        name = (it.get("item_name") or "").strip()
        if not name:
            continue
        desc = (it.get("item_description") or "").strip()
        if len(desc) > 140:
            desc = desc[:137].rstrip() + "…"
        cat = (it.get("item_category") or "").strip()
        cuisine = (it.get("item_cuisine") or "").strip()
        try:
            price = float(it.get("item_price") or 0)
            price_str = f"Rs.{int(price)}"
        except Exception:
            price_str = ""
        meta_bits = [b for b in (cuisine, cat, price_str) if b]
        meta = f" [{' · '.join(meta_bits)}]" if meta_bits else ""
        line = f"- {name}{meta}"
        if desc:
            line += f" — {desc}"
        lines.append(line)
    return "\n".join(lines)


def _extract_mentioned_items(
    reply_text: str,
    catalog: List[Dict[str, Any]],
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """Find catalog items whose names appear in the LLM reply so the UI
    can surface matching tiles alongside the spoken answer."""
    if not reply_text or not catalog:
        return []
    reply_l = reply_text.lower()
    matches: List[Dict[str, Any]] = []
    seen: set = set()
    for it in catalog:
        name = (it.get("item_name") or "").strip()
        if not name or name.lower() in seen:
            continue
        if name.lower() in reply_l:
            seen.add(name.lower())
            matches.append(it)
        if len(matches) >= limit:
            break
    return matches


def _conversational_waiter_reply(
    raw_transcript: str,
    normalized_text: str,
    language: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Optional[Dict[str, Any]]:
    """Produce a natural-language waiter reply grounded in the live menu.

    Returns a dict of {reply, menu_items, deals} or None on failure so
    the caller can fall back to the canned domain reply.
    """
    if ITEM_NAME_LLM is None or HumanMessage is None:
        return None

    raw = (raw_transcript or "").strip()
    norm = (normalized_text or "").strip()
    if not raw and not norm:
        return None

    catalog = _load_menu_catalog_for_prompt()
    catalog_text = _format_catalog_for_prompt(catalog)

    lang_instruction = (
        "Reply in Urdu (Urdu script). If the user wrote Roman Urdu, you may "
        "answer in Roman Urdu too, but default to Urdu script."
        if language != "en"
        else "Reply in natural English."
    )

    # Keep the last ~4 turns for light context; skip if not provided.
    history_block = ""
    if history:
        recent: List[str] = []
        for turn in history[-4:]:
            role = (turn.get("role") or "").strip().lower()
            content = (turn.get("content") or "").strip()
            if not content:
                continue
            if role == "user":
                recent.append(f"User: {content}")
            elif role in {"assistant", "ai"}:
                recent.append(f"Waiter: {content}")
        if recent:
            history_block = "\nRecent conversation:\n" + "\n".join(recent) + "\n"

    prompt = (
        "You are a friendly, concise Pakistani restaurant waiter helping a "
        "guest at a dine-in kiosk. Have a natural conversation about the "
        "menu: answer taste-based questions (spicy, mild, cold, sweet, "
        "light, filling, kid-friendly, vegetarian, what's good today, "
        "etc.) and give honest recommendations.\n\n"
        "STRICT RULES:\n"
        "1. ONLY recommend items that appear in the MENU list below. Use "
        "their EXACT names (copy the name verbatim).\n"
        "2. Never invent dishes, prices, or ingredients. If nothing fits, "
        "say so politely and suggest the closest real item.\n"
        "3. Infer spiciness / temperature / sweetness / heaviness from each "
        "item's name and description — do not make up attributes.\n"
        "4. Keep it SHORT: 2–4 sentences, waiter tone. No bullet lists, no "
        "markdown, no emojis, no prices unless the user asked.\n"
        "5. Recommend at most 3 items; usually 1–2 is better.\n"
        "6. If the user's message is not about food/menu, steer them back "
        "politely in one sentence.\n"
        f"7. {lang_instruction}\n\n"
        f"MENU (authoritative, do not add to it):\n{catalog_text}\n"
        f"{history_block}"
        f"\nGuest said (raw): {raw!r}\n"
        f"Guest said (normalized English): {norm!r}\n\n"
        "Now reply as the waiter in 2–4 natural sentences."
    )

    try:
        resp = ITEM_NAME_LLM.invoke([HumanMessage(content=prompt)])
        reply_text = str(getattr(resp, "content", "") or "").strip()
    except Exception as e:
        logger.info(f"[CONVO][llm_error] {e}")
        return None

    if not reply_text:
        return None

    # Strip any stray markdown/asterisks the model might emit.
    reply_text = re.sub(r"^[\s\*\-•]+", "", reply_text).strip()
    reply_text = reply_text.replace("**", "").replace("__", "").strip()
    # Collapse excessive newlines (we want a single spoken paragraph).
    reply_text = re.sub(r"\n{2,}", " ", reply_text)
    reply_text = re.sub(r"\s*\n\s*", " ", reply_text).strip()

    menu_items = _extract_mentioned_items(reply_text, catalog, limit=3)

    return {
        "reply": reply_text,
        "menu_items": menu_items,
        "deals": [],
    }


# ──────────────────────────────────────────────────────────────
# DESCRIBE-ITEM (INFO INTENT)
# ──────────────────────────────────────────────────────────────
#
# Triggered by utterances like
#   • "spring rolls ke baray mein batao"
#   • "اسپرنگ رول کے بارے میں بتاؤ"
#   • "tell me about fast solo A"
#
# We search menu_item + deal for the user's phrase and produce a single
# Urdu/English reply describing the match. No LLM round-trip on the hot
# path: item descriptions are pulled straight from the DB so the response
# is fast and deterministic.

def _detect_info_target(
    raw_transcript: str,
    normalized_text: str,
) -> Optional[str]:
    """Return the item phrase the user asked info about, or None.

    Runs the voice translator's ``detect_info_intent`` against BOTH the
    raw transcript (Urdu / Roman) AND the normalized English text so we
    catch the request regardless of which form the phrase survives in.
    """
    for candidate in (raw_transcript, normalized_text):
        hit = detect_info_intent(candidate or "")
        if hit and hit.get("is_info"):
            phrase = (hit.get("item") or "").strip()
            if phrase:
                return phrase
    return None


def _find_best_menu_item(phrase: str) -> Optional[Dict[str, Any]]:
    """Best-effort lookup: exact → ILIKE → resolve-by-canonical-name."""
    phrase = (phrase or "").strip()
    if not phrase:
        return None

    rows = fetch_menu_items_by_name(phrase)
    if rows:
        # Prefer exact name match when present, else first row.
        for r in rows:
            if str(r.get("item_name") or "").strip().lower() == phrase.lower():
                return r
        return rows[0]

    # Fall back to the cart-name resolver which already fuzzy-matches across
    # the full menu + deal catalog using string similarity.
    try:
        resolved = _resolve_cart_item_name(phrase, voice_strict=False)
    except Exception:
        resolved = ""
    if resolved and resolved.lower() != phrase.lower():
        rows = fetch_menu_items_by_name(resolved)
        if rows:
            for r in rows:
                if str(r.get("item_name") or "").strip().lower() == resolved.lower():
                    return r
            return rows[0]

    return None


def _find_best_deal(phrase: str) -> Optional[Dict[str, Any]]:
    phrase = (phrase or "").strip()
    if not phrase:
        return None

    rows = fetch_deals_by_name(phrase)
    if rows:
        for r in rows:
            if str(r.get("deal_name") or "").strip().lower() == phrase.lower():
                return r
        return rows[0]

    try:
        resolved = _resolve_cart_item_name(phrase, voice_strict=False)
    except Exception:
        resolved = ""
    if resolved and resolved.lower() != phrase.lower():
        rows = fetch_deals_by_name(resolved)
        if rows:
            for r in rows:
                if str(r.get("deal_name") or "").strip().lower() == resolved.lower():
                    return r
            return rows[0]

    return None


def _translate_to_urdu(text_value: str) -> str:
    """Best-effort English → Urdu translation using the existing Groq LLM.

    Keeps latency down by only running when the description clearly has
    English characters. Returns the original text on any failure so the
    caller can always use the return value as-is.
    """
    src = (text_value or "").strip()
    if not src:
        return ""

    # If it's already mostly Urdu, leave it alone.
    urdu_chars = sum(1 for c in src if "\u0600" <= c <= "\u06ff")
    if urdu_chars >= max(1, len(src.replace(" ", "")) // 3):
        return src

    if ITEM_NAME_LLM is None or HumanMessage is None:
        return src

    try:
        prompt = (
            "Translate the following restaurant menu description into simple, "
            "natural Urdu. Keep brand / dish names (e.g. 'Zinger Burger', "
            "'Chicken Tikka', 'Chow Mein') in their original form. Output "
            "ONLY the Urdu translation, no prefix or explanation.\n\n"
            f"English: {src}\nUrdu:"
        )
        resp = ITEM_NAME_LLM.invoke([HumanMessage(content=prompt)])
        out = str(getattr(resp, "content", "") or "").strip()
        # Strip any leading "Urdu:" the model might emit.
        out = re.sub(r"^\s*(?:urdu|اردو)\s*[:：]\s*", "", out, flags=re.IGNORECASE)
        return out or src
    except Exception as e:
        logger.info(f"[info_intent][translate_error] {e}")
        return src


def _format_menu_item_description(
    item: Dict[str, Any],
    language: str,
) -> str:
    name = str(item.get("item_name") or "").strip() or "Item"
    desc_en = str(item.get("item_description") or "").strip()
    price = item.get("item_price") or 0
    serving = item.get("serving_size")
    portion = str(item.get("quantity_description") or "").strip()
    prep = item.get("prep_time_minutes")
    category = str(item.get("item_category") or "").strip()
    cuisine = str(item.get("item_cuisine") or "").strip()

    if language == "en":
        parts = [f"{name}"]
        if desc_en:
            parts.append(f"— {desc_en}.")
        extras: List[str] = []
        if serving:
            try:
                s_int = int(serving)
                if s_int > 0:
                    extras.append(f"serves {s_int}")
            except Exception:
                pass
        if portion:
            extras.append(f"portion {portion}")
        if prep:
            try:
                p_int = int(prep)
                if p_int > 0:
                    extras.append(f"ready in {p_int} min")
            except Exception:
                pass
        if category:
            extras.append(f"category: {category}")
        if cuisine:
            extras.append(f"cuisine: {cuisine}")
        if extras:
            parts.append("(" + ", ".join(extras) + ")")
        if price:
            parts.append(f"Price Rs {price}.")
        return " ".join(parts).strip()

    # ── Urdu reply ────────────────────────────────────────────
    desc_ur = _translate_to_urdu(desc_en) if desc_en else ""
    parts = [f"{name} ہمارے مینو میں موجود ہے۔"]
    if desc_ur:
        parts.append(desc_ur)
    extras: List[str] = []
    if serving:
        try:
            s_int = int(serving)
            if s_int > 0:
                extras.append(f"{s_int} افراد کے لیے")
        except Exception:
            pass
    if portion:
        extras.append(f"پورشن: {portion}")
    if prep:
        try:
            p_int = int(prep)
            if p_int > 0:
                extras.append(f"تیاری کا وقت تقریباً {p_int} منٹ")
        except Exception:
            pass
    if extras:
        parts.append("، ".join(extras) + "۔")
    if price:
        parts.append(f"قیمت {price} روپے ہے۔")
    return " ".join(parts).strip()


def _format_deal_description(
    deal: Dict[str, Any],
    language: str,
) -> str:
    name = str(deal.get("deal_name") or "").strip() or "Deal"
    price = deal.get("deal_price") or 0
    serving = deal.get("serving_size")
    items_str = str(deal.get("items") or "").strip()

    serving_int = 0
    try:
        serving_int = int(serving or 0)
    except Exception:
        serving_int = 0

    if language == "en":
        parts = [f"{name} is one of our deals."]
        if items_str:
            parts.append(f"It includes {items_str}.")
        if serving_int > 0:
            parts.append(f"It serves {serving_int}"
                         + (" person." if serving_int == 1 else " people."))
        if price:
            parts.append(f"Price Rs {price}.")
        return " ".join(parts).strip()

    # Urdu
    parts = [f"{name} ہماری ڈیلز میں شامل ہے۔"]
    if items_str:
        items_ur = _translate_to_urdu(items_str)
        parts.append(f"اس میں {items_ur} شامل ہیں۔")
    if serving_int > 0:
        parts.append(f"یہ {serving_int} افراد کے لیے ہے۔")
    if price:
        parts.append(f"قیمت {price} روپے ہے۔")
    return " ".join(parts).strip()


def _describe_item_reply(phrase: str, language: str) -> Dict[str, Any]:
    """Resolve ``phrase`` against menu + deals and build a descriptive reply.

    Returns ``{"reply": str, "menu_items": [...], "deals": [...]}``. If
    nothing matches we still return a friendly "not found" reply so the
    caller can hand it to TTS as-is.
    """
    phrase = (phrase or "").strip()
    if not phrase:
        if language == "en":
            return {"reply": "Which item would you like to know about?",
                    "menu_items": [], "deals": []}
        return {"reply": "آپ کس آئٹم کے بارے میں جاننا چاہتے ہیں؟",
                "menu_items": [], "deals": []}

    # Decide what to prioritise: phrases containing "deal" / "ڈیل" look up
    # deals first, everything else prefers menu_item.
    lowered = phrase.lower()
    prefer_deal = (
        "deal" in lowered
        or "combo" in lowered
        or "bundle" in lowered
        or "solo" in lowered
        or "squad" in lowered
        or "duo" in lowered
        or "party" in lowered
        or "ڈیل" in phrase
    )

    menu_hit = None
    deal_hit = None
    if prefer_deal:
        deal_hit = _find_best_deal(phrase)
        if not deal_hit:
            menu_hit = _find_best_menu_item(phrase)
    else:
        menu_hit = _find_best_menu_item(phrase)
        if not menu_hit:
            deal_hit = _find_best_deal(phrase)

    if menu_hit:
        return {
            "reply": _format_menu_item_description(menu_hit, language),
            "menu_items": [menu_hit],
            "deals": [],
        }
    if deal_hit:
        return {
            "reply": _format_deal_description(deal_hit, language),
            "menu_items": [],
            "deals": [deal_hit],
        }

    if language == "en":
        return {
            "reply": f"Sorry, I couldn't find any menu item or deal named "
                     f"'{phrase}'.",
            "menu_items": [], "deals": [],
        }
    return {
        "reply": f"معذرت، '{phrase}' نام سے کوئی آئٹم یا ڈیل ہمارے مینو میں نہیں ملی۔",
        "menu_items": [], "deals": [],
    }


def _canonicalize_action_item_names(
    tool_calls: List[Dict[str, Any]],
    *,
    voice_strict: bool = False,
) -> List[Dict[str, Any]]:
    fixed_calls: List[Dict[str, Any]] = []
    for call in tool_calls or []:
        name = str((call or {}).get("name") or "").strip()
        args = dict((call or {}).get("args") or {})

        if name in {"add_to_cart", "remove_from_cart", "change_quantity"}:
            raw_item = str(args.get("item_name") or "").strip()
            if raw_item:
                resolved_item = _resolve_cart_item_name(
                    raw_item,
                    voice_strict=voice_strict,
                )
                args["item_name"] = resolved_item

        fixed_calls.append({"name": name, "args": args})

    return fixed_calls


_TOOL_NAME_ALIASES = {
    "show_order_status": "get_order_status",
    "check_order_status": "get_order_status",
    "order_tracking": "get_order_status",
}


def _alias_tool_call_names(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for c in tool_calls or []:
        if not c:
            continue
        nc = dict(c)
        nm = str(nc.get("name") or "").strip().lower()
        if nm in _TOOL_NAME_ALIASES:
            nc["name"] = _TOOL_NAME_ALIASES[nm]
        out.append(nc)
    return out


def _finalize_action_tool_calls(
    tool_calls: List[Dict[str, Any]],
    *,
    voice_strict: bool = False,
) -> List[Dict[str, Any]]:
    """Resolve item names, then apply restaurant ordering (cart before checkout, etc.)."""
    tool_calls = _alias_tool_call_names(tool_calls)
    fixed = _canonicalize_action_item_names(
        tool_calls,
        voice_strict=voice_strict,
    )
    try:
        planned = plan_restaurant_tool_calls(fixed)
        return planned
    except Exception as e:
        logger.info(f"[intent_pipeline] plan_restaurant_tool_calls fallback: {e}")
        return fixed


def _action_reply_from_tools(tool_calls: List[Dict[str, Any]], language: str) -> str:
    if not tool_calls:
        return _safe_domain_reply(language)

    # Multi-add summary: when the user adds several items in one breath
    # ("add biryani and zinger burger and coke"), the old behaviour only
    # announced the first item. Now we count the distinct items and speak
    # a natural multi-add acknowledgement.
    add_calls = [
        c for c in tool_calls
        if str((c or {}).get("name") or "").strip().lower() == "add_to_cart"
    ]
    if len(add_calls) >= 2:
        item_names = []
        for c in add_calls:
            nm = str(((c or {}).get("args") or {}).get("item_name") or "").strip()
            if nm and nm not in item_names:
                item_names.append(nm)
        if language == "en":
            if len(item_names) == 1:
                return f"Added {item_names[0]} to your cart."
            if len(item_names) == 2:
                return f"Added {item_names[0]} and {item_names[1]} to your cart."
            joined = ", ".join(item_names[:-1]) + f" and {item_names[-1]}"
            return f"Added {joined} to your cart."
        else:
            if len(item_names) == 1:
                return f"{item_names[0]} کارٹ میں شامل کر دیا۔"
            if len(item_names) == 2:
                return f"{item_names[0]} اور {item_names[1]} کارٹ میں شامل کر دیے۔"
            joined = "، ".join(item_names[:-1]) + f" اور {item_names[-1]}"
            return f"{joined} کارٹ میں شامل کر دیے۔"

    first = tool_calls[0] or {}
    name = str(first.get("name") or "").strip().lower()
    args = first.get("args") or {}

    if language == "en":
        if name == "add_to_cart":
            item = str((args or {}).get("item_name") or "").strip()
            return f"Added {item} to your cart." if item else "Item added to cart."
        if name == "remove_from_cart":
            return "Item removed from cart."
        if name == "clear_cart":
            return "Clearing your cart."
        if name == "change_quantity":
            return "Cart quantity updated."
        if name == "place_order":
            pm = str(args.get("payment_method") or "").strip().upper()
            if pm == "ASK":
                return (
                    "I'll place the order once you choose card or cash on delivery."
                )
            return "Sending your order now."
        if name == "settle_payment":
            method = str(args.get("payment_method") or "card").lower()
            if method == "cash":
                return "Processing cash settlement."
            if method == "ask":
                return "Would you like to pay by card or by cash?"
            return "Processing card payment."
        if name == "call_waiter":
            return "Calling a waiter now."
        if name in {"get_order_status", "order_status"}:
            return "Checking your latest order status."
        if name == "get_recommendations":
            return "Sharing top recommendations for you."
        if name == "show_cart":
            return "Opening your cart."
        if name == "navigate_to":
            return "Opening that section now."
        if name in {"search_menu", "search_deal", "retrieve_menu_context"}:
            if name == "search_menu":
                q = str(args.get("query") or "").strip().lower()
                if "spicy" in q:
                    return "Got it. Here are some spicy options."
                if any(k in q for k in ("sweet", "dessert", "meetha", "meethi")):
                    return "Sure, here are some sweet options."
                if any(k in q for k in ("drinks", "drink", "cold", "thanda", "chilled")):
                    return "Great choice. Here are some chilled drink options."
                if any(k in q for k in ("light", "mild", "healthy")):
                    return "Here are some light options for you."
            return "Here are the matching options."
        if name == "manage_favourites":
            action_val = str((args or {}).get("action") or "").lower()
            item_val = str((args or {}).get("item_name") or "").strip()
            if action_val == "add":
                return f"Added {item_val} to your favourites." if item_val else "Added to favourites."
            if action_val == "remove":
                return f"Removed {item_val} from your favourites." if item_val else "Removed from favourites."
            return "Opening your favourites."
        return "Done."

    if name == "add_to_cart":
        item = str((args or {}).get("item_name") or "").strip()
        return f"{item} کارٹ میں شامل کر دیا۔" if item else "آئٹم کارٹ میں شامل کر دیا۔"
    if name == "remove_from_cart":
        return "آئٹم کارٹ سے ہٹا دیا۔"
    if name == "clear_cart":
        return "کارٹ خالی کر دی گئی۔"
    if name == "change_quantity":
        return "کارٹ اپڈیٹ کر دی گئی۔"
    if name == "place_order":
        pm = str(args.get("payment_method") or "").strip().upper()
        if pm == "ASK":
            return (
                "براہ کرم بتائیں کارڈ سے ادا کریں گے یا ڈیلیوری پر کیش (COD)؟"
            )
        return "آپ کا آرڈر کچن کو بھیج رہا ہوں۔"
    if name == "settle_payment":
        method = str(args.get("payment_method") or "card").lower()
        if method == "cash":
            return "کیش ادائیگی کیلئے ویٹر کو مطلع کر رہا ہوں۔"
        if method == "ask":
            return "کارڈ سے ادائیگی کرنی ہے یا کیش سے؟"
        return "کارڈ ادائیگی پراسیس کر رہا ہوں۔"
    if name == "call_waiter":
        return "ویٹر کو اطلاع دے دی گئی ہے۔"
    if name in {"get_order_status", "order_status"}:
        return "آپ کے آرڈر کی تازہ حالت چیک کر رہا ہوں۔"
    if name == "get_recommendations":
        return "میں آپ کو ٹاپ سفارشات بتا رہا ہوں۔"
    if name == "show_cart":
        return "آپ کی کارٹ کھول رہا ہوں۔"
    if name == "navigate_to":
        return "متعلقہ اسکرین کھول رہا ہوں۔"
    if name in {"search_menu", "search_deal", "retrieve_menu_context"}:
        if name == "search_menu":
            q = str(args.get("query") or "").strip().lower()
            if "spicy" in q:
                return "بالکل، یہ رہے کچھ چٹ پٹے آپشنز۔"
            if any(k in q for k in ("sweet", "dessert", "meetha", "meethi")):
                return "ضرور، یہ رہے کچھ میٹھے آپشنز۔"
            if any(k in q for k in ("drinks", "drink", "cold", "thanda", "chilled")):
                return "بہترین، یہ رہے کچھ ٹھنڈے مشروبات۔"
            if any(k in q for k in ("light", "mild", "healthy")):
                return "یہ رہے آپ کیلئے ہلکے آپشنز۔"
        return "یہ رہے متعلقہ آپشنز۔"
    if name == "manage_favourites":
        action_val = str((args or {}).get("action") or "").lower()
        item_val = str((args or {}).get("item_name") or "").strip()
        if action_val == "add":
            return f"{item_val} فیورٹ میں شامل کر دیا۔" if item_val else "فیورٹ میں شامل کر دیا۔"
        if action_val == "remove":
            return f"{item_val} فیورٹ سے ہٹا دیا۔" if item_val else "فیورٹ سے ہٹا دیا۔"
        return "آپ کی پسندیدہ فہرست کھول رہا ہوں۔"
    return "ٹھیک ہے۔"


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
    if not menu_items and not deals:
        return "معذرت، اس نام سے کوئی آئٹم یا ڈیل نہیں ملی۔"

    lines: List[str] = []

    if menu_items:
        lines.append("یہ آئٹمز دستیاب ہیں:")
        for item in menu_items[:4]:
            name = str(item.get("item_name") or "Item")
            price = item.get("item_price") or 0
            lines.append(f"- {name} — Rs {price}")

    if deals:
        if lines:
            lines.append("")
        lines.append("یہ ڈیلز دستیاب ہیں:")
        for deal in deals[:4]:
            name = str(deal.get("deal_name") or "Deal")
            price = deal.get("deal_price") or 0
            serving = int(deal.get("serving_size") or 0)
            if serving > 0:
                lines.append(f"- {name} — Rs {price} ({serving} افراد)")
            else:
                lines.append(f"- {name} — Rs {price}")

    return "\n".join(lines)


@app.on_event("startup")
def warmup_whisper():
    if not VOICE_ENABLED:
        print("Voice warm-up skipped: Voice feature disabled")
        return

    _stt_backend = os.getenv("STT_BACKEND", "elevenlabs").strip().lower()

    if _stt_backend == "elevenlabs":
        # API-based backend — no model to load, no warmup needed
        print(f"[STT] Backend: ElevenLabs Scribe v2 (API) — no warmup required.")
        return

    # Local model backend — run the warmup inference pass
    print(f"[STT] Backend: Local Whisper — warming up model...")
    try:
        if warmup_transcriber is None:
            print("[STT] Whisper warm-up skipped: transcriber unavailable")
            return

        warmup_transcriber()
        print("[STT] Whisper warm-up complete!")

    except Exception as e:
        print("[STT] Whisper warm-up failed:", repr(e))

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
            OR item_description ILIKE :name
            OR item_category ILIKE :name
            OR item_cuisine ILIKE :name
            OR tags::text ILIKE :name
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
            OR mi.item_description ILIKE :name
            OR mi.item_category ILIKE :name
            OR mi.item_cuisine ILIKE :name
            OR mi.tags::text ILIKE :name
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

    lines: List[str] = []

    # Menu items section
    if menu_items:
        if language == "en":
            lines.append("These items are available:")
        else:
            lines.append("یہ آئٹمز دستیاب ہیں:")

        for item in menu_items[:4]:
            name = item.get("item_name", "")
            price = item.get("item_price", 0)
            lines.append(f"- {name} — Rs {price}")

    # Deals section
    if deals:
        lines.append("")

        if language == "en":
            lines.append("These deals are available:")
        else:
            lines.append("یہ ڈیلز دستیاب ہیں:")

        for deal in deals[:4]:
            name = deal.get("deal_name", "")
            price = deal.get("deal_price", 0)
            serving = int(deal.get("serving_size", 0) or 0)

            if language == "en":
                if serving > 0:
                    line = f"- {name} — Rs {price} (serves {serving})"
                else:
                    line = f"- {name} — Rs {price}"
            else:
                if serving > 0:
                    line = f"- {name} — Rs {price} ({serving} افراد)"
                else:
                    line = f"- {name} — Rs {price}"
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
    # Order tracking / ETA before describe-item — same ordering as /voice_chat
    # so English "what is the status of my order?" cannot become describe_item.
    if _text_requests_order_tracking(user_text) or _text_requests_order_tracking(
        normalized_text
    ):
        oc = [{"name": "get_order_status", "args": {}}]
        return {
            "success": True,
            "reply": _action_reply_from_tools(oc, language),
            "menu_items": [],
            "deals": [],
            "tool_calls": oc,
            "nlp": nlp,
            "memory_slots": mem.get("slots", {}) if mem else {},
            "raw": "order-status-precheck",
        }

    # ── Info / describe-item short-circuit (text chat) ─────────
    # Mirrors the voice flow so both entry points answer
    # "X ke baray mein batao" the same way.
    info_phrase = _detect_info_target(user_text, normalized_text)
    if info_phrase:
        info_result = _describe_item_reply(info_phrase, language)
        logger.info(
            "[CHAT] session=%s info_intent phrase='%s' matched_menu=%s matched_deals=%s",
            session_id,
            info_phrase,
            len(info_result.get("menu_items") or []),
            len(info_result.get("deals") or []),
        )
        return {
            "success": True,
            "reply": info_result["reply"],
            "menu_items": info_result.get("menu_items") or [],
            "deals": info_result.get("deals") or [],
            "tool_calls": [
                {"name": "describe_item", "args": {"item_name": info_phrase}}
            ],
            "nlp": nlp,
            "memory_slots": mem.get("slots", {}) if mem else {},
            "raw": f"info-intent:{info_phrase}",
        }

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
        if language == "en":
            custom_reply = result.get("message", "Custom deal generated.")
        else:
            custom_reply = "کسٹم ڈیل تیار ہے۔" if result.get("success") else "کسٹم ڈیل کیلئے مزید تفصیل بتائیں۔"
        return {
            "success": True,
            "reply": custom_reply,
            "menu_items": [],
            "deals": [result] if result.get("success") else [],
            "tool_calls": [],
            "nlp": nlp,
            "memory_slots": slots,
            "raw": result,
        }

    deterministic_calls = _deterministic_chat_tool_calls(normalized_text, nlp)
    if deterministic_calls:
        deterministic_calls = _finalize_action_tool_calls(deterministic_calls)
        return {
            "success": True,
            "reply": _action_reply_from_tools(deterministic_calls, language),
            "menu_items": [],
            "deals": [],
            "tool_calls": deterministic_calls,
            "nlp": nlp,
            "memory_slots": mem.get("slots", {}) if mem else {},
            "raw": "deterministic-routing",
        }

    # ── Conversational waiter short-circuit ────────────────────
    # Taste / temperature / recommendation questions ("kuch spicy chahiye",
    # "thanday mein kya hai?", "what do you recommend?") don't map cleanly
    # to a concrete action. Instead of dumping menu rows or a canned
    # fallback, answer naturally using a menu-grounded LLM call.
    if _is_conversational_query(user_text, normalized_text, nlp):
        convo = _conversational_waiter_reply(
            raw_transcript=user_text,
            normalized_text=normalized_text,
            language=language,
            history=None,
        )
        if convo and convo.get("reply"):
            return {
                "success": True,
                "reply": convo["reply"],
                "menu_items": convo.get("menu_items") or [],
                "deals": convo.get("deals") or [],
                "tool_calls": [],
                "nlp": nlp,
                "memory_slots": mem.get("slots", {}) if mem else {},
                "raw": "conversational-waiter",
            }

    # 1) Let LLM decide TOOL_CALLS (intent + query)
    ai_response = get_ai_response(
        user_input=normalized_text,
        conversation_history=[],
        menu_context=""
    )

    tool_calls = _finalize_action_tool_calls(
        getattr(ai_response, "tool_calls", []),
    )

    menu_items = []
    deals = []
    used_search_tool = False

    # 2) Execute DB searches based on TOOL_CALLs
    for call in tool_calls:
        if call["name"] in {"search_menu", "retrieve_menu_context"}:
            used_search_tool = True
            query = call["args"].get("query", "")
            menu_items = fetch_menu_items_by_name(query)
            deals = fetch_deals_by_name(query)

    # Deterministic menu fallback so menu/filter voice commands don't rely on free-text.
    if nlp["intent"] == "search_menu" and not used_search_tool:
        query = (nlp.get("keywords", {}).get("cuisine") or normalized_text)
        menu_items = fetch_menu_items_by_name(query)
        deals = fetch_deals_by_name(query)
        tool_calls = [{"name": "search_menu", "args": {"query": str(query)}}]
        used_search_tool = True

    # Deterministic deal-first path: avoid wrong LLM query opening menu-all view.
    if nlp["intent"] == "search_deal":
        deals = _search_deals_from_nlp(nlp, normalized_text)
        menu_items = []
        tool_calls = _build_deal_tool_calls(nlp)
        used_search_tool = True

    menu_items, deals, tool_calls = _merge_menu_and_deal_results(
        nlp, normalized_text, menu_items, deals, tool_calls
    )

    # Deterministic fallback: if deal intent but no deals, ask for custom deal using memory slots.
    # Skip when the user asked for menu+deals together and we still have menu rows to show.
    if (
        not deals
        and nlp["intent"] == "search_deal"
        and not (_want_menu_and_deals_together(nlp) and menu_items)
    ):
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
    elif tool_calls:
        # Action-only replies should remain short and deterministic.
        reply_text = _action_reply_from_tools(tool_calls, language)
    else:
        # Nothing matched. Try the waiter-style LLM before falling back to
        # the canned domain line so the guest still gets a helpful answer.
        convo = _conversational_waiter_reply(
            raw_transcript=user_text,
            normalized_text=normalized_text,
            language=language,
            history=None,
        )
        if convo and convo.get("reply"):
            if not menu_items:
                menu_items = convo.get("menu_items") or []
            reply_text = convo["reply"]
        else:
            reply_text = _safe_domain_reply(language)

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

        # ── Custom deal short-circuit ─────────────────────────
        # Run BEFORE _is_custom_deal_confirmation / search_deal routing so that
        # explicit "make me a deal" style requests never get hijacked by the
        # search_deal branch (which navigates to the deals tab instead of
        # creating one). Checks both the raw Urdu transcript and the
        # normalized English text, with an LLM tiebreaker for ambiguous
        # cases — see _route_custom_deal for details.
        custom_deal_route = _route_custom_deal(
            raw_transcript=transcript,
            normalized_text=normalized_text,
            nlp=nlp,
            slots=(mem.get("slots", {}) if mem else {}),
        )
        if custom_deal_route:
            slots = mem.get("slots", {}) if mem else {}
            slots["pending_custom_deal"] = False
            if custom_deal_route.get("cuisine"):
                slots["cuisine"] = custom_deal_route["cuisine"]
            if custom_deal_route.get("people"):
                slots["people"] = custom_deal_route["people"]
            if mem is not None:
                mem["slots"] = slots
                _SESSION_MEMORY[session_id] = mem

            tool_calls = [
                {
                    "name": "create_custom_deal",
                    "args": {
                        "query": custom_deal_route["query"],
                        "user_query": custom_deal_route["query"],
                    },
                }
            ]
            reply_text = (
                "آپ کیلئے کسٹم ڈیل تیار کر رہا ہوں…"
                if response_language != "en"
                else "Creating your custom deal..."
            )
            _voice_log(
                session_id,
                "custom_deal_route",
                source=custom_deal_route.get("source"),
                query=custom_deal_route["query"],
                cuisine=custom_deal_route.get("cuisine"),
                people=custom_deal_route.get("people"),
            )
            return {
                "success": True,
                "transcript": transcript,
                "normalized_text": normalized_text,
                "reply": reply_text,
                "menu_items": [],
                "deals": [],
                "tool_calls": tool_calls,
                "nlp": nlp,
                "memory_slots": slots,
                "raw": f"custom-deal-route:{custom_deal_route.get('source')}",
            }

        # ── Order tracking before describe-item ───────────────────
        # Stops phrases like "what is the status of my order?" from matching
        # the generic English "what is X" menu-info detector.
        if _text_requests_order_tracking(
            transcript
        ) or _text_requests_order_tracking(normalized_text):
            oc = [{"name": "get_order_status", "args": {}}]
            return {
                "success": True,
                "transcript": transcript,
                "normalized_text": normalized_text,
                "reply": _action_reply_from_tools(oc, response_language),
                "menu_items": [],
                "deals": [],
                "tool_calls": oc,
                "nlp": nlp,
                "memory_slots": (mem.get("slots", {}) if mem else {}),
                "raw": "order-status-precheck",
            }

        # ── Info / describe-item short-circuit ────────────────
        # Runs after custom-deal (so "deal banao" still wins) but before
        # generic tool routing, because the keyword detector would otherwise
        # send "spring rolls ke baray mein batao" to the add/search path.
        info_phrase = _detect_info_target(transcript, normalized_text)
        if info_phrase:
            info_result = _describe_item_reply(info_phrase, response_language)
            _voice_log(
                session_id,
                "info_intent",
                phrase=info_phrase,
                matched_menu=len(info_result.get("menu_items") or []),
                matched_deals=len(info_result.get("deals") or []),
            )
            return {
                "success": True,
                "transcript": transcript,
                "normalized_text": normalized_text,
                "reply": info_result["reply"],
                "menu_items": info_result.get("menu_items") or [],
                "deals": info_result.get("deals") or [],
                "tool_calls": [
                    {
                        "name": "describe_item",
                        "args": {"item_name": info_phrase},
                    }
                ],
                "nlp": nlp,
                "memory_slots": (mem.get("slots", {}) if mem else {}),
                "raw": f"info-intent:{info_phrase}",
            }

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
            if response_language == "en":
                custom_reply = result.get("message", "Custom deal generated.")
            else:
                custom_reply = "کسٹم ڈیل تیار ہے۔" if result.get("success") else "کسٹم ڈیل کیلئے مزید تفصیل بتائیں۔"
            return {
                "success": True,
                "transcript": transcript,
                "normalized_text": normalized_text,
                "reply": custom_reply,
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

        # 3) Deterministic-first routing, then LLM fallback.
        # voice_strict=True: do not fuzzy-map vague ASR tokens to random menu rows.
        _urdu_cart_intent_detected = False  # set True when Urdu-cart extractor fires
        deterministic_calls = _deterministic_chat_tool_calls(
            normalized_text, nlp, voice_strict=True
        )

        # ── Favourites dual-pass ──────────────────────────────────────────────
        # If normalized text didn't trigger a favourites action, try the raw
        # Urdu transcript so Roman-Urdu phrases like
        # "cheese burger ko favourite me add krdo" still work even when the
        # translator drops or changes "favourite".
        if not deterministic_calls:
            _fav_raw_keys = ("favourite", "favorite", "pasandida", "pasand", "پسندیدہ", "فیورٹ")
            raw_lower = (transcript or "").lower()
            if any(k in raw_lower for k in _fav_raw_keys):
                deterministic_calls = _deterministic_chat_tool_calls(
                    transcript, nlp, voice_strict=True
                )

        # Mixed Urdu + English dish names: translation often garbles names; raw
        # _extract_urdu_add_to_cart beats a single bad fuzzy add from normalized text.
        urdu_pref: List[Dict[str, Any]] = []
        if _detect_urdu_add_to_cart_intent(transcript):
            urdu_pref = _extract_urdu_add_to_cart(transcript, voice_strict=True)
        if urdu_pref:
            det_adds = [
                c
                for c in (deterministic_calls or [])
                if str((c or {}).get("name") or "") == "add_to_cart"
            ]
            tr = transcript or ""
            mixed_cart_tail = ("cart" in tr.lower()) and ("میں" in tr)
            if len(urdu_pref) > len(det_adds) or not det_adds:
                deterministic_calls = urdu_pref
            elif mixed_cart_tail and det_adds:
                deterministic_calls = urdu_pref

        if deterministic_calls:
            deterministic_calls = _finalize_action_tool_calls(
                deterministic_calls,
                voice_strict=True,
            )
            ai_response = SimpleNamespace(
                content=_action_reply_from_tools(deterministic_calls, response_language),
                tool_calls=deterministic_calls,
            )
            _voice_log(session_id, "deterministic", tool_calls=deterministic_calls)

        # 3b) Urdu-first add-to-cart short-circuit.
        # If the deterministic pass on the translated English text produced no
        # add_to_cart calls (or the translation garbled the item name), try to
        # extract the command directly from the raw Urdu transcript.  This fires
        # when the user said something like "دیسی ڈیو کارٹ میں ڈال دو" whose
        # translation came out as "Add desi dev cut in the order." — which the
        # deterministic pass can't resolve to a real menu item.
        elif _detect_urdu_add_to_cart_intent(transcript):
            urdu_calls = _extract_urdu_add_to_cart(transcript, voice_strict=True)
            if urdu_calls:
                urdu_calls = _finalize_action_tool_calls(
                    urdu_calls,
                    voice_strict=True,
                )
                ai_response = SimpleNamespace(
                    content=_action_reply_from_tools(urdu_calls, response_language),
                    tool_calls=urdu_calls,
                )
                _voice_log(session_id, "urdu_direct_cart", tool_calls=urdu_calls)
            else:
                # Urdu-script add-to-cart detected but item lookup failed.
                # Fall through to the LLM so it can attempt its own
                # resolution — but mark that we MUST NOT let the last-resort
                # conversational waiter fire (it gives unsolicited suggestions).
                _voice_log(session_id, "urdu_cart_fallback_to_llm", transcript=transcript)
                ai_response = SimpleNamespace(content="", tool_calls=[])
                _urdu_cart_intent_detected = True

        elif VOICE_LLM_ENABLED and _is_conversational_query(transcript, normalized_text, nlp):
            # ── Conversational waiter short-circuit ────────────
            # Taste / recommendation / temperature questions deserve a
            # natural reply grounded in the live menu, not a menu-dump or
            # canned fallback. Runs off the hot path of deterministic
            # actions so "add biryani", "show deals" etc. still win.
            convo_start = _time.time()
            convo = await run_in_threadpool(
                _conversational_waiter_reply,
                transcript,
                normalized_text,
                response_language,
                history,
            )
            if convo and convo.get("reply"):
                _voice_log(
                    session_id,
                    "conversational",
                    convo_ms=int((_time.time() - convo_start) * 1000),
                    matched_items=len(convo.get("menu_items") or []),
                )
                return {
                    "success": True,
                    "transcript": transcript,
                    "normalized_text": normalized_text,
                    "reply": convo["reply"],
                    "menu_items": convo.get("menu_items") or [],
                    "deals": [],
                    "tool_calls": [],
                    "nlp": nlp,
                    "memory_slots": mem.get("slots", {}) if mem else {},
                    "raw": "conversational-waiter",
                }
            # On failure fall through to the regular LLM tool-call path.
            ai_response = SimpleNamespace(content="", tool_calls=[])
        else:
            if not VOICE_LLM_ENABLED:
                _voice_log(session_id, "llm_disabled", reason="VOICE_LLM_ENABLED=0")
                ai_response = SimpleNamespace(content="", tool_calls=[])
            else:
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

        tool_calls = _finalize_action_tool_calls(
            getattr(ai_response, "tool_calls", []),
            voice_strict=True,
        )

        menu_items = []
        deals = []
        used_search_tool = False

        # 4) Execute tool calls (search)
        for call in tool_calls:
            if call["name"] in {"search_menu", "retrieve_menu_context"}:
                used_search_tool = True
                query = call["args"].get("query", "")
                menu_items = fetch_menu_items_by_name(query)
                deals = fetch_deals_by_name(query)

        # Deterministic menu fallback so menu/filter commands stay DB-grounded.
        if nlp["intent"] == "search_menu" and not used_search_tool:
            query = (nlp.get("keywords", {}).get("cuisine") or normalized_text)
            menu_items = fetch_menu_items_by_name(query)
            deals = fetch_deals_by_name(query)
            tool_calls = [{"name": "search_menu", "args": {"query": str(query)}}]
            used_search_tool = True

        # Deterministic deal-first path: if user asked for deals, do DB deal search from parsed slots.
        if nlp["intent"] == "search_deal":
            deals = _search_deals_from_nlp(nlp, normalized_text)
            menu_items = []
            tool_calls = _build_deal_tool_calls(nlp)
            used_search_tool = True

        menu_items, deals, tool_calls = _merge_menu_and_deal_results(
            nlp, normalized_text, menu_items, deals, tool_calls
        )

        # Deterministic fallback: no deal found, continue conversation with memory.
        if (
            not deals
            and nlp["intent"] == "search_deal"
            and not (_want_menu_and_deals_together(nlp) and menu_items)
        ):
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

        # 5) Format reply text
        if used_search_tool:
            if response_language == "en":
                reply_text = format_results_response(menu_items, deals, language="en")
            else:
                reply_text = format_items_urdu(menu_items, deals)
        elif tool_calls:
            reply_text = _action_reply_from_tools(tool_calls, response_language)
        else:
            # When we know this was an add-to-cart intent (Urdu-direct path
            # tried and fell through) do NOT run the conversational waiter —
            # it would give unsolicited food suggestions.
            if _urdu_cart_intent_detected:
                reply_text = _safe_domain_reply(response_language)
            else:
                # In strict deterministic voice mode, skip conversational LLM fallback.
                if not VOICE_LLM_ENABLED:
                    reply_text = _safe_domain_reply(response_language)
                else:
                    # Last-resort: try waiter-style LLM before the canned domain
                    # reply so guests still get a natural answer.
                    convo = await run_in_threadpool(
                        _conversational_waiter_reply,
                        transcript,
                        normalized_text,
                        response_language,
                        history,
                    )
                    if convo and convo.get("reply"):
                        reply_text = convo["reply"]
                        if not menu_items:
                            menu_items = convo.get("menu_items") or []
                        _voice_log(session_id, "conversational_fallback", matched_items=len(menu_items))
                    else:
                        reply_text = _safe_domain_reply(response_language)

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


class VoiceTtsRequest(BaseModel):
    text: str
    language: Optional[str] = "ur"


@app.post("/voice/tts")
async def voice_tts_endpoint(req: VoiceTtsRequest):
    if not TTS_ENABLED or generate_tts is None:
        raise HTTPException(status_code=503, detail="Voice TTS is temporarily disabled")

    text_value = (req.text or "").strip()
    if not text_value:
        raise HTTPException(status_code=400, detail="Text is required")

    lang = (req.language or "ur").strip().lower()
    lang = "en" if lang == "en" else "ur"

    try:
        file_path = await run_in_threadpool(generate_tts, text_value, lang)
        file_name = os.path.basename(file_path)
        return {
            "success": True,
            "audio_url": f"/voice/audio/{file_name}",
            "language": lang,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate TTS audio: {e}")


@app.get("/voice/audio/{file_name}")
def get_voice_audio(file_name: str):
    safe_name = os.path.basename(file_name)
    if safe_name != file_name:
        raise HTTPException(status_code=400, detail="Invalid file name")

    audio_path = os.path.join("audio", safe_name)
    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(audio_path, media_type="audio/mpeg", filename=safe_name)


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
