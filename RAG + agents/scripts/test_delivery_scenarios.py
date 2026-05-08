#!/usr/bin/env python3
"""
Delivery-focused scenario tests for the Khadim backend.

Covers as much as possible *without* Flutter UI or the kiosk flavor:

  1) /chat — all scripted phrases (intent + tools + reply). Same brain as voice
     after text exists (minus ASR). Use --session per-case or shared (default shared).

  2) /voice_chat — optional: one .wav (--wav) or a folder of recordings (--voice-dir)
     so you automate real STT + server pipeline without holding the phone mic during CI.

  3) Flutter UI — still manual or integration_test; this script only validates API JSON.

Usage:
  set API_BASE_URL=http://127.0.0.1:8000
  python scripts/test_delivery_scenarios.py

  python scripts/test_delivery_scenarios.py --voice-dir ./recordings/wavs

  python scripts/test_delivery_scenarios.py --chat-session per_case

Offline (no API, clear-cart + order-tracking heuristics):

  python scripts/test_cart_voice_heuristics.py

Optional: API_TOKEN=...  if /chat requires Bearer auth.
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

# Delivery + cart + payment coverage (IDs unique for --only filter).
CHAT_CASES: list[tuple[str, str, str]] = [
    (
        "D1",
        "Home delivery ke liye Chinese deals dikhao, phir Spring Rolls cart mein add karo, place order COD se.",
        "Combined browse + add + COD checkout",
    ),
    (
        "D4",
        "Place order card se bhi kar sakte hain aur COD bhi delivery pe.",
        "Payment conflict -> ask / single method",
    ),
    (
        "D7",
        "Pehle order place kardo phir ek cola aur zinger burger add karo COD.",
        "Speech order vs pipeline ordering",
    ),
    (
        "D11",
        "Deliver karo BBQ squad deal malai boti 2 add payment COD.",
        "Roman Urdu composite + COD",
    ),
    (
        "D13",
        "Nahi zinger burger bola tha cart mein add karo.",
        "Repair / correction",
    ),
    # Extra coverage (menu / cart / checkout / info-style utterances)
    (
        "M1",
        "Chinese menu dikhao.",
        "Menu / search routing",
    ),
    (
        "M2",
        "Fast food deals for 2 people dikhao.",
        "Deal + serving hint",
    ),
    (
        "M3",
        "Zinger burger cart mein add karo.",
        "Add to cart",
    ),
    (
        "M4",
        "Cart dikhao.",
        "Show cart tool path",
    ),
    (
        "M5",
        "Place order COD se.",
        "Checkout intent + COD",
    ),
    (
        "M6",
        "Mujhe payment karni hai.",
        "Payment / settle flow",
    ),
    (
        "M7",
        "Mera order kahan hai?",
        "Order status phrasing",
    ),
    (
        "M8",
        "Cart se saari cheezen remove karo poora empty kar do.",
        "Clear entire cart",
    ),
    (
        "M9",
        "What is the status of my order?",
        "English order status (not describe_item)",
    ),
    (
        "M10",
        "How much time is left for my order?",
        "ETA phrasing",
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
        description="Khadim /chat + optional /voice_chat scenario tests",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE,
        help=f"API base (default env API_BASE_URL or {DEFAULT_BASE})",
    )
    parser.add_argument(
        "--wav",
        type=Path,
        help="Single .wav for /voice_chat",
    )
    parser.add_argument(
        "--voice-dir",
        type=Path,
        help="Directory of .wav files — each uploaded to /voice_chat (sorted by name)",
    )
    parser.add_argument("--lang", default="ur", choices=["ur", "en"])
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help="Comma-separated case IDs. Empty = all /chat cases.",
    )
    parser.add_argument(
        "--skip-chat",
        action="store_true",
        help="Skip /chat matrix (only run --wav / --voice-dir)",
    )
    parser.add_argument(
        "--chat-session",
        choices=["single", "per_case"],
        default="single",
        help="single=one session_id for all /chat turns (memory); per_case=fresh session each",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.25,
        help="Seconds to sleep between /chat requests (reduces Groq 429 rate limits). Use 0 to disable.",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    print(f"API: {base}", flush=True)
    _ping(base)

    failed = 0
    chat_ok = 0
    voice_ok = 0
    voice_fail = 0

    if not args.skip_chat:
        print(
            "Running /chat scenario matrix (same logic family as voice after ASR)...",
            flush=True,
        )
        shared_session = f"qa_{uuid.uuid4().hex[:12]}"
        only = {x.strip() for x in args.only.split(",") if x.strip()}
        cases = CHAT_CASES
        if only:
            cases = [c for c in CHAT_CASES if c[0] in only]
            if not cases:
                print("No cases match --only", file=sys.stderr)
                raise SystemExit(2)

        for case_id, phrase, note in cases:
            sid = shared_session if args.chat_session == "single" else f"qa_{uuid.uuid4().hex[:12]}"
            try:
                out = post_chat(base, sid, phrase, args.lang)
                print_result(case_id, note, out)
                chat_ok += 1
                if args.delay > 0:
                    time.sleep(args.delay)
            except Exception as e:
                print(f"\n[{case_id}] FAIL: {e}")
                failed += 1

        print("\n" + "-" * 72)
        print(f"  /chat finished: ok={chat_ok} failed={failed}  (total={chat_ok + failed})")

    if args.wav:
        if not args.wav.is_file():
            print(f"WAV not found: {args.wav}", file=sys.stderr)
            raise SystemExit(2)
        vsession = f"qa_voice_{uuid.uuid4().hex[:12]}"
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
        # Dedupe if nested glob doubled
        wavs = list(dict.fromkeys(wavs))
        if not wavs:
            print(f"No .wav files under {d}", file=sys.stderr)
            raise SystemExit(2)
        print(f"\n/voice_chat batch: {len(wavs)} file(s) from {d}", flush=True)
        for i, wp in enumerate(wavs, start=1):
            vsession = f"qa_vbatch_{uuid.uuid4().hex[:10]}"
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

    if not args.skip_chat or args.wav or args.voice_dir:
        print(
            "\nWhat still needs manual / other automation:\n"
            "  • Flutter UI (navigation, cart widgets) — run the app or integration_test.\n"
            "  • Kiosk: scripts/test_dine_in_scenarios.py.\n"
            "  • Full menu + deals as delivery & dine-in user: scripts/test_user_dine_delivery_full.py.\n"
            "  • Complex multi-step utterances: scripts/test_menu_and_complex_scenarios.py.\n"
        )

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
