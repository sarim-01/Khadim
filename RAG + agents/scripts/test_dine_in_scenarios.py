#!/usr/bin/env python3
"""
Kiosk / dine-in scenario tests for the Khadim backend.

Same NLP + /chat pipeline as delivery; differs by:

  • Bootstraps an active dine-in session via:
      POST /dine-in/table-login  then, if needed,
      POST /dine-in/table-start-session
    so `session_id` matches what the kiosk app uses for voice/chat memory.

  • Phrases are framed for table / in-restaurant (no home delivery).

Environment (required unless --session-id):

  DINE_IN_TABLE_NUMBER   e.g. 3  or T3
  DINE_IN_TABLE_PIN      table PIN from public.restaurant_tables (or Admin → tables)

Optional:

  API_BASE_URL           default http://127.0.0.1:8000
  API_TOKEN              Bearer for /chat if your deployment requires it

Usage:

  set DINE_IN_TABLE_NUMBER=3
  set DINE_IN_TABLE_PIN=your_pin
  python scripts/test_dine_in_scenarios.py

  python scripts/test_dine_in_scenarios.py --session-id <uuid> --skip-table-auth

  python scripts/test_dine_in_scenarios.py --only K1,K6 --delay 1.5

See also: scripts/test_delivery_scenarios.py for delivery-only matrix.

Offline (no server): python scripts/test_cart_voice_heuristics.py

Full simulation suites (API must be running; use --delay to avoid Groq 429):

  python scripts/test_menu_and_complex_scenarios.py
  python scripts/test_user_dine_delivery_full.py --delay 1.5

Kiosk needs table env or --session-id (see Usage above).

DBA quick checks (psql):

  SELECT table_number, status, table_pin
  FROM public.restaurant_tables
  ORDER BY table_number;

  SELECT session_id, table_id, status, started_at
  FROM public.dine_in_sessions
  WHERE status = 'active';

  SELECT email, is_active FROM auth.app_users WHERE email = 'admin@gmail.com';
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

DEFAULT_TABLE = os.environ.get("DINE_IN_TABLE_NUMBER", "").strip()
DEFAULT_PIN = os.environ.get("DINE_IN_TABLE_PIN", "").strip()

# Kiosk / table coverage (IDs for --only).
CHAT_CASES: list[tuple[str, str, str]] = [
    (
        "K1",
        "Yahan Chinese deals dikhao, phir Spring Rolls cart mein add karo.",
        "Browse + add (table framing, no delivery)",
    ),
    (
        "K2",
        "Payment card se bhi kar sakte hain aur cash table pe bhi.",
        "Payment ambiguity → ask single method",
    ),
    (
        "K3",
        "Zinger burger cart mein add karo.",
        "Add to cart (speech item)",
    ),
    (
        "K4",
        "Chinese menu dikhao.",
        "Menu routing",
    ),
    (
        "K5",
        "Cart dikhao.",
        "Show cart",
    ),
    (
        "K6",
        "Waiter ko bulao.",
        "Waiter call tool path",
    ),
    (
        "K7",
        "Mera order kahan hai?",
        "Order status phrasing",
    ),
    (
        "K8",
        "BBQ squad deal dikhao 4 logon ke liye, phir malai boti 2 add karo payment cash.",
        "Composite deal + items + payment hint",
    ),
    (
        "K9",
        "Poora cart khali kar do. Sab kuch remove karo.",
        "Clear entire cart (kiosk table session)",
    ),
    (
        "K10",
        "Cart mein se saare items remove kar do.",
        "Clear cart Roman Urdu (was mis-routed to search_menu)",
    ),
    (
        "K11",
        "Mere order ki kya progress hai?",
        "Order progress → get_order_status (not menu info)",
    ),
    (
        "K12",
        "Ek kung pao aur do zinger burger cart mein add karo.",
        "Kung pao + zinger add (translation must not snap to karahi)",
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
        json={
            "session_id": session_id,
            "message": message,
            "language": lang,
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()


def post_voice_chat(
    base: str, session_id: str, wav_path: Path, lang: str = "ur"
) -> dict:
    with open(wav_path, "rb") as f:
        data = f.read()
    if len(data) < 2048:
        raise ValueError(f"audio too small ({len(data)} bytes): {wav_path}")
    files = {"file": (wav_path.name, data, "audio/wav")}
    fields = {
        "session_id": session_id,
        "language": lang,
        "conversation_history": "[]",
    }
    headers: dict[str, str] = {}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    r = requests.post(
        f"{base}/voice_chat",
        headers=headers,
        files=files,
        data=fields,
        timeout=180,
    )
    r.raise_for_status()
    return r.json()


def ensure_dine_in_session(
    base: str,
    table_number: str,
    pin: str,
) -> tuple[str, dict]:
    """Return (session_id, last_json_from_login_or_start)."""
    login = requests.post(
        f"{base}/dine-in/table-login",
        headers={"Content-Type": "application/json"},
        json={"table_number": table_number, "pin": pin},
        timeout=30,
    )
    if login.status_code == 401:
        raise RuntimeError(
            "table-login 401: invalid DINE_IN_TABLE_NUMBER / DINE_IN_TABLE_PIN"
        )
    login.raise_for_status()
    body = login.json()
    sid = body.get("session_id")
    if sid:
        return str(sid), body

    start = requests.post(
        f"{base}/dine-in/table-start-session",
        headers={"Content-Type": "application/json"},
        json={"table_number": table_number, "pin": pin},
        timeout=30,
    )
    if start.status_code == 409:
        raise RuntimeError(
            "table-start-session 409: table not available — end the dine-in session "
            "in Admin or clear stuck rows (see script docstring DBA queries)."
        )
    start.raise_for_status()
    body2 = start.json()
    sid2 = body2.get("session_id")
    if not sid2:
        raise RuntimeError(f"No session_id after table-start-session: {body2}")
    return str(sid2), body2


def print_result(case_id: str, note: str, payload: dict) -> None:
    print("\n" + "=" * 72)
    print(f"  [{case_id}]  {note}")
    print("=" * 72)
    print("  success:", payload.get("success"))
    print("  reply:", (payload.get("reply") or "")[:500])
    if len((payload.get("reply") or "")) > 500:
        print("  ... [truncated]")
    tc = payload.get("tool_calls") or []
    print("  tool_calls:", json.dumps(tc, ensure_ascii=False)[:800])
    nlp = payload.get("nlp") or {}
    print("  nlp.intent:", nlp.get("intent"), " signals:", nlp.get("signals"))
    if "transcript" in payload:
        print("  transcript:", (payload.get("transcript") or "")[:300])
    if "normalized_text" in payload:
        print("  normalized_text:", (payload.get("normalized_text") or "")[:300])


def _ping(base: str) -> None:
    try:
        r = requests.get(f"{base}/docs", timeout=5)
        print(f"  (health: GET /docs -> {r.status_code})")
    except Exception as e:
        print(f"  WARNING: cannot reach {base}: {e}")


def main() -> None:
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Khadim dine-in /chat + optional /voice_chat (kiosk session)",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE,
        help=f"API base (default env API_BASE_URL or {DEFAULT_BASE})",
    )
    parser.add_argument("--table-number", default=DEFAULT_TABLE, help="Or env DINE_IN_TABLE_NUMBER")
    parser.add_argument("--table-pin", default=DEFAULT_PIN, help="Or env DINE_IN_TABLE_PIN")
    parser.add_argument(
        "--session-id",
        default="",
        help="Skip table login and use this dine-in session UUID directly",
    )
    parser.add_argument(
        "--skip-table-auth",
        action="store_true",
        help="Alias: require --session-id (same as providing session-id)",
    )
    parser.add_argument("--wav", type=Path, help="Single .wav for /voice_chat")
    parser.add_argument(
        "--voice-dir",
        type=Path,
        help="Directory of .wav files for /voice_chat batch",
    )
    parser.add_argument("--lang", default="ur", choices=["ur", "en"])
    parser.add_argument("--only", type=str, default="", help="Comma-separated case IDs")
    parser.add_argument("--skip-chat", action="store_true", help="Only voice batch / wav")
    parser.add_argument(
        "--delay",
        type=float,
        default=1.25,
        help="Seconds between /chat calls (Groq rate limits). 0 = off.",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    print(f"API: {base}", flush=True)
    _ping(base)

    session_id = (args.session_id or "").strip()
    if args.skip_table_auth and not session_id:
        print("--skip-table-auth requires --session-id", file=sys.stderr)
        raise SystemExit(2)

    if not session_id:
        tnum = (args.table_number or "").strip()
        pin = (args.table_pin or "").strip()
        if not tnum or not pin:
            print(
                "Set DINE_IN_TABLE_NUMBER and DINE_IN_TABLE_PIN, or pass "
                "--table-number / --table-pin, or --session-id.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        try:
            session_id, boot = ensure_dine_in_session(base, tnum, pin)
            print(
                f"Dine-in session: {session_id}  (table {boot.get('table_number', tnum)!r})",
                flush=True,
            )
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            raise SystemExit(1)

    failed = 0
    chat_ok = 0
    voice_ok = 0
    voice_fail = 0

    if not args.skip_chat:
        print(
            "Running /chat dine-in matrix (session_id = active table session)...",
            flush=True,
        )
        shared_session = session_id
        only = {x.strip() for x in args.only.split(",") if x.strip()}
        cases = CHAT_CASES
        if only:
            cases = [c for c in CHAT_CASES if c[0] in only]
            if not cases:
                print("No cases match --only", file=sys.stderr)
                raise SystemExit(2)

        for case_id, phrase, note in cases:
            try:
                out = post_chat(base, shared_session, phrase, args.lang)
                print_result(case_id, note, out)
                chat_ok += 1
                if args.delay > 0:
                    time.sleep(args.delay)
            except Exception as e:
                print(f"\n[{case_id}] FAIL: {e}")
                failed += 1

        print("\n" + "-" * 72)
        print(f"  /chat dine-in finished: ok={chat_ok} failed={failed}  (total={chat_ok + failed})")

    if args.wav:
        if not args.wav.is_file():
            print(f"WAV not found: {args.wav}", file=sys.stderr)
            raise SystemExit(2)
        vsession = session_id
        print(f"\nPosting /voice_chat: {args.wav} ...")
        try:
            vout = post_voice_chat(base, vsession, args.wav, args.lang)
            print_result("VOICE_1", str(args.wav), vout)
            voice_ok += 1
        except Exception as e:
            print(f"/voice_chat FAIL: {e}", file=sys.stderr)
            voice_fail += 1
            failed += 1

    if args.voice_dir:
        d = args.voice_dir
        if not d.is_dir():
            print(f"--voice-dir not a directory: {d}", file=sys.stderr)
            raise SystemExit(2)
        wavs = sorted(d.glob("*.wav")) + sorted(d.glob("**/*.wav"))
        wavs = list(dict.fromkeys(wavs))
        if not wavs:
            print(f"No .wav files under {d}", file=sys.stderr)
            raise SystemExit(2)
        print(f"\n/voice_chat batch: {len(wavs)} file(s) from {d}", flush=True)
        for i, wp in enumerate(wavs, start=1):
            vsession = session_id
            label = f"V{i}_{wp.stem}"
            try:
                vout = post_voice_chat(base, vsession, wp, args.lang)
                try:
                    rel_note = str(wp.resolve().relative_to(d.resolve()))
                except ValueError:
                    rel_note = str(wp)
                print_result(label, rel_note, vout)
                voice_ok += 1
            except Exception as e:
                print(f"\n[{label}] FAIL: {e}")
                voice_fail += 1
                failed += 1

        print("-" * 72)
        print(f"  /voice_chat batch: ok={voice_ok} failed={voice_fail}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
