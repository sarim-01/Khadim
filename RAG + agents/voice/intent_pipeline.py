"""
Restaurant voice / chat tool-call pipeline (dine-in & delivery).

Problem
-------
Guests combine many intents in one utterance. Speech order is not kitchen order:
e.g. "Place order … burger add … cola add" must execute adds first, then checkout.

Design
------
1. **Single-intent vocabulary** (atomic tools the LLM / determiners emit):

   - **Discover**: search_menu, search_deal, retrieve_menu_context, get_recommendations,
     create_custom_deal, navigate_to, call_waiter, get_order_status, weather_upsell
   - **Cart**: clear_cart, remove_from_cart, change_quantity, add_to_cart, show_cart
   - **Commit**: place_order (kitchen / checkout), settle_payment (in-app payment UX)

2. **Permutations** — Any list of tool calls is a candidate; we do not enumerate all
   exponential combinations. We **filter** with:

   - Payment coherence: at most one logical payment resolution per turn.
   - Phase ordering: discover → cart hygiene (remove → adjust → add → review) → commit.

3. **Does it make sense?**
   - Contradictory payment (card + cash/COD in the same breath) → collapse to **ask**.
   - `place_order` / `settle_payment` always **after** cart-building steps in the same turn.

This matches typical flow:

* **Dine-in kiosk**: browse → add to cart → optionally show cart → confirm → pay (card vs cash
  once) → kitchen.
* **Delivery**: same, with COD explicitly as cash-on-delivery instead of counter cash.

The module only **reorders and normalizes args**; execution stays in ``main.py``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

# --- Phase buckets (lower = earlier) -----------------------------------------

_DISCOVERY: Set[str] = {
    "search_menu",
    "search_deal",
    "retrieve_menu_context",
    "get_recommendations",
    "create_custom_deal",
    "navigate_to",
    "call_waiter",
    "get_order_status",
    "weather_upsell",
}

_CART_ORDER: Dict[str, int] = {
    "clear_cart": -1,
    "remove_from_cart": 0,
    "change_quantity": 1,
    "add_to_cart": 2,
    "show_cart": 3,
}

_COMMIT: Set[str] = {"place_order", "settle_payment"}


def _tool_name(call: Dict[str, Any]) -> str:
    return str((call or {}).get("name") or "").strip().lower()


def _norm_settle_method(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s in ("card", "credit", "debit"):
        return "card"
    if s in ("cash", "cod", "naqd", "naqad"):
        return "cash"
    if s in ("ask", "", "?") or s == "none":
        return "ask"
    return s


def _norm_place_order_method(raw: str) -> str:
    s = (raw or "").strip().upper()
    if s in ("CARD", "CREDIT", "DEBIT"):
        return "CARD"
    if s in ("COD", "CASH"):
        return "COD"
    if s in ("ASK", "", "?"):
        return "ASK"
    return s


def reconcile_payment_conflicts(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """If both card-like and cash-like payment appear, force a single ambiguous method.

    One coherent disposition per turn; client / TTS can ask 'card or cash?'.
    """
    if not calls:
        return calls

    card_hit = False
    cash_hit = False
    for c in calls:
        n = _tool_name(c)
        args = dict((c or {}).get("args") or {})
        if n == "settle_payment":
            m = _norm_settle_method(str(args.get("payment_method") or ""))
            if m == "card":
                card_hit = True
            elif m == "cash":
                cash_hit = True
        elif n == "place_order":
            m = _norm_place_order_method(str(args.get("payment_method") or ""))
            if m == "CARD":
                card_hit = True
            elif m == "COD":
                cash_hit = True

    if not (card_hit and cash_hit):
        return calls

    out: List[Dict[str, Any]] = []
    for c in calls:
        n = _tool_name(c)
        args = dict((c or {}).get("args") or {})
        if n == "settle_payment":
            args["payment_method"] = "ask"
        elif n == "place_order":
            args["payment_method"] = "ASK"
        out.append({"name": n, "args": args})
    return out


def plan_restaurant_tool_calls(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reorder tool calls into a restaurant-realistic pipeline for one user turn.

    Rules:
      1. Reconcile conflicting payment methods (card vs cash/COD).
      2. ``place_order`` / ``settle_payment`` always last (checkout after building cart).
      3. Discovery / info tools first (stable relative order among them).
      4. Cart ops: remove → change_quantity → add_to_cart → show_cart (logical edit order).
      5. Unknown tools keep their relative position in the pre-commit block.
    """
    calls = [c for c in (calls or []) if c]
    if not calls:
        return calls

    calls = reconcile_payment_conflicts(calls)

    commit = [c for c in calls if _tool_name(c) in _COMMIT]
    non_commit = [c for c in calls if _tool_name(c) not in _COMMIT]

    discovery: List[Dict[str, Any]] = []
    cart_ops: List[Dict[str, Any]] = []
    other: List[Dict[str, Any]] = []

    for c in non_commit:
        n = _tool_name(c)
        if n in _DISCOVERY:
            discovery.append(c)
        elif n in _CART_ORDER:
            cart_ops.append(c)
        else:
            other.append(c)

    cart_ops.sort(key=lambda x: _CART_ORDER.get(_tool_name(x), 99))

    # Browse / misc first, then cart mutations (items land before implicit checkout).
    ordered = discovery + other + cart_ops + commit
    return ordered


def explain_pipeline_summary() -> str:
    """Human-readable one-page summary for operators / future LLM prompts."""
    return __doc__ or ""
