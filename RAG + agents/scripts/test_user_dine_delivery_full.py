#!/usr/bin/env python3
"""
Full user-simulation tests: behave as a *delivery customer* and as a *dine-in customer*,
for **every** menu item and **every** deal returned by the API.

Uses GET /menu and GET /deals (no DB client). Each row gets natural Roman/Urdu-style
phrases — not robotic "{name} add".

Examples:
  python scripts/test_user_dine_delivery_full.py
  python scripts/test_user_dine_delivery_full.py --deals-only --delay 2
  python scripts/test_user_dine_delivery_full.py --delivery-only --max-items 10
  python scripts/test_user_dine_delivery_full.py --dine-only --quiet

Counts (49 items × 2 contexts + 20 deals × 2 contexts) ≈ 138 /chat calls — use --delay
to avoid Groq rate limits.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install: pip install requests", file=sys.stderr)
    raise SystemExit(1)


def _ensure_utf8_stdio() -> None:
    """Avoid UnicodeEncodeError on Windows consoles when printing Urdu replies."""
    for stream in (sys.stdout, sys.stderr):
        if not hasattr(stream, "reconfigure"):
            continue
        enc = getattr(stream, "encoding", None) or ""
        if enc.lower() == "utf-8":
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_BASE = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("API_TOKEN", "").strip()

# Customer voice templates — {name} = exact menu_item.item_name or deal.deal_name
DELIVERY_ITEM_PHRASES: list[str] = [
    "Home delivery ke liye {name} cart mein add karo.",
    "Ghar par mangwana hai — {name} order mein dal do cart.",
    "Deliver karo, {name} bhi cart mein shamil karo COD wale order ke liye.",
]

DINE_IN_ITEM_PHRASES: list[str] = [
    "Yahan restaurant table pe baith ke {name} cart mein add karo.",
    "Dine in hun, {name} apni tray mein add kar do cart.",
    "Kiosk se order — {name} include karo cart mein, abhi yahi khaoonga.",
]

DELIVERY_DEAL_PHRASES: list[str] = [
    "Ghar deliver karwana hai, {name} deal dikhao options.",
    "Home delivery ke liye {name} wala package kya price pe hai dikhao.",
]

DINE_IN_DEAL_PHRASES: list[str] = [
    "Yahan hall mein bethe hain — {name} deal table ke liye dikhao.",
    "Restaurant mein dine in {name} deal available hai? Dikhao.",
]


def _headers_json() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def post_chat(base: str, session_id: str, message: str, lang: str = "ur") -> dict:
    r = requests.post(
        f"{base}/chat",
        headers=_headers_json(),
        json={"session_id": session_id, "message": message, "language": lang},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()


def get_json(base: str, path: str) -> dict:
    r = requests.get(f"{base}{path}", headers=_headers_json(), timeout=60)
    r.raise_for_status()
    return r.json()


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def _collect_add_names(payload: dict) -> list[str]:
    out: list[str] = []
    for c in payload.get("tool_calls") or []:
        if (c.get("name") or "").strip().lower() != "add_to_cart":
            continue
        args = c.get("args") or {}
        n = (args.get("item_name") or "").strip()
        if n:
            out.append(n)
    return out


def _names_match(expected: str, resolved: str) -> bool:
    e, r = _norm(expected), _norm(resolved)
    if not e or not r:
        return False
    return e == r or e in r or r in e


def _tool_names(payload: dict) -> list[str]:
    return [str((c or {}).get("name") or "") for c in (payload.get("tool_calls") or [])]


def _ping(base: str) -> None:
    try:
        r = requests.get(f"{base}/docs", timeout=5)
        print(f"  (health: GET /docs -> {r.status_code})")
    except Exception as e:
        print(f"  WARNING: cannot reach API: {e}")


def run_menu_user_simulation(
    base: str,
    lang: str,
    delay: float,
    *,
    do_delivery: bool,
    do_dine: bool,
    max_items: int | None,
    quiet: bool,
) -> tuple[int, int]:
    data = get_json(base, "/menu")
    menu = data.get("menu") or []
    if not menu:
        print("GET /menu empty", file=sys.stderr)
        return 0, 1
    ok, failed = 0, 0
    n = 0
    for row in menu:
        if max_items is not None and n >= max_items:
            break
        iid = row.get("item_id")
        name = (row.get("item_name") or "").strip()
        if not name:
            failed += 1
            n += 1
            if not quiet:
                print(f"  BAD  item_id={iid} empty name")
            continue

        if do_delivery:
            phrase = DELIVERY_ITEM_PHRASES[n % len(DELIVERY_ITEM_PHRASES)].format(name=name)
            sid = f"usr_del_{uuid.uuid4().hex[:10]}"
            label = f"DEL-ITEM id={iid}"
            try:
                out = post_chat(base, sid, phrase, lang)
                adds = _collect_add_names(out)
                hit = any(_names_match(name, x) for x in adds)
                if hit and out.get("success"):
                    ok += 1
                    if not quiet:
                        print(f"  OK   {label}  {name[:42]}")
                else:
                    failed += 1
                    print(
                        f"  FAIL {label}  {name[:40]}  phrase={phrase[:55]!r}  "
                        f"adds={adds!r}  tools={_tool_names(out)}"
                    )
            except Exception as e:
                failed += 1
                print(f"  FAIL {label} {name[:35]}: {e}")
            if delay > 0:
                time.sleep(delay)

        if do_dine:
            phrase = DINE_IN_ITEM_PHRASES[n % len(DINE_IN_ITEM_PHRASES)].format(name=name)
            sid = f"usr_din_{uuid.uuid4().hex[:10]}"
            label = f"DIN-ITEM id={iid}"
            try:
                out = post_chat(base, sid, phrase, lang)
                adds = _collect_add_names(out)
                hit = any(_names_match(name, x) for x in adds)
                if hit and out.get("success"):
                    ok += 1
                    if not quiet:
                        print(f"  OK   {label}  {name[:42]}")
                else:
                    failed += 1
                    print(
                        f"  FAIL {label}  {name[:40]}  phrase={phrase[:55]!r}  "
                        f"adds={adds!r}  tools={_tool_names(out)}"
                    )
            except Exception as e:
                failed += 1
                print(f"  FAIL {label} {name[:35]}: {e}")
            if delay > 0:
                time.sleep(delay)

        n += 1
    return ok, failed


def run_deal_user_simulation(
    base: str,
    lang: str,
    delay: float,
    *,
    do_delivery: bool,
    do_dine: bool,
    max_deals: int | None,
    quiet: bool,
) -> tuple[int, int]:
    data = get_json(base, "/deals")
    deals = data.get("deals") or []
    if not deals:
        print("GET /deals empty", file=sys.stderr)
        return 0, 1
    ok, failed = 0, 0
    n = 0
    for row in deals:
        if max_deals is not None and n >= max_deals:
            break
        did = row.get("deal_id")
        name = (row.get("deal_name") or "").strip()
        if not name:
            failed += 1
            n += 1
            continue

        if do_delivery:
            phrase = DELIVERY_DEAL_PHRASES[n % len(DELIVERY_DEAL_PHRASES)].format(name=name)
            sid = f"usr_deld_{uuid.uuid4().hex[:10]}"
            label = f"DEL-DEAL id={did}"
            try:
                out = post_chat(base, sid, phrase, lang)
                tools = _tool_names(out)
                good = "search_deal" in tools or "search_menu" in tools
                if good and out.get("success") is not False:
                    ok += 1
                    if not quiet:
                        print(f"  OK   {label}  {name[:45]}")
                else:
                    failed += 1
                    print(
                        f"  FAIL {label}  {name[:38]}  phrase={phrase[:60]!r}  "
                        f"tools={tools}  reply={(out.get('reply') or '')[:80]!r}"
                    )
            except Exception as e:
                failed += 1
                print(f"  FAIL {label} {name[:35]}: {e}")
            if delay > 0:
                time.sleep(delay)

        if do_dine:
            phrase = DINE_IN_DEAL_PHRASES[n % len(DINE_IN_DEAL_PHRASES)].format(name=name)
            sid = f"usr_dind_{uuid.uuid4().hex[:10]}"
            label = f"DIN-DEAL id={did}"
            try:
                out = post_chat(base, sid, phrase, lang)
                tools = _tool_names(out)
                good = "search_deal" in tools or "search_menu" in tools
                if good and out.get("success") is not False:
                    ok += 1
                    if not quiet:
                        print(f"  OK   {label}  {name[:45]}")
                else:
                    failed += 1
                    print(
                        f"  FAIL {label}  {name[:38]}  phrase={phrase[:60]!r}  "
                        f"tools={tools}"
                    )
            except Exception as e:
                failed += 1
                print(f"  FAIL {label} {name[:35]}: {e}")
            if delay > 0:
                time.sleep(delay)

        n += 1
    return ok, failed


def main() -> None:
    _ensure_utf8_stdio()
    ap = argparse.ArgumentParser(
        description="Simulate delivery + dine-in users for every menu item and deal",
    )
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--lang", default="ur", choices=["ur", "en"])
    ap.add_argument("--delay", type=float, default=1.5, help="Pause between /chat calls (Groq)")
    ap.add_argument("--menu-only", action="store_true", help="Only menu items (both contexts unless scoped)")
    ap.add_argument("--deals-only", action="store_true", help="Only deals")
    ap.add_argument(
        "--delivery-only",
        action="store_true",
        help="Only 'delivery customer' phrases",
    )
    ap.add_argument(
        "--dine-only",
        action="store_true",
        help="Only 'dine-in customer' phrases",
    )
    ap.add_argument("--max-items", type=int, default=None)
    ap.add_argument("--max-deals", type=int, default=None)
    ap.add_argument("--quiet", action="store_true", help="Print failures only for menu ok lines")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    do_delivery = not args.dine_only
    do_dine = not args.delivery_only
    if args.delivery_only and args.dine_only:
        print("Cannot combine --delivery-only with --dine-only", file=sys.stderr)
        raise SystemExit(2)

    do_menu = not args.deals_only
    do_deals = not args.menu_only
    if args.menu_only and args.deals_only:
        print("Nothing to run with both --menu-only and --deals-only", file=sys.stderr)
        raise SystemExit(2)

    print(f"API: {base}")
    print(
        f"Contexts: delivery={do_delivery}  dine-in={do_dine}  "
        f"menu={do_menu}  deals={do_deals}"
    )
    _ping(base)

    total_ok = 0
    total_bad = 0

    if do_menu:
        print("\n=== MENU ITEMS (user phrases: home delivery vs dine-in) ===\n")
        ok, bad = run_menu_user_simulation(
            base,
            args.lang,
            args.delay,
            do_delivery=do_delivery,
            do_dine=do_dine,
            max_items=args.max_items,
            quiet=args.quiet,
        )
        total_ok += ok
        total_bad += bad
        print(f"\n  menu simulation: ok={ok} failed={bad}")

    if do_deals:
        print("\n=== DEALS (user phrases: delivery browse vs dine-in browse) ===\n")
        ok, bad = run_deal_user_simulation(
            base,
            args.lang,
            args.delay,
            do_delivery=do_delivery,
            do_dine=do_dine,
            max_deals=args.max_deals,
            quiet=args.quiet,
        )
        total_ok += ok
        total_bad += bad
        print(f"\n  deal simulation: ok={ok} failed={bad}")

    print("\n" + "-" * 72)
    print(f"  TOTAL ok={total_ok}  failed={total_bad}")
    if total_bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
