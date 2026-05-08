#!/usr/bin/env python3
"""
End-to-end API checks for (1) *complex* multi-step / mixed-language phrases and
(2) optional *full menu* sweep: one /chat per item to catch bad resolution.

Requires API running (default API_BASE_URL). Uses GET /menu — no DB driver needed.

For **every** menu row + every deal as a *delivery vs dine-in user*, run:
  python scripts/test_user_dine_delivery_full.py

Usage:
  python scripts/test_menu_and_complex_scenarios.py
  python scripts/test_menu_and_complex_scenarios.py --skip-complex
  python scripts/test_menu_and_complex_scenarios.py --all-items --delay 1.5
  python scripts/test_menu_and_complex_scenarios.py --all-items --max-items 10
  python scripts/test_menu_and_complex_scenarios.py --deal-smoke --delay 2
"""
from __future__ import annotations

import argparse
import json
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

# Multi-intent / multi-item / high-churn phrases (IDs for --only).
COMPLEX_CASES: list[tuple[str, str, str]] = [
    (
        "C1",
        "ek kung pao, ek sweet and sour, aur ek zinger burger cart mein add karo",
        "Triple add (Roman Urdu + English dish names)",
    ),
    (
        "C2",
        "ایک kung pao، ایک sweet and sour اور ایک zinger burger cart میں add کر دو",
        "Triple add mixed Urdu script + Latin (kiosk pattern)",
    ),
    (
        "C3",
        "Chinese menu dikhao, phir vegetable spring rolls aur cola cart mein add karo.",
        "Search menu + two adds",
    ),
    (
        "C4",
        "Pehle beef biryani hatao phir chicken karahi cart mein add karo.",
        "Remove then add (repair-style)",
    ),
    (
        "C5",
        "Home delivery BBQ deals for 4 log dikhao, phir malai boti 2 add, cart dikhao.",
        "Deal browse + quantity + show cart",
    ),
    (
        "C6",
        "Place order card se bhi aur COD se bhi — ek hi payment batao.",
        "Payment conflict -> ask single method (delivery framing)",
    ),
    (
        "C7",
        "Fast food deals 2 bando ke liye dikhao, phir fast duo confirm karo nahi sirf zinger burger add karo.",
        "Deal distraction vs explicit single-item add",
    ),
    (
        "C8",
        "Chinese deals dikhao, spring rolls add karo, phir place order COD se.",
        "Deal discovery + item + checkout",
    ),
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


def _names_match(expected_menu_name: str, resolved: str) -> bool:
    e, r = _norm(expected_menu_name), _norm(resolved)
    if not e or not r:
        return False
    return e == r or e in r or r in e


def print_case(case_id: str, note: str, payload: dict) -> None:
    print("\n" + "=" * 72)
    print(f"  [{case_id}]  {note}")
    print("=" * 72)
    print("  success:", payload.get("success"))
    print("  reply:", (payload.get("reply") or "")[:420])
    tc = payload.get("tool_calls") or []
    print("  tool_calls:", json.dumps(tc, ensure_ascii=False)[:900])
    nlp = payload.get("nlp") or {}
    print("  nlp.intent:", nlp.get("intent"))


def run_complex(base: str, lang: str, delay: float, only: set[str]) -> tuple[int, int]:
    failed = 0
    ok = 0
    sid = f"qa_complex_{uuid.uuid4().hex[:10]}"
    cases = COMPLEX_CASES
    if only:
        cases = [c for c in COMPLEX_CASES if c[0] in only]
    for case_id, phrase, note in cases:
        try:
            out = post_chat(base, sid, phrase, lang)
            print_case(case_id, note, out)
            ok += 1
        except Exception as e:
            print(f"\n[{case_id}] FAIL: {e}")
            failed += 1
        if delay > 0:
            time.sleep(delay)
    return ok, failed


def run_all_menu_items(
    base: str,
    lang: str,
    delay: float,
    max_items: int | None,
) -> tuple[int, int]:
    data = get_json(base, "/menu")
    menu = data.get("menu") or []
    if not menu:
        print("GET /menu returned empty menu", file=sys.stderr)
        return 0, 1
    ok, failed = 0, 0
    sid = f"qa_menu_{uuid.uuid4().hex[:10]}"
    print(f"\n--- All menu items ({len(menu)} rows) — add resolution ---\n")
    n_run = 0
    for row in menu:
        if max_items is not None and n_run >= max_items:
            break
        iid = row.get("item_id")
        name = (row.get("item_name") or "").strip()
        if not name:
            failed += 1
            print(f"  [skip] item_id={iid} empty name")
            continue
        phrase = f"{name} cart mein add karo"
        try:
            out = post_chat(base, sid, phrase, lang)
            adds = _collect_add_names(out)
            hit = any(_names_match(name, x) for x in adds)
            if hit and out.get("success"):
                print(f"  OK  id={iid}  {name[:50]}")
                ok += 1
            else:
                print(
                    f"  BAD id={iid}  {name[:50]}  adds={adds!r}  success={out.get('success')}"
                )
                failed += 1
        except Exception as e:
            print(f"  FAIL id={iid} {name[:40]}: {e}")
            failed += 1
        n_run += 1
        if delay > 0:
            time.sleep(delay)
    return ok, failed


def run_deal_smoke(base: str, lang: str, delay: float) -> tuple[int, int]:
    data = get_json(base, "/deals")
    deals = data.get("deals") or []
    if not deals:
        print("GET /deals: could not list deals (check response shape)", file=sys.stderr)
        return 0, 0
    ok, failed = 0, 0
    sid = f"qa_deal_{uuid.uuid4().hex[:10]}"
    print(f"\n--- Deal search smoke ({len(deals)} deals) ---\n")
    for row in deals:
        did = row.get("deal_id")
        name = (row.get("deal_name") or "").strip()
        if not name:
            continue
        phrase = f"{name} dikhao"
        try:
            out = post_chat(base, sid, phrase, lang)
            tc = out.get("tool_calls") or []
            names = [str((c or {}).get("name")) for c in tc]
            if "search_deal" in names or "search_menu" in names:
                print(f"  OK  deal_id={did}  {name[:55]}")
                ok += 1
            else:
                print(f"  BAD deal_id={did}  {name[:40]}  tools={names}")
                failed += 1
        except Exception as e:
            print(f"  FAIL deal_id={did}: {e}")
            failed += 1
        if delay > 0:
            time.sleep(delay)
    return ok, failed


def _ping(base: str) -> None:
    try:
        r = requests.get(f"{base}/docs", timeout=5)
        print(f"  (health: GET /docs -> {r.status_code})")
    except Exception as e:
        print(f"  WARNING: {e}")


def main() -> None:
    _ensure_utf8_stdio()
    ap = argparse.ArgumentParser(
        description="Complex /chat scenarios + optional full menu add sweep",
    )
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--lang", default="ur", choices=["ur", "en"])
    ap.add_argument("--delay", type=float, default=1.25)
    ap.add_argument("--only", type=str, default="", help="Comma case IDs, e.g. C1,C2")
    ap.add_argument("--skip-complex", action="store_true")
    ap.add_argument("--all-items", action="store_true", help="GET /menu then one add phrase per item")
    ap.add_argument("--max-items", type=int, default=None, help="Cap menu sweep (for CI)")
    ap.add_argument("--deal-smoke", action="store_true", help="GET /deals then search_deal phrase each")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    only = {x.strip() for x in args.only.split(",") if x.strip()}

    print(f"API: {base}")
    _ping(base)

    total_failed = 0
    total_ok = 0

    if not args.skip_complex:
        print("\n>>> Complex scenarios (/chat)\n")
        ok, bad = run_complex(base, args.lang, args.delay, only)
        total_ok += ok
        total_failed += bad
        print(f"\n  complex: ok={ok} failed={bad}")

    if args.all_items:
        ok, bad = run_all_menu_items(base, args.lang, args.delay, args.max_items)
        total_ok += ok
        total_failed += bad
        print(f"\n  menu sweep: ok={ok} failed={bad}")

    if args.deal_smoke:
        ok, bad = run_deal_smoke(base, args.lang, args.delay)
        total_ok += ok
        total_failed += bad
        print(f"\n  deal smoke: ok={ok} failed={bad}")

    if args.skip_complex and not args.all_items and not args.deal_smoke:
        print("Nothing to run. Use complex (default), --all-items, and/or --deal-smoke", file=sys.stderr)
        raise SystemExit(2)

    print("\n" + "-" * 72)
    print(f"  TOTAL ok={total_ok} failed={total_failed}")
    if total_failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
