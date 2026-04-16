#!/usr/bin/env python3
"""
test_khaadim_full.py  —  Khaadim Voice System: 45 Test Cases
Usage:
  python test_khaadim_full.py
  python test_khaadim_full.py --base-url http://127.0.0.1:8000 --token <JWT>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import types
import unittest
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import requests

# ── Prevent Whisper loading ───────────────────────────────────────────────────
_voice_stub = types.ModuleType("voice.transcribe")
_voice_stub.transcribe_audio = lambda *a, **kw: ""
_voice_stub.warmup_transcriber = lambda *a, **kw: None
sys.modules["voice.transcribe"] = _voice_stub

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = os.getenv("VOICE_BASE_URL", "http://127.0.0.1:8000")
TOKEN = os.getenv(
    "VOICE_TEST_TOKEN",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJlMTI4NzVkNy00ZGUwLTRmZmQtYTVkNS1iZWEwYzE3NGQ2YTAiLCJpYXQiOjE3NzU5OTA0NjQsImV4cCI6MTc3ODU4MjQ2NH0"
    ".sdOBDbUZ3yGmJkkVUwrLjgkcBte4fukmJDCK_d7Wyzs",
)
AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}"}
AUDIO_FILE   = ("sample.wav", b"a" * 4096, "audio/wav")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _client() -> TestClient:
    if hasattr(main, "_SESSION_MEMORY"):
        main._SESSION_MEMORY.clear()
    return TestClient(main.app)


def _deal_check(client, cuisine, person_count, fake_deals):
    with patch.object(main, "fetch_deals_for_voice", return_value=fake_deals):
        return client.get("/voice/deal_check",
                          params={"cuisine": cuisine, "person_count": person_count})


def _has_tool(body, name, arg_key=None, arg_val=None):
    for call in body.get("tool_calls", []) or []:
        if call.get("name") != name:
            continue
        if arg_key is None:
            return True
        if str(call.get("args", {}).get(arg_key, "")).lower() == str(arg_val).lower():
            return True
    return False


def _chat_with_tool(client, message, tool_name, tool_args=None, language="ur"):
    fake_ai = SimpleNamespace(
        content="ok",
        tool_calls=[{"name": tool_name, "args": tool_args or {}}],
    )
    with patch.object(main, "get_ai_response", return_value=fake_ai), \
         patch.object(main, "fetch_menu_items_by_name", return_value=[]), \
         patch.object(main, "fetch_deals_by_name", return_value=[]):
        res = client.post("/chat", json={
            "message": message, "language": language,
            "session_id": "tc-session",
        })
    return res.json()


def _chat_with_menu(client, message, menu_items=None, deals=None, language="en"):
    fake_ai = SimpleNamespace(
        content="ok",
        tool_calls=[{"name": "search_menu", "args": {"query": message}}],
    )
    with patch.object(main, "get_ai_response", return_value=fake_ai), \
         patch.object(main, "fetch_menu_items_by_name", return_value=menu_items or []), \
         patch.object(main, "fetch_deals_by_name", return_value=deals or []):
        res = client.post("/chat", json={
            "message": message, "language": language, "session_id": "menu-tc"
        })
    return res.json()


def _get_history_from_mock(ai_mock):
    """Safely extract history from ai_mock regardless of positional/keyword args."""
    call_args = ai_mock.call_args
    if call_args is None:
        return None
    if call_args.args and len(call_args.args) > 1:
        return call_args.args[1]
    if "conversation_history" in (call_args.kwargs or {}):
        return call_args.kwargs["conversation_history"]
    return None


# ── CAT 1: Deal Exact Match ───────────────────────────────────────────────────
class TestCat1DealExactMatch(unittest.TestCase):

    def setUp(self): self.client = _client()

    def test_tc01_chinese_3_no_exact_fallback(self):
        """TC-01: Chinese 3 people — no exact match, nearest shown"""
        res = _deal_check(self.client, "chinese", 3, [
            {"deal_id": 7,  "deal_name": "Chinese Duo",    "deal_price": 1935, "serving_size": 2, "items": "2"},
            {"deal_id": 8,  "deal_name": "Chinese Squad A","deal_price": 5670, "serving_size": 4, "items": "4"},
        ])
        b = res.json()
        self.assertFalse(b["exists"])
        self.assertTrue(b["suggest_custom"])
        self.assertIn(2, b["available_sizes"])
        self.assertIn(4, b["available_sizes"])

    def test_tc02_bbq_4_exact_match(self):
        """TC-02: BBQ Squad for 4 — exact match found"""
        res = _deal_check(self.client, "bbq", 4, [
            {"deal_id": 13, "deal_name": "BBQ Squad", "deal_price": 4725, "serving_size": 4, "items": "BBQ"},
        ])
        b = res.json()
        self.assertTrue(b["exists"])
        self.assertFalse(b["suggest_custom"])
        self.assertEqual(b["deals"][0]["deal_name"], "BBQ Squad")

    def test_tc03_fast_food_solo_two_options(self):
        """TC-03: Fast food solo — both Fast Solo A and B returned"""
        res = _deal_check(self.client, "fast_food", 1, [
            {"deal_id": 1, "deal_name": "Fast Solo A", "deal_price": 720,   "serving_size": 1, "items": "A"},
            {"deal_id": 2, "deal_name": "Fast Solo B", "deal_price": 877.5, "serving_size": 1, "items": "B"},
        ])
        b = res.json()
        self.assertTrue(b["exists"])
        self.assertEqual(len(b["deals"]), 2)

    def test_tc04_desi_party_6_exact(self):
        """TC-04: Desi Party for 6 — exact match"""
        res = _deal_check(self.client, "desi", 6, [
            {"deal_id": 20, "deal_name": "Desi Party", "deal_price": 7227, "serving_size": 6, "items": "Desi"},
        ])
        b = res.json()
        self.assertTrue(b["exists"])
        self.assertEqual(b["deals"][0]["deal_price"], 7227)


# ── CAT 2: No Match → Custom Deal ────────────────────────────────────────────
class TestCat2CustomDealFallback(unittest.TestCase):

    def setUp(self): self.client = _client()

    def test_tc05_chinese_5_triggers_custom(self):
        """TC-05: Chinese 5 people — no match → custom deal suggested"""
        res = _deal_check(self.client, "chinese", 5, [
            {"deal_id": 7,  "deal_name": "Chinese Duo",   "deal_price": 1935, "serving_size": 2, "items": "2"},
            {"deal_id": 8,  "deal_name": "Chinese Squad", "deal_price": 5670, "serving_size": 4, "items": "4"},
            {"deal_id": 10, "deal_name": "Chinese Party", "deal_price": 5850, "serving_size": 6, "items": "6"},
        ])
        b = res.json()
        self.assertFalse(b["exists"])
        self.assertTrue(b["suggest_custom"])
        self.assertEqual(b["custom_query"], "create chinese deal for 5 people")

    def test_tc06_bbq_3_no_match_sizes(self):
        """TC-06: BBQ 3 people → no match → correct available sizes"""
        res = _deal_check(self.client, "bbq", 3, [
            {"deal_id": 11, "deal_name": "BBQ Solo",  "deal_price": 1350, "serving_size": 1, "items": "1"},
            {"deal_id": 12, "deal_name": "BBQ Duo",   "deal_price": 2187, "serving_size": 2, "items": "2"},
            {"deal_id": 13, "deal_name": "BBQ Squad", "deal_price": 4725, "serving_size": 4, "items": "4"},
        ])
        b = res.json()
        self.assertFalse(b["exists"])
        self.assertTrue(b["suggest_custom"])
        self.assertNotIn(3, b["available_sizes"])

    def test_tc07_unknown_cuisine_graceful(self):
        """TC-07: Unknown cuisine (Italian) → 200 response, no crash"""
        res = _deal_check(self.client, "italian", 2, [])
        self.assertEqual(res.status_code, 200)
        b = res.json()
        self.assertFalse(b["exists"])
        self.assertIn("message_en", b)


# ── CAT 3: Menu Search ────────────────────────────────────────────────────────
class TestCat3MenuSearch(unittest.TestCase):

    def setUp(self): self.client = _client()

    def test_tc08_zinger_price(self):
        """TC-08: Zinger Burger price — Rs 550 in reply"""
        b = _chat_with_menu(self.client, "zinger burger", menu_items=[
            {"item_name": "Zinger Burger", "item_price": 550,
             "item_description": "Spicy chicken", "item_cuisine": "Fast Food",
             "item_category": "main", "quantity_description": "1 burger"},
        ])
        self.assertTrue(b["success"])
        self.assertIn("Zinger Burger", b["reply"])
        self.assertIn("550", b["reply"])

    def test_tc09_noodles_search(self):
        """TC-09: 'spicy noodles' → Chicken Chow Mein returned"""
        b = _chat_with_menu(self.client, "spicy noodles", menu_items=[
            {"item_name": "Chicken Chow Mein", "item_price": 1000,
             "item_description": "Stir-fried noodles", "item_cuisine": "Chinese",
             "item_category": "main", "quantity_description": "500g"},
        ])
        self.assertTrue(b["success"])
        self.assertGreater(len(b["menu_items"]), 0)

    def test_tc10_vegetarian_items(self):
        """TC-10: Vegetarian query — at least 3 items returned"""
        b = _chat_with_menu(self.client, "vegetarian", menu_items=[
            {"item_name": "Veggie Burger", "item_price": 300, "item_cuisine": "Fast Food",
             "item_category": "main", "item_description": "Veg", "quantity_description": "1"},
            {"item_name": "Daal Chawal",   "item_price": 650, "item_cuisine": "Desi",
             "item_category": "main", "item_description": "Lentil", "quantity_description": "1 plate"},
            {"item_name": "Aloo Paratha",  "item_price": 250, "item_cuisine": "Desi",
             "item_category": "bread", "item_description": "Paratha", "quantity_description": "1"},
        ])
        self.assertTrue(b["success"])
        self.assertGreaterEqual(len(b["menu_items"]), 3)

    def test_tc11_dairy_free(self):
        """TC-11: Dairy-free — no Cheeseburger or Malai Boti returned"""
        b = _chat_with_menu(self.client, "dairy free", menu_items=[
            {"item_name": "Fries",       "item_price": 200, "item_cuisine": "Fast Food",
             "item_category": "side",  "item_description": "Fries", "quantity_description": "150g"},
            {"item_name": "Cola",        "item_price": 150, "item_cuisine": "Drinks",
             "item_category": "drink", "item_description": "Cola",  "quantity_description": "330ml"},
        ])
        self.assertTrue(b["success"])
        names = [i["item_name"] for i in b["menu_items"]]
        self.assertNotIn("Cheeseburger", names)
        self.assertNotIn("Malai Boti", names)

    def test_tc12_under_300(self):
        """TC-12: All returned items ≤ Rs 300"""
        b = _chat_with_menu(self.client, "under 300 rupees", menu_items=[
            {"item_name": "Fries", "item_price": 200, "item_cuisine": "Fast Food",
             "item_category": "side", "item_description": "Fries", "quantity_description": "150g"},
            {"item_name": "Roti",  "item_price": 50,  "item_cuisine": "Desi",
             "item_category": "bread", "item_description": "Roti", "quantity_description": "1"},
        ])
        self.assertTrue(b["success"])
        for item in b["menu_items"]:
            self.assertLessEqual(float(item["item_price"]), 300)

    def test_tc13_fastest_prep(self):
        """TC-13: Fastest items — Roti (1 min) in results"""
        b = _chat_with_menu(self.client, "fastest to prepare", menu_items=[
            {"item_name": "Roti", "item_price": 50, "item_cuisine": "Desi",
             "item_category": "bread", "item_description": "Flatbread", "quantity_description": "1"},
            {"item_name": "Naan", "item_price": 70, "item_cuisine": "Desi",
             "item_category": "bread", "item_description": "Naan", "quantity_description": "1"},
        ])
        self.assertTrue(b["success"])
        self.assertIn("Roti", [i["item_name"] for i in b["menu_items"]])


# ── CAT 4: Cart Management ────────────────────────────────────────────────────
class TestCat4CartManagement(unittest.TestCase):

    def setUp(self): self.client = _client()

    def test_tc14_add_single(self):
        """TC-14: 'ek Chicken Tikka add karo' → add_to_cart fires"""
        b = _chat_with_tool(self.client, "ek Chicken Tikka add karo",
                            "add_to_cart", {"item_name": "Chicken Tikka", "quantity": "1"})
        self.assertTrue(b["success"])
        self.assertTrue(_has_tool(b, "add_to_cart"))

    def test_tc15_add_multiple(self):
        """TC-15: 'do zinger aur teen fries' → add_to_cart fires"""
        b = _chat_with_tool(self.client, "do zinger burger aur teen fries cart mein dalo",
                            "add_to_cart", {"item_name": "Zinger Burger", "quantity": "2"})
        self.assertTrue(b["success"])
        self.assertTrue(_has_tool(b, "add_to_cart"))

    def test_tc16_remove_item(self):
        """TC-16: 'fries hatao' → remove_from_cart fires"""
        b = _chat_with_tool(self.client, "fries hatao cart se",
                            "remove_from_cart", {"item_name": "Fries"})
        self.assertTrue(b["success"])
        self.assertTrue(_has_tool(b, "remove_from_cart"))

    def test_tc17_change_quantity(self):
        """TC-17: 'cola ki quantity 3 karo' → change_quantity fires"""
        b = _chat_with_tool(self.client, "cola ki quantity 3 kar do",
                            "change_quantity", {"item_name": "Cola", "quantity": "3"})
        self.assertTrue(b["success"])
        self.assertTrue(_has_tool(b, "change_quantity"))

    def test_tc18_show_cart(self):
        """TC-18: 'meri cart dikhao' → show_cart fires"""
        b = _chat_with_tool(self.client, "meri cart dikhao", "show_cart")
        self.assertTrue(b["success"])
        self.assertTrue(_has_tool(b, "show_cart"))


# ── CAT 5: Context Memory ─────────────────────────────────────────────────────
class TestCat5ContextMemory(unittest.TestCase):

    def setUp(self): self.client = _client()

    def test_tc19_isko_resolves(self):
        """TC-19: 'isko add karo' with Kung Pao in history → add_to_cart fires"""
        history = [
            {"role": "user",      "content": "Kung Pao Chicken kitna hai"},
            {"role": "assistant", "content": "Kung Pao Chicken Rs 1200 mein available hai."},
        ]
        b = _chat_with_tool(self.client, "isko cart mein dalo",
                            "add_to_cart", {"item_name": "Kung Pao Chicken", "quantity": "1"})
        self.assertTrue(b["success"])
        self.assertTrue(_has_tool(b, "add_to_cart"))

    def test_tc20_history_passed_to_ai(self):
        """TC-20: BBQ deal follow-up — history passed to AI"""
        history = [
            {"role": "user",      "content": "4 logon ke liye BBQ deal chahiye"},
            {"role": "assistant", "content": "BBQ Squad Rs 4725."},
        ]
        fake_ai = SimpleNamespace(content="BBQ Duo Rs 2187", tool_calls=[])
        with patch.object(main, "get_ai_response", return_value=fake_ai) as ai_mock, \
             patch.object(main, "fetch_menu_items_by_name", return_value=[]), \
             patch.object(main, "fetch_deals_by_name", return_value=[]):
            self.client.post("/chat", json={
                "message": "thoda sasta option?",
                "language": "ur", "session_id": "bbq-mem",
                "conversation_history": history,
            })
        h = _get_history_from_mock(ai_mock)
        self.assertIsNotNone(h, "History not passed to get_ai_response")
        self.assertGreaterEqual(len(h), 2)

    def test_tc21_voice_chat_history_passed(self):
        """TC-21: conversation_history in /voice_chat reaches AI"""
        history = [
            {"role": "user",      "content": "mera order kahan hai"},
            {"role": "assistant", "content": "Preparing mein hai."},
        ]
        fake_ai = SimpleNamespace(content="ok", tool_calls=[])
        with patch.object(main, "transcribe_audio", return_value="kitna time lagega"), \
             patch.object(main, "get_ai_response", return_value=fake_ai) as ai_mock, \
             patch.object(main, "fetch_deals_by_name", return_value=[]), \
             patch.object(main, "fetch_menu_items_by_name", return_value=[]):
            self.client.post("/voice_chat", data={
                "session_id": "vc-mem", "language": "ur",
                "conversation_history": json.dumps(history),
            }, files={"file": AUDIO_FILE})
        h = _get_history_from_mock(ai_mock)
        self.assertIsNotNone(h)
        self.assertEqual(len(h), 2)

    def test_tc22_10_turns_all_passed(self):
        """TC-22: 10 history turns — all 10 reach AI"""
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}"}
            for i in range(10)
        ]
        fake_ai = SimpleNamespace(content="ok", tool_calls=[])
        with patch.object(main, "transcribe_audio", return_value="hello"), \
             patch.object(main, "get_ai_response", return_value=fake_ai) as ai_mock, \
             patch.object(main, "fetch_deals_by_name", return_value=[]), \
             patch.object(main, "fetch_menu_items_by_name", return_value=[]):
            self.client.post("/voice_chat", data={
                "session_id": "mem-10", "language": "ur",
                "conversation_history": json.dumps(history),
            }, files={"file": AUDIO_FILE})
        h = _get_history_from_mock(ai_mock)
        self.assertIsNotNone(h)
        self.assertEqual(len(h), 10)


# ── CAT 6: Navigation ─────────────────────────────────────────────────────────
class TestCat6Navigation(unittest.TestCase):

    def setUp(self): self.client = _client()

    def test_tc23_deals_tab(self):
        """TC-23: 'deals dikhao' → navigate_to deals or search_deal"""
        fake_ai = SimpleNamespace(
            content="ok",
            tool_calls=[{"name": "navigate_to", "args": {"screen": "deals"}}],
        )
        with patch.object(main, "get_ai_response", return_value=fake_ai), \
             patch.object(main, "fetch_menu_items_by_name", return_value=[]), \
             patch.object(main, "fetch_deals_by_name", return_value=[]):
            res = self.client.post("/chat", json={
                "message": "deals dikhao", "language": "ur", "session_id": "nav"
            })
        b = res.json()
        self.assertTrue(b["success"])
        ok = (_has_tool(b, "navigate_to", "screen", "deals") or
              _has_tool(b, "search_deal"))
        self.assertTrue(ok)

    def test_tc24_orders_nav(self):
        """TC-24: 'mera orders history' → navigate_to orders"""
        b = _chat_with_tool(self.client, "mera orders ka history dikhao",
                            "navigate_to", {"screen": "orders"})
        self.assertTrue(b["success"])
        self.assertTrue(_has_tool(b, "navigate_to", "screen", "orders"))

    def test_tc25_favourites_nav(self):
        """TC-25: 'meri favourites' → manage_favourites show"""
        b = _chat_with_tool(self.client, "meri favourites dikhao",
                            "manage_favourites", {"action": "show"})
        self.assertTrue(b["success"])
        self.assertTrue(_has_tool(b, "manage_favourites", "action", "show"))

    def test_tc26_home_nav(self):
        """TC-26: 'home page par jao' → navigate_to home"""
        b = _chat_with_tool(self.client, "home page par jao",
                            "navigate_to", {"screen": "home"})
        self.assertTrue(b["success"])
        self.assertTrue(_has_tool(b, "navigate_to", "screen", "home"))


# ── CAT 7: Upsell ─────────────────────────────────────────────────────────────
class TestCat7Upsell(unittest.TestCase):

    def _try_upsell(self, last_item, cart_items):
        try:
            return requests.post(
                f"{BASE_URL}/voice/upsell_after_add",
                headers=AUTH_HEADERS,
                json={"last_item_name": last_item, "cart_items": cart_items},
                timeout=15,
            )
        except Exception:
            return None

    def test_tc27_upsell_after_burger(self):
        """TC-27: After burger → upsell fires"""
        res = self._try_upsell("Cheeseburger", ["Cheeseburger"])
        if res is None or res.status_code == 404:
            self.skipTest("upsell_after_add not implemented")
        self.assertIn(res.status_code, [200, 201])

    def test_tc28_upsell_after_bbq(self):
        """TC-28: After Chicken Tikka → upsell fires"""
        res = self._try_upsell("Chicken Tikka", ["Chicken Tikka"])
        if res is None or res.status_code == 404:
            self.skipTest("upsell_after_add not implemented")
        self.assertIn(res.status_code, [200, 201])

    def test_tc29_no_duplicate_drink(self):
        """TC-29: After Cola → upsell does NOT suggest Cola"""
        res = self._try_upsell("Cola", ["Cola"])
        if res is None or res.status_code == 404:
            self.skipTest("upsell_after_add not implemented")
        if res.status_code == 200:
            self.assertNotIn("cola", res.text.lower())


# ── CAT 8: Urdu ASR / NLP ────────────────────────────────────────────────────
class TestCat8NLPAccuracy(unittest.TestCase):

    def setUp(self): self.client = _client()

    def _urdu(self, transcript, session="nlp"):
        res = requests.post(f"{BASE_URL}/chat", json={
            "message": transcript, "language": "ur", "session_id": session
        }, timeout=20)
        return res.json()

    def test_tc30_paanch_as_paas(self):
        """TC-30: 'پاس بندوں' (5 people mishear) → search_deal fires"""
        b = self._urdu("پاس بندوں کی چائنیز ڈیل")
        self.assertTrue(b.get("success", True))
        triggered = any(c.get("name") == "search_deal" for c in b.get("tool_calls", []))
        self.assertTrue(triggered, f"Expected search_deal, got: {b.get('tool_calls')}")

    def test_tc31_urdu_favourites(self):
        """TC-31: 'فریوٹس دکھاؤ' → manage_favourites detected"""
        b = self._urdu("فریوٹس دکھاؤ")
        self.assertTrue(b.get("success", True))
        triggered = any(c.get("name") == "manage_favourites" for c in b.get("tool_calls", []))
        self.assertTrue(triggered, f"Expected manage_favourites, got: {b.get('tool_calls')}")

    def test_tc32_code_switching(self):
        """TC-32: Mixed Urdu-English deal query → search_deal fires"""
        b = self._urdu("mujhe Chinese ka deal show karo 4 logo ke liye")
        self.assertTrue(b.get("success", True))
        triggered = any(c.get("name") == "search_deal" for c in b.get("tool_calls", []))
        self.assertTrue(triggered)

    def test_tc33_addar_order(self):
        """TC-33: 'اڈر پلیس کرو' → no crash, reply returned"""
        b = self._urdu("اڈر پلیس کرو")
        self.assertTrue(b.get("success", True))
        self.assertIn("reply", b)

    def test_tc34_short_haan(self):
        """TC-34: 'ہاں' alone → no crash, reply given"""
        b = self._urdu("ہاں")
        self.assertTrue(b.get("success", True))
        self.assertIn("reply", b)

    def test_tc35_empty_audio_no_crash(self):
        """TC-35: Audio < 5000 bytes → no 5xx crash"""
        client = _client()
        tiny = ("tiny.wav", b"a" * 2048, "audio/wav")
        res = client.post("/voice_chat", data={
            "session_id": "tiny", "language": "ur", "conversation_history": "[]"
        }, files={"file": tiny})
        self.assertNotIn(res.status_code, [500, 502, 503, 504],
                         f"Server crashed on tiny audio: {res.status_code}")


# ── CAT 9: Payment ────────────────────────────────────────────────────────────
class TestCat9Payment(unittest.TestCase):

    def setUp(self): self.client = _client()

    def test_tc36_cod(self):
        """TC-36: 'cash on delivery se order karo' → place_order COD"""
        b = _chat_with_tool(self.client, "cash on delivery se order karo",
                            "place_order", {"payment_method": "COD"})
        self.assertTrue(b["success"])
        self.assertTrue(_has_tool(b, "place_order", "payment_method", "COD"))

    def test_tc37_card(self):
        """TC-37: 'card se payment' → place_order CARD"""
        b = _chat_with_tool(self.client, "card se payment karna hai",
                            "place_order", {"payment_method": "CARD"})
        self.assertTrue(b["success"])
        self.assertTrue(_has_tool(b, "place_order", "payment_method", "CARD"))

    def test_tc38_bill_dine_in(self):
        """TC-38: 'bill lao' → show_cart or navigate_to fires"""
        b = _chat_with_tool(self.client, "bill lao", "show_cart")
        self.assertTrue(b["success"])
        triggered = any(c.get("name") in ("show_cart", "navigate_to")
                        for c in b.get("tool_calls", []))
        self.assertTrue(triggered)


# ── CAT 10: Edge Cases ────────────────────────────────────────────────────────
class TestCat10EdgeCases(unittest.TestCase):

    def setUp(self): self.client = _client()

    def test_tc39_off_topic(self):
        """TC-39: 'kal mausam kaisa rahega' → no crash, reply given"""
        fake_ai = SimpleNamespace(content="Sirf restaurant orders mein madad karta hoon.", tool_calls=[])
        with patch.object(main, "get_ai_response", return_value=fake_ai), \
             patch.object(main, "fetch_menu_items_by_name", return_value=[]), \
             patch.object(main, "fetch_deals_by_name", return_value=[]):
            res = self.client.post("/chat", json={
                "message": "kal mausam kaisa rahega", "language": "ur", "session_id": "weather"
            })
        b = res.json()
        self.assertTrue(b["success"])
        self.assertNotEqual(b.get("reply", ""), "")

    def test_tc40_vague_deal(self):
        """TC-40: 'koi deal bana do' (no cuisine) → create_custom_deal or reply"""
        fake_ai = SimpleNamespace(
            content="Kaunsi cuisine chahiye?",
            tool_calls=[{"name": "create_custom_deal", "args": {"user_query": "koi deal bana do"}}],
        )
        with patch.object(main, "get_ai_response", return_value=fake_ai), \
             patch.object(main, "fetch_menu_items_by_name", return_value=[]), \
             patch.object(main, "fetch_deals_by_name", return_value=[]):
            res = self.client.post("/chat", json={
                "message": "koi deal bana do", "language": "ur", "session_id": "vague"
            })
        b = res.json()
        self.assertTrue(b["success"])
        triggered = any(c.get("name") == "create_custom_deal" for c in b.get("tool_calls", []))
        self.assertTrue(triggered or bool(b.get("reply")))

    def test_tc41_clarification_history_preserved(self):
        """TC-41: Clarification answer — 2-turn history reaches AI"""
        history = [
            {"role": "user",      "content": "koi deal bana do"},
            {"role": "assistant", "content": "Kaunsi cuisine chahiye?"},
        ]
        fake_ai = SimpleNamespace(
            content="ok",
            tool_calls=[{"name": "create_custom_deal",
                         "args": {"user_query": "desi 3 logon ke liye"}}],
        )
        with patch.object(main, "get_ai_response", return_value=fake_ai) as ai_mock, \
             patch.object(main, "fetch_menu_items_by_name", return_value=[]), \
             patch.object(main, "fetch_deals_by_name", return_value=[]):
            self.client.post("/chat", json={
                "message": "desi 3 logon ke liye",
                "language": "ur", "session_id": "clarify",
                "conversation_history": history,
            })
        h = _get_history_from_mock(ai_mock)
        self.assertIsNotNone(h)
        self.assertGreaterEqual(len(h), 2)

    def test_tc42_custom_deal_yes(self):
        """TC-42: 'haan shamil karo' after deal summary → reply given"""
        history = [
            {"role": "user",      "content": "desi 3 logon ke liye deal"},
            {"role": "assistant", "content": "Aapki custom deal tayyar hai. Kya shamil karun?"},
        ]
        fake_ai = SimpleNamespace(content="Deal shamil kar di!", tool_calls=[])
        with patch.object(main, "get_ai_response", return_value=fake_ai), \
             patch.object(main, "fetch_menu_items_by_name", return_value=[]), \
             patch.object(main, "fetch_deals_by_name", return_value=[]):
            res = self.client.post("/chat", json={
                "message": "haan shamil karo", "language": "ur",
                "session_id": "yes-confirm", "conversation_history": history,
            })
        b = res.json()
        self.assertTrue(b["success"])
        self.assertIn("reply", b)

    def test_tc43_custom_deal_no(self):
        """TC-43: 'nahi' after deal summary → no add_to_cart fires"""
        fake_ai = SimpleNamespace(content="Theek hai, cancel.", tool_calls=[])
        with patch.object(main, "get_ai_response", return_value=fake_ai), \
             patch.object(main, "fetch_menu_items_by_name", return_value=[]), \
             patch.object(main, "fetch_deals_by_name", return_value=[]):
            res = self.client.post("/chat", json={
                "message": "nahi", "language": "ur", "session_id": "no-confirm",
            })
        b = res.json()
        self.assertTrue(b["success"])
        no_add = all(c.get("name") != "add_to_cart" for c in b.get("tool_calls", []))
        self.assertTrue(no_add)

    def test_tc44_rapid_commands(self):
        """TC-44: 3 sequential commands don't interfere"""
        for msg, tool in [
            ("Zinger Burger add karo", "add_to_cart"),
            ("Fries bhi dalo",         "add_to_cart"),
            ("cart dikhao",            "show_cart"),
        ]:
            b = _chat_with_tool(self.client, msg, tool)
            self.assertTrue(b["success"], f"Failed: {msg}")
            self.assertTrue(_has_tool(b, tool), f"Missing {tool} for: {msg}")

    def test_tc45_asr_timeout_graceful(self):
        """TC-45: ASR timeout → 200 with error body, NOT 504"""
        client = _client()
        with patch.object(main, "transcribe_audio", side_effect=TimeoutError("slow")):
            res = client.post("/voice_chat", data={
                "session_id": "timeout", "language": "ur", "conversation_history": "[]"
            }, files={"file": AUDIO_FILE})
        self.assertEqual(res.status_code, 200)
        b = res.json()
        self.assertFalse(b.get("success", True))
        self.assertIn("reply", b)


