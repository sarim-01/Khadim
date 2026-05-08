#!/usr/bin/env python3
"""
Offline unit tests for voice routing heuristics (no API, no Redis, no DB).

  python scripts/test_cart_voice_heuristics.py

Covers deterministic precursors used by /chat and /voice_chat for BOTH
delivery and dine-in kiosk (same server routing).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from voice.cart_voice_heuristics import (  # noqa: E402
    wants_clear_entire_cart,
    text_requests_order_tracking,
)


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> None:
    # --- clear cart ---
    _check(wants_clear_entire_cart("cart میں سے سارے item remove kar 2"),
           "Urdu+Latin cart clear phrase")
    _check(wants_clear_entire_cart("clear cart"), "clear cart")
    _check(wants_clear_entire_cart("empty cart"), "empty cart")
    _check(wants_clear_entire_cart("Cart se sab items remove kar do"), "roman clear")
    _check(wants_clear_entire_cart("poora cart khali kar do"), "khali cart")
    _check(
        wants_clear_entire_cart(
            "Cart se saari cheezen remove karo poora empty kar do."
        ),
        "M8 Roman clear phrase",
    )
    _check(wants_clear_entire_cart("کارڈ خالی کر دو"), "card typo empty")
    _check(
        not wants_clear_entire_cart("zinger burger cart mein add karo"),
        "add-to-cart must not clear",
    )

    # --- order tracking ---
    _check(text_requests_order_tracking("Mera order kahan hai?"), "kahan")
    _check(text_requests_order_tracking("What is the status of my order?"), "english status")
    _check(text_requests_order_tracking("mere order ki kya progress hai"),
           "progress")
    _check(text_requests_order_tracking("my order track kr ke batao"), "track")
    _check(
        text_requests_order_tracking("آرڈر میں کتنا ٹائم ہے؟"),
        "urdu eta",
    )
    _check(
        not text_requests_order_tracking("chinese menu dikhao"),
        "menu browse not tracking",
    )

    print("OK  voice/cart_voice_heuristics.py  (all checks passed)")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("FAIL:", e, file=sys.stderr)
        raise SystemExit(1)
