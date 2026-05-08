"""
Cart + order-tracking heuristics for voice / chat deterministic routing.

Used by both dine-in (kiosk) and delivery — identical server-side logic.
Keeps behavior testable without importing the full FastAPI app stack.
"""

from __future__ import annotations

import re


def wants_clear_entire_cart(text: str) -> bool:
    """Whole-cart clear: beats NLP search_menu false positives on Urdu phrasing."""
    if not (text or "").strip():
        return False
    t = text.strip()
    low = t.lower()
    compact = re.sub(r"\s+", "", low)

    if re.search(r"\bclear\s+cart\b", low) or re.search(r"\bempty\s+cart\b", low):
        return True
    if "clearcart" in compact or "emptycart" in compact or "cartclear" in compact:
        return True
    if re.search(r"\bremove\s+all\b", low) and ("cart" in low or "کارٹ" in t):
        return True

    cart_hits = ("cart" in low) or ("کارٹ" in t)
    all_markers = (
        "sab ",
        " saab",
        "saari",
        " saari",
        " saare",
        "saare",
        "sare",
        "saray",
        "sari ",
        "sara ",
        "saara",
        " saara",
        " سارے",
        "سارے",
        "سارا",
        " سارا",
        "سب",
        "tamam",
        "تمام",
        "remove all",
        "delete all",
    )
    has_all = (
        re.search(r"\ball\s+items?\b", low) is not None
        or re.search(r"\bitems?\s+all\b", low) is not None
        or any(m in low or m in t for m in all_markers)
    )
    verbs = (
        "remove",
        "حذف",
        "nikal",
        "hata",
        "خالی",
        "khali",
        "empty",
        "clear",
        "delete",
        "kar do",
        "kardo",
        "krdo",
        "ریمو",
    )
    has_verb = any(v in low or v in t for v in verbs)
    if cart_hits and has_all and has_verb:
        return True

    # "Mera cart bilkul khali kar do" should clear even without explicit "all".
    if cart_hits and ("خالی" in t or "khali" in low or "empty" in low):
        if any(
            k in low
            for k in ("kar do", "kar 2", "kardo", "krdo", "clear", "empty", "remove")
        ):
            return True

    if re.search(r"\b(poora|pura|poori|sara|saara)\s+cart\b", low) and any(
        k in low for k in ("khali", "empty", "clear", "خالی")
    ):
        return True

    if (
        "کارڈ" in t
        or ("card" in low and "credit" not in low and "debit" not in low)
    ) and ("خالی" in t or "khali" in low or "empty" in low):
        if not any(k in low for k in ("payment", "پیمنٹ", "pay bill", "card pay")):
            return True

    return False


def text_requests_order_tracking(t: str) -> bool:
    """Rough match for ETA / track / progress (normalised English or mixed)."""
    if not (t or "").strip():
        return False
    raw = t.strip()
    low = raw.lower()
    needles = (
        "where is my order",
        "order status",
        "status of my order",
        "track my order",
        "track order",
        "order tracking",
        "mera order kahan",
        "mera order track",
        "mere order ki",
        "mere order ki kya progress",
        "delivery time",
        "time left",
        "how long",
        "how much time",
        "kitna time",
        "kitni dair",
        "order mein kitni dair",
        "order me kitni dair",
        "order kidhar",
        "order kab",
        "order pata",
        "eta ",
        " eta",
        "progress",
        "my order track",
        "order ki kya progress",
        "how much time is left",
    )
    if any(n in low for n in needles):
        return True
    orderish = ("order" in low) or any(
        x in raw
        for x in ("آرڈر", "اڈر", "آڈر", "میرا order", "میرے order")
    )
    if not orderish:
        return False
    statusish = any(
        x in low or x in raw
        for x in (
            "track",
            "progress",
            "status",
            "time",
            "waqt",
            "dair",
            "دیر",
            "کتنا",
            " ٹائم",
            "ٹائم",
            "وقت",
        )
    )
    return statusish