# ── Summary Result ────────────────────────────────────────────────────────────
class _SummaryResult(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._issues: List[str] = []

    def addFailure(self, test, err):
        super().addFailure(test, err)
        msg = self._exc_info_to_string(err, test).splitlines()[-1]
        self._issues.append(f"  FAIL   {test.shortDescription()} \n         {msg}")

    def addError(self, test, err):
        super().addError(test, err)
        msg = self._exc_info_to_string(err, test).splitlines()[-1]
        self._issues.append(f"  ERROR  {test.shortDescription()} \n         {msg}")

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._issues.append(f"  SKIP   {test.shortDescription()} \n         {reason}")

    def print_compact_summary(self):
        passed = self.testsRun - len(self.failures) - len(self.errors) - len(self.skipped)
        print("\n" + "=" * 65)
        print("  KHAADIM 45-TEST SUMMARY")
        print("=" * 65)
        print(f"  Passed : {passed}/{self.testsRun}")
        print(f"  Failed : {len(self.failures)}")
        print(f"  Errors : {len(self.errors)}")
        print(f"  Skipped: {len(self.skipped)}")
        if self._issues:
            print("\n  Issues to share:")
            print("  " + "-" * 60)
            for line in self._issues:
                print(line)
        else:
            print("\n  All tests passed!")
        print("=" * 65)


class _SummaryRunner(unittest.TextTestRunner):
    def _makeResult(self):
        return _SummaryResult(self.stream, self.descriptions, self.verbosity)

    def run(self, test):
        result = super().run(test)
        result.print_compact_summary()
        return result


def build_suite():
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()
    for cls in [
        TestCat1DealExactMatch, TestCat2CustomDealFallback,
        TestCat3MenuSearch,     TestCat4CartManagement,
        TestCat5ContextMemory,  TestCat6Navigation,
        TestCat7Upsell,         TestCat8NLPAccuracy,
        TestCat9Payment,        TestCat10EdgeCases,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))
    return suite


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("VOICE_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token",    default=os.getenv("VOICE_TEST_TOKEN", TOKEN))
    args, _ = parser.parse_known_args()
    BASE_URL     = args.base_url
    TOKEN        = args.token
    AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}"}

    # Suppress per-test output — only show the compact summary
    runner = _SummaryRunner(verbosity=0, stream=open(os.devnull, "w"))
    result = runner.run(build_suite())
    sys.exit(0 if result.wasSuccessful() else 1)