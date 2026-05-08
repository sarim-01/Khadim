"""
voice/urdu_translator.py
Normalizes Whisper output to English for keyword matching.
"""

import re, os
from typing import Dict, List
from dotenv import load_dotenv
load_dotenv()

# Keep translation deterministic by default; set to 1/true to re-enable LLM fallback.
TRANSLATOR_LLM_FALLBACK_ENABLED = (
    os.getenv("TRANSLATOR_LLM_FALLBACK_ENABLED", "0").strip().lower()
    in {"1", "true", "yes", "on"}
)


def _safe_log_text(value: str) -> str:
    """Return ASCII-safe representation for Windows cp1252 consoles."""
    try:
        return (value or "").encode("unicode_escape").decode("ascii")
    except Exception:
        return "<unprintable>"

# ─────────────────────────────────────────────────────────────
# ENGLISH WRITTEN IN URDU SCRIPT BY WHISPER
# ─────────────────────────────────────────────────────────────
ENGLISH_IN_URDU_SCRIPT = {
    # ── Order/confirm words — the most critical ────────────
    "اڈرگن":   "order confirm",  # "order confirm" merged by Whisper
    "اڈر":     "order",          # Whisper mishear of "order"
    "اوڈر":    "order",          # another variant
    "اوڈرگن":  "order",
    "کنفرم":   "confirm",
    "کنفرمڈ":  "confirm",
    "پلیس":    "place",
    "بلیس":    "place",          # Whisper mishears "place"
    "پلیس کردو": "place it",
    "اسے پلیس": "place it",
    "چک اوپ":  "checkout",
    "چیک اوپ": "checkout",
    # ── Payment ─────────────────────────────────────────────
    # Full Urdu payment sentences first so they consume the whole phrase
    # before "پیمنٹ"/"کیش"/"کارڈ" (single-word entries below) can fragment them.
    "مجھے کارڈ سے پیمنٹ کرنی ہے": "pay by card",
    "مجھے کیش سے پیمنٹ کرنی ہے":  "pay by cash",
    "مجھے کارڈ سے پیمنٹ کرنا ہے": "pay by card",
    "مجھے کیش سے پیمنٹ کرنا ہے":  "pay by cash",
    "کارڈ سے پیمنٹ کرنی ہے":     "pay by card",
    "کیش سے پیمنٹ کرنی ہے":      "pay by cash",
    "کارڈ سے پیمنٹ کرنا ہے":     "pay by card",
    "کیش سے پیمنٹ کرنا ہے":      "pay by cash",
    "کارڈ سے ادائیگی کرنی ہے":   "pay by card",
    "کیش سے ادائیگی کرنی ہے":    "pay by cash",
    "مجھے پیمنٹ کرنی ہے":        "payment karni hai",
    "مجھے پیمنٹ کرنا ہے":        "payment karna hai",
    "مجھے ادائیگی کرنی ہے":      "payment karni hai",
    "پیمنٹ کرنی ہے":             "payment karni hai",
    "پیمنٹ کرنا ہے":             "payment karna hai",
    "ادائیگی کرنی ہے":           "payment karni hai",
    "ادائیگی کرنا ہے":           "payment karna hai",
    "گاڈ":     "card",           # Whisper mishears "card" as "gaad"
    "پیمنٹ":   "payment",
    "کیش":     "cash",
    # ── Cart/bill ────────────────────────────────────────────
    "بلہ":     "bill",           # Whisper mishears "bill"
    "فریوٹس":  "favourites",     # Whisper mishears "favourites"
    "فیوٹس":   "favourites",     # Whisper mishears "favourites"
    "فیورٹس":  "favourites",
    "فیوڈز":   "favourites",
    "فریورٹس": "favourites",
    "پھرائیوٹس": "favourites",
    "فریوٹ":   "favourite",
    "فریوٹنی": "favourites",
    "ویلے":    "",               # filler word — ignore
    "فارم":    "",               # filler word — ignore
    "کروں گا": "",               # "will do" — filler for intent
    # ── Numbers ─────────────────────────────────────────────
    "اون":     "one",   "اوان": "one",   "وان":  "one",
    "ٹو":      "two",   "تھری": "three", "فور":  "four",
    # ── Actions ─────────────────────────────────────────────
    "ایڈ":     "add",   "ایٹ":  "add",
    "ریموو":   "remove","ریموف":"remove",
    "شو":      "show",  "شووی": "show me","شومی": "show me",
    "ویٹر":    "waiter",
    "ویٹرر":   "waiter",
    "سٹیٹس":   "status",
    "اسٹیٹس":  "status",
    "ایٹا":    "eta",
    "کارٹ":    "cart",
    "منیو":    "menu",  "منیوم":"menu",   "مینیو":"menu",
    "میلیو":   "menu",
    "ڈیل":     "deal",  "ڈیلز": "deals", "ڈیم": "deal",
    "لکھو":    "write",  # NEW: handle "لکھو" (write) as a deal request variant
    # ── Food ─────────────────────────────────────────────────
    "فرائز":   "fries", "فرائیز":"fries",
    "چکن":     "chicken","چیکن": "chicken","جیکن": "chicken","چکا": "chicken","برگر": "burger","بردر": "burger",
    "چکر":     "chicken","کولا": "cola",  "ڈرنک": "drink",
    "نگٹس":    "nuggets","نیگٹس":"nuggets","نیکٹس":"nuggets","نیگسٹ":"nuggets","نیکٹ":"nuggets","نیگٹسٹو":"nuggets",
    "زنگر":    "zinger","زیگر": "zinger","زینگر":"zinger","زیلگر":"zinger",
    "کنگ پاؤ": "kung pao","کنگ پاک": "kung pao","کونگ پاؤ": "kung pao",
    # ── Cuisine ──────────────────────────────────────────────
    "فاسٹ":    "fast",  "فوڈ":  "food",
    "فاس":     "fast",  "فاصحوٹ": "fast food", "فاصحود": "fast food", "فاسپورٹ": "fast food", "فاس خوڈ": "fast food", "خوڈ": "food", "ارمتین": "3",
    "چائنیز":  "chinese","چینیز":"chinese",
    "ڈیسی":    "desi",  "ڈیز":  "desi",
    "بی بی کیو":"bbq",
}

# ─────────────────────────────────────────────────────────────
# URDU SCRIPT → ENGLISH (proper Urdu phrases)
# ─────────────────────────────────────────────────────────────
URDU_SCRIPT_MAP = {
    # ── Place order / checkout phrases ──────────────────────
    "میرا آرڈر کنفرم ہے":       "confirm order",
    "میرا اوڈر کنفرم ہے":       "confirm order",
    "میرا اوڈر کنفرم":          "confirm order",
    "میرا order confirm":       "confirm order",
    "میرا order":               "my order",
    "آرڈر کنفرم":               "confirm order",
    "پلیس کردو":                 "place order",
    "پلیس کر دو":                "place order",
    "اسے پلیس کردو":             "place it",
    "اسے پلیس کر دو":            "place it",
    "میں اسے پلیس کر":          "place it",
    "میں اسے place کر":         "place it",
    "آرڈر بھیج دو":              "place order",
    "بھیج دو":                   "place order",
    "آرڈر کرو":                  "place order",
    "آرڈر کر دو":                "place order",
    "چیک آؤٹ کرنا ہے":          "checkout",
    "چیک آؤٹ":                   "checkout",
    "چیک اوٹ":                   "checkout",
    # ── Payment method ───────────────────────────────────────
    # Longest-first: full payment sentences first so they consume the whole
    # phrase before the shorter mappings (e.g. "کیش سے") or the single-word
    # map (e.g. "پیمنٹ" -> "payment") can fragment them.
    "مجھے کارڈ سے پیمنٹ کرنی ہے": "pay by card",
    "مجھے کیش سے پیمنٹ کرنی ہے":  "pay by cash",
    "مجھے کارڈ سے پیمنٹ کرنا ہے": "pay by card",
    "مجھے کیش سے پیمنٹ کرنا ہے":  "pay by cash",
    "کارڈ سے پیمنٹ کرنی ہے":     "pay by card",
    "کیش سے پیمنٹ کرنی ہے":      "pay by cash",
    "کارڈ سے پیمنٹ کرنا ہے":     "pay by card",
    "کیش سے پیمنٹ کرنا ہے":      "pay by cash",
    "کارڈ سے ادائیگی کرنی ہے":   "pay by card",
    "کیش سے ادائیگی کرنی ہے":    "pay by cash",
    "مجھے پیمنٹ کرنی ہے":        "payment karni hai",
    "مجھے پیمنٹ کرنا ہے":        "payment karna hai",
    "مجھے ادائیگی کرنی ہے":      "payment karni hai",
    "کارڈ سے پیمنٹ":             "card payment",
    "کیش سے پیمنٹ":              "cash payment",
    "کارڈ سے":                   "card payment",
    "کارڈ کے ذریعے":             "card payment",
    "کارڈ پیمنٹ":                "card payment",
    "کارڈ سے ادائیگی":           "card payment",
    "کیش آن ڈیلیوری":           "cash on delivery",
    "کیش سے":                    "cash payment",
    "کیش پیمنٹ":                 "cash payment",
    "کیش سے ادائیگی":            "cash payment",
    "نقد ادائیگی":               "cash payment",
    # Generic payment phrases — keep the word "payment" in the normalized
    # text so the backend's deterministic router (which looks for
    # "payment karni"/"payment karna") can kick in and prompt for method.
    "پیمنٹ کرنی ہے":             "payment karni hai",
    "پیمنٹ کرنا ہے":             "payment karna hai",
    "پیمنٹ کرنی":                "payment karni",
    "پیمنٹ کرنا":                "payment karna",
    "ادائیگی کرنی ہے":           "payment karni hai",
    "ادائیگی کرنا ہے":           "payment karna hai",
    "ادائیگی کرنی":              "payment karni",
    "بل ادا کرنا":               "pay the bill",
    "بل ادا کرنی":               "pay the bill",
    # ── Waiter / payment assistance ─────────────────────────
    "ویٹر کو بلاؤ":              "call waiter",
    "ویٹر کو بلاو":              "call waiter",
    "ویٹر بلاؤ":                 "call waiter",
    "ویٹر بلاو":                 "call waiter",
    "ویٹر چاہیے":                "call waiter",
    "ویٹر":                      "waiter",
    # ── Order status / ETA ──────────────────────────────────
    "آرڈر کی حالت":              "order status",
    "آرڈر کہاں ہے":              "order status",
    "آرڈر کی اپڈیٹ":             "order status",
    "کتنا وقت باقی ہے":          "time left",
    "کتنا ٹائم رہ گیا":          "time left",
    "آرڈر میں کتنا ٹائم":        "time left",
    "آڈر میں کتنا ٹائم":         "time left",
    "آرڈر کو کتنا ٹائم":         "time left",
    "میری ڈیلیوری کتنی دیر":     "time left",
    "ای ٹی اے":                  "eta",
    # ── Suggestions / top sellers ───────────────────────────
    "ٹاپ سیلرز":                 "top sellers",
    "مشہور آئٹمز":               "top sellers",
    "مشورہ دو":                  "suggest",
    "سجیشن دو":                  "suggest",
    # ── Show cart ────────────────────────────────────────────
    "کارڈ خالی کر دو":          "empty cart",
    "کارڈ خالی کر":            "empty cart",
    "کارڈ خالی":               "empty cart",
    "کارٹ خالی کر دو":         "empty cart",
    "کارٹ خالی":               "empty cart",
    "کارٹ میں کیا ہے":          "show cart",
    "کارٹ دکھاؤ":                "show cart",
    "کارٹ دکھائیں":              "show cart",
    "میری کارٹ":                 "show cart",
    "بل بتاؤ":                   "show cart",
    "بل دکھاؤ":                  "show cart",
    "کتنا بل ہے":                "show cart",
    "کل قیمت":                   "show cart",
    # ── Custom deal patterns ─────────────────────────────────
    "کسٹم ڈیل بناؤ":             "create custom deal",
    "کرسن ڈیل":                  "custom deal",
    "قسم ڈیل":                   "custom deal",
    "گسٹن ڈیل":                  "custom deal",
    "کسٹم ڈیل بنائیں":           "create custom deal",
    "اپنی ڈیل بناؤ":             "create custom deal",
    "ڈیل بنا دو":                "create deal",
    "ڈیل بناؤ":                  "create deal",
    "ڈیل چاہیے":                 "create deal",
    "ڈیل پیدا":                  "create deal",
    "ڈیل لکھو":                  "show deal",
    "کی ڈیل":                    "person deal",
    "کے لیے ڈیل":                "deal for",
    "بندوں کی ڈیل":              "people deal for",
    "لوگوں کے لیے":              "people deal for",
    "بندوں":                     "people",
    "بندگرہ":                    "people",
    "بندو":                      "people",
    "بند":                       "people",
    "مندھوں":                    "people",
    "مندوں":                     "people",
    "پرسند":                     "person",
    # ── Navigation ───────────────────────────────────────────
    "کارٹ دکھاؤ":                "show cart",
    "آرڈرز دکھاؤ":               "my orders",
    "ڈیلز دکھاؤ":                "show deals",
    "فیورٹس دکھاؤ":              "show favourites",
    "فریوٹس":                    "favourites",
    "فیوٹس":                     "favourites",
    "فریویٹ":                    "favourite",
    "فیویٹس":                    "favourites",
    "فیویٹ":                     "favourite",
    "فریورٹس":                   "favourites",
    "پھرائیوٹس":                 "favourites",
    "فریوٹنی":                   "favourites",
    # ── Actions ──────────────────────────────────────────────
    "کارٹ میں ڈالو":             "add to cart",
    "کارٹ میں شامل":             "add to cart",
    "شامل کرو":                  "add",
    # Imperative dois — unicode keys so bare dois->2 cannot break "کر dois".
    "شامل کر دو":        "add",
    "کر دو":   "kar do",
    "ڈالو":                      "add",
    "ڈال دو":            "add",
    "ہٹاؤ":                      "remove",
    "ہٹا دو":                    "remove",
    "نکالو":                     "remove",
    "دکھاؤ":                     "show",
    "دکھا":                      "show",
    "دکھاگا":                    "show",
    "دکھائیں":                   "show",
    "دیکھو":                     "show",
    "بتاؤ":                      "show",
    "دیدو":                      "show",
    "دے دو":                     "show",
    # ── Menu/cuisine ─────────────────────────────────────────
    "مینو":                      "menu",
    "فاسٹ فوڈ":                  "fast food",
    "فاسبوٹ":                    "fast food",
    "پاسٹ وڈ":                   "fast food",
    "فاس فوٹ":                   "fast food",
    "فاس فورڈ":                  "fast food",
    "فاسپورٹ":                   "fast food",
    "فاس خوڈ":                   "fast food",
    "فاس":                       "fast food",
    "چائنیز":                    "chinese",
    "چینیز":                     "chinese",
    "چینی":                      "chinese",
    "دیسی":                      "desi",
    "مشروبات":                   "drinks",
    # ── Deal keywords ────────────────────────────────────────
    "ڈیل":                       "deal",
    "ڈیلز":                      "deals",
    "سولو":                      "solo",
    "اسکواڈ":                    "squad",
    "پارٹی":                     "party",
    "پرسن":                      "person",
    "افراد":                     "people",
    "لوگ":                       "people",
    "کے لیے":                    "for",
    "کیلئے":                     "for",
    # ── Food items ───────────────────────────────────────────
    # Keep "zinger" only — "برگر"/"burger" is mapped separately or already in the phrase.
    # Mapping زنگر→"zinger burger" then برگر→"burger" produced "zinger burger burger".
    "زنگر":                      "zinger",
    "زندھر":                     "zinger",
    "برگر":                      "burger",
    "کڑاہی":                     "karahi",
    "بریانی":                    "biryani",
    "نہاری":                     "nihari",
    "ٹکہ":                       "tikka",
    "چاؤمین":                    "chow mein",
    "روٹی":                      "roti",
    "نان":                       "naan",
    "گارلک نان":                 "garlic naan",
    "کولا":                      "cola",
    "لیمونیڈ":                   "lemonade",
    "چائے":                      "chai",
    "پانی":                      "water",
    # ── Numbers ──────────────────────────────────────────────
    "ایک":                       "1",
    "دو":                        "2",
    "تین":                       "3",
    "چار":                       "4",
    "اور":                       "and",
    "بھی":                       "and",
    # ── Filler words — strip these ───────────────────────────
    "مجھے":                      "",
    "اچھا":                      "",
    "لیکن":                      "",
    "نہ":                        "",
    "طور":                       "",
    "اس کو":                     "",
    "کرنا ہے":                   "",
    # ── Confirmations ────────────────────────────────────────
    "ہاں":                       "yes",
    "جی":                        "yes",
    "ٹھیک ہے":                   "ok",
    "بالکل":                     "yes",
}

# ─────────────────────────────────────────────────────────────
# HINDI/DEVANAGARI
# ─────────────────────────────────────────────────────────────
HINDI_MAP = {
    "शो":"show","मी":"me","मुझे":"show me","दिखाओ":"show",
    "मेनू":"menu","कार्ट":"cart","ऐड":"add","रिमूव":"remove",
    "ऑर्डर":"order","फास्ट":"fast","फूड":"food","चाइनीज़":"chinese",
    "देसी":"desi","डील":"deal","बर्गर":"burger","ज़िंगर":"zinger",
    "फ्राइज़":"fries","चाय":"chai","कोला":"cola","पानी":"water",
    "हाँ":"yes","ओके":"ok","ठीक":"ok","एक":"1","दो":"2","तीन":"3",
}

# ─────────────────────────────────────────────────────────────
# ROMAN URDU
# ─────────────────────────────────────────────────────────────
ROMAN_MAP = {
    # Order/payment — longest first
    "cash on delivery":           "cash on delivery",
    "card payment":               "card payment",
    "confirm order":              "confirm order",
    "place order":                "place order",
    "order confirm":              "confirm order",
    "mera order confirm":         "confirm order",
    "mera order":                 "my order confirm",  # NEW
    "my order confirm":           "confirm order",    # NEW
    "my order is":                "my order",          # NEW
    "place it":                   "place order",       # NEW
    "place kar do":               "place order",       # NEW
    "place karo":                 "place order",       # NEW
    "checkout karo":              "checkout",
    "checkout":                   "checkout",
    "bhej do":                    "place order",
    "order karo":                 "place order",
    "order de do":                "place order",
    "card se":                    "card payment",
    "cash se":                    "cash payment",
    "waiter bulao":               "call waiter",
    "waiter chahiye":             "call waiter",
    "order status":               "order status",
    "kitna time":                 "time left",
    "time left":                  "time left",
    "eta":                        "eta",
    "top sellers":                "top sellers",
    "popular items":              "top sellers",
    # Cart
    "cart dikhao":                "show cart",
    "show cart":                  "show cart",
    "bill batao":                 "show cart",
    "kya hai cart mein":          "show cart",
    # Custom deal
    "deal banao":                 "create deal",
    "deal bana do":               "create deal",
    "deal chahiye":               "create deal",
    "custom deal":                "create custom deal",
    "custom bill":                "create custom deal",
    "my fruits":                  "my favourites",
    "my feet":                    "my favourites",
    "my fruit":                   "my favourites",
    "to my favourites":           "to my favourites",
    "create the bill":            "create custom deal",
    "make the bill":              "create custom deal",
    "apni deal":                  "create custom deal",
    "ke liye deal":               "deal for",
    "logon ke liye":              "people for",
    "bando ki deal":              "people deal",        # NEW
    "bando":                      "people",             # NEW
    "bande":                      "people",             # NEW
    "bandon":                     "people",             # NEW
    # Add/remove
    "cart mein dalo":             "add to cart",
    "shamil karo":                "add",
    "dalo":                       "add",
    "hatao":                      "remove",
    "hata do":                    "remove",
    "nikal do":                   "remove",
    "nikalo":                     "remove",
    "remove krdo":                "remove",
    "remove kardo":               "remove",
    "remove kar do":              "remove",
    # Nav
    "fast food":                  "fast food",
    "fas food":                   "fast food",          # NEW
    "fos food":                   "fast food",          # NEW
    "ford":                       "fast food",          # NEW: handle mispronunciation
    "chinese":                    "chinese",
    "desi":                       "desi",
    "bbq":                        "bbq",
    "menu":                       "menu",
    "deal":                       "deal",
    "deals":                      "deals",
    # Food
    "zinger":                     "zinger",
    "burger":                     "burger",
    "biryani":                    "biryani",
    "karahi":                     "karahi",
    "fries":                      "fries",
    "chai":                       "chai",
    "cola":                       "cola",
    "pani":                       "water",
    # Numbers
    "haan":                       "yes",
    "theek hai":                  "ok",
    "aur":                        "and",
    "ek":                         "1",
    "do":                         "2",
    "teen":                       "3",
    "chaar":                      "4",
    "paanch":                     "5",
}

# ─────────────────────────────────────────────────────────────
# CUSTOM DEAL DETECTION
# ─────────────────────────────────────────────────────────────
_CUSTOM_DEAL_PATTERNS = [
    "ڈیل بنا","ڈیل چاہیے","ڈیل پیدا","ڈیل دیں",
    "کی ڈیل","کے لیے ڈیل","کیلئے ڈیل",
    "بندوں","مندھوں","پرسند","لوگوں کے لیے",
    "deal banao","deal bana do","deal chahiye",
    "custom deal","apni deal","ke liye deal","logon ke liye",
    "پاس بندوں",    # "5 people" — پانچ→پاس mis-hearing
    "پائن بندوں",   # another variant
    "فاصحوٹ",       # "fast food" mangled
    "فاصحود",       # another mangling
]

_COUNT_MAP = {
    "ایک":"1","دو":"2","تین":"3","چار":"4","پانچ":"5","چھ":"6",
    "ek":"1","do":"2","teen":"3","chaar":"4",
    "1":"1","2":"2","3":"3","4":"4","5":"5","6":"6",
    "پاس":   "5",    # Whisper mishears پانچ as پاس
    "پائن":  "9",    # نو variant
    "پاون":  "5",    # another پانچ variant
}

def _is_custom_deal_query(text: str) -> bool:
    """Trigger custom deal whenever the user clearly wants a NEW/MADE deal.

    Robust to:
      - Whisper translating Urdu → English (so "custom" word may be lost)
      - Roman Urdu (`bana do`, `banado`, `banade`)
      - Pure Urdu script (`ڈیل بنا`, `ڈیل بنوا`)
      - Verb + "deal" + people-count combos like "make a deal for 2 people"
    """
    lowered = (text or "").lower()
    if not lowered.strip():
        return False

    # If this is a favourites command, do not hijack it as create-custom-deal.
    if any(w in lowered for w in ["favourite", "favorite", "favourites", "favorites", "فریوٹس", "فیوٹس", "فیورٹس", "فیوڈز", "فریورٹس", "پھرائیوٹس", "فریوٹ", "فریوٹنی"]):
        return False

    # Explicit "show me deals" should NEVER be treated as a create request.
    show_phrases = [
        "show deal", "show deals", "show me deal", "show me the deal",
        "dikhao deal", "deal dikhao", "deals dikhao",
        "list deals", "available deals", "what deals",
        "ڈیل دکھا", "ڈیلز دکھا", "ڈیل دیکھ", "ڈیلز دیکھ",
    ]
    if any(p in lowered for p in show_phrases):
        return False

    # 1) Strong explicit create patterns — works in Urdu / Roman / English.
    explicit_create_patterns = [
        # Urdu script
        "ڈیل بنا", "ڈیل بنوا", "ڈیل چاہیے", "ڈیل چاہئے", "ڈیل پیدا",
        "ڈیل تیار", "کسٹم ڈیل",
        # Roman Urdu
        "deal banao", "deal bana do", "deal banado", "deal bana de",
        "deal banade", "deal bnado", "deal bnaado", "deal chahiye",
        "deal chahiyay", "custom deal", "apni deal", "khaas deal",
        "khaas deel",
        # English variants Whisper actually emits when translating Urdu
        "custom bill", "create the bill", "make the bill",
        "create a deal", "create deal", "make a deal", "make me a deal",
        "build me a deal", "build a deal", "build deal",
        "i want a deal", "i need a deal", "i want deal",
        "give me a deal", "prepare a deal", "prepare deal",
    ]
    if any(p in lowered for p in explicit_create_patterns):
        return True

    # 2) Heuristic: a create-verb + the word "deal" within ~4 tokens of each other.
    #    Catches "bana do <something> deal", "make a special deal", "create chinese deal".
    create_verb_pattern = (
        r"\b("
        r"bana(?:o|do|ado|de|ade|den|dijiye)?|bnado|bnaao|"
        r"banwa(?:o|do)?|"
        r"create|make|build|prepare|generate|want|need|give|"
        r"بنا|بنوا|تیار"
        r")\b"
    )
    deal_word_pattern = r"(deal|deals|ڈیل|ڈیلز)"

    if re.search(create_verb_pattern, lowered) and re.search(deal_word_pattern, lowered):
        # Make sure they appear close-ish (within ~40 chars) to avoid false matches
        # like "make me chicken karahi I saw a deal somewhere".
        for m_verb in re.finditer(create_verb_pattern, lowered):
            for m_deal in re.finditer(deal_word_pattern, lowered):
                if abs(m_deal.start() - m_verb.start()) <= 40:
                    return True

    # 3) "for N people" + "deal" alone — strongly implies a NEW deal request.
    #    e.g. "deal for 2 people", "2 logon ke liye deal".
    if re.search(deal_word_pattern, lowered) and re.search(
        r"\b(for\s+\d+\s+(people|person)|\d+\s+(log|logon|logo|bando|bandon|afrad|afraad|persons?))\b",
        lowered,
    ):
        return True

    return False

def _extract_deal_info(text: str):
    """Pull (people_count, cuisine) from a deal-related utterance.

    Tries Urdu, Roman Urdu, and Whisper's translated English in that order.
    """
    t = (text or "").lower()

    # ── People count ──────────────────────────────────────────
    m = re.search(
        r'(ایک|دو|تین|چار|پانچ|چھ|1|2|3|4|5|6|7|8|9|10)\s*'
        r'(?:پرسن|پرسند|پرسندوں|بندوں|بندے|لوگوں|مندھوں|مندوں|افراد|'
        r'person|people|persons|log|logon|bando|bandon|afrad|afraad)',
        text,
    )
    count = _COUNT_MAP.get(m.group(1), m.group(1)) if m else ""

    if not count:
        # Roman/English number-words near the word "deal".
        m2 = re.search(
            r'\b(1|2|3|4|5|6|7|8|9|10|ek|do|teen|chaar|paanch|chha|saat|aath|nau|das|'
            r'one|two|three|four|five|six|seven|eight|nine|ten)\b',
            t,
        )
        if m2 and ("deal" in t or "ڈیل" in text):
            tok = m2.group(1)
            english_word_map = {
                "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
                "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
                "chha": "6", "saat": "7", "aath": "8", "nau": "9", "das": "10",
            }
            count = _COUNT_MAP.get(tok, english_word_map.get(tok, tok))

    # ── Cuisine ───────────────────────────────────────────────
    cuisine = ""
    if any(w in t for w in ["چائنیز", "چینیز", "chinese", "چینی"]):
        cuisine = "chinese"
    elif any(w in t for w in ["دیسی", "desi", "پاکستانی", "pakistani"]):
        cuisine = "desi"
    elif any(w in t for w in ["بی بی کیو", "bbq", "ٹکہ", "barbeque", "barbecue"]):
        cuisine = "bbq"
    elif any(
        w in t
        for w in [
            "فاسٹ", "fast", "فاس فوٹ", "فاصد خوب", "فاصد", "فاسد خوب",
            "زنگر", "برگر", "burger", "zinger", "fries", "fast food",
        ]
    ):
        cuisine = "fast food"

    return count, cuisine


# Dish tokens that MUST survive the custom-deal rewrite. When the user says
# "karahi deal for 3 people" the naive rewrite throws away "karahi" and the
# agent has to guess — which it can't, because "karahi" isn't a cuisine.
# Keeping the list explicit here (rather than reading from the DB) avoids
# coupling the translator to the database layer and is plenty fast.
#
# Each entry maps one or more surface forms (Urdu / Roman / English) to the
# canonical English dish keyword the agent's `_rule_based_parse` expects in
# `known_items`.
_DISH_ALIASES: Dict[str, List[str]] = {
    "karahi":    ["karahi", "karhai", "karai", "کڑاہی", "کڑائی"],
    "handi":     ["handi", "ہانڈی"],
    "biryani":   ["biryani", "biriyani", "بریانی"],
    "tikka":     ["tikka", "tika", "ٹکہ"],
    "kung pao": ["kung pao", "kungpao", "کنگ پاؤ", "کنگ پاک", "کنک پاؤ"],
    "boti":      ["boti", "بوٹی"],
    "kebab":     ["kebab", "kabab", "kabaab", "کباب"],
    "burger":    ["burger", "برگر"],
    "zinger":    ["zinger", "zingar", "زنگر"],
    "pizza":     ["pizza", "پیزا"],
    "fries":     ["fries", "فرائز"],
    "wings":     ["wings", "ونگز"],
    "sandwich":  ["sandwich", "sandwhich", "سینڈوچ"],
    "chowmein":  ["chowmein", "chow mein", "چومیں"],
    "manchurian": ["manchurian", "منچورین"],
    "fried rice": ["fried rice", "رائس", "چاول"],
    "shake":     ["shake", "شیک", "milkshake"],
    "margarita": ["margarita", "مارگریٹا"],
}


# Adjectives/qualifiers that narrow down which variant the user wants.
# When one of these appears IMMEDIATELY before a known dish token we fold
# it into the phrase — so "chicken biryani" survives as a single token
# instead of collapsing to "biryani" (which FAISS then snaps to "Beef
# Biryani" or any other neighbour).
_QUALIFIER_WORDS = {
    "chicken", "beef", "mutton", "fish", "veggie", "veg", "veggie",
    "zinger", "crispy", "spicy", "hot", "cheese", "cheesy",
    "malai", "tikka", "bbq", "grilled", "fried", "classic",
    "mint", "strawberry", "mango", "chocolate", "vanilla", "banana",
    "plain", "garlic", "butter", "paneer", "special",
}


def _extract_deal_items(text: str) -> List[str]:
    """Return a de-duplicated list of dish phrases mentioned in ``text``.

    Scans the original utterance (Urdu, Roman, or translated English) for any
    known dish surface form and — crucially — keeps a preceding qualifier
    word when one is present. So "one chicken biryani and one burger"
    produces ``["chicken biryani", "burger"]``, not ``["biryani", "burger"]``.
    Without the qualifier, the downstream FAISS search snaps to whatever
    biryani is closest in embedding space, giving the user Beef Biryani
    when they explicitly asked for Chicken Biryani.

    Example:
        >>> _extract_deal_items("3 bandon ke liye karahi deal bana do")
        ['karahi']
        >>> _extract_deal_items("one chicken biryani and one burger")
        ['chicken biryani', 'burger']
        >>> _extract_deal_items("zinger burger aur fries deal")
        ['zinger burger', 'fries']
    """
    if not text:
        return []

    # We work on the lowered string for token scanning, but walk words so
    # qualifiers before a dish (e.g. "chicken" before "biryani") can be
    # attached in one pass.
    lowered = text.lower()

    # Build an alias → canonical map so variant hits map back to a
    # deterministic key (e.g. "kabab" → "kebab"). Sort by length desc so
    # "fried rice" beats "fries" when both would otherwise match.
    alias_to_canonical: Dict[str, str] = {}
    for canonical, variants in _DISH_ALIASES.items():
        for variant in variants:
            alias_to_canonical[variant] = canonical

    # Tokenise to ASCII-ish words; keep Urdu runs as single tokens.
    words = re.findall(r"[\u0600-\u06ff]+|[A-Za-z]+", lowered)

    phrases: List[str] = []
    canonicals_seen: Dict[str, str] = {}  # canonical → chosen phrase
    i = 0
    while i < len(words):
        match_span = 0
        matched_canonical = ""
        # Try longest multi-word alias first (e.g. "fried rice" over "fries").
        for span in (3, 2, 1):
            if i + span > len(words):
                continue
            candidate = " ".join(words[i : i + span])
            if candidate in alias_to_canonical:
                match_span = span
                matched_canonical = alias_to_canonical[candidate]
                break

        if match_span == 0:
            i += 1
            continue

        # Some tokens double as both a dish AND a qualifier for the NEXT
        # dish (e.g. "zinger" is canonical on its own, but in "zinger
        # burger" it acts as a qualifier). Avoid emitting the standalone
        # dish when we can see it's about to be consumed as a qualifier.
        if (
            match_span == 1
            and words[i] in _QUALIFIER_WORDS
            and i + 1 < len(words)
            and words[i + 1] in alias_to_canonical
            and alias_to_canonical[words[i + 1]] != matched_canonical
        ):
            i += 1
            continue

        # Attach a preceding qualifier ("chicken" before "biryani").
        dish_phrase = " ".join(words[i : i + match_span])
        if i - 1 >= 0 and words[i - 1] in _QUALIFIER_WORDS:
            dish_phrase = f"{words[i - 1]} {dish_phrase}"

        # Keep the MORE specific phrase for a canonical dish: if we already
        # have "biryani" and now see "chicken biryani", upgrade to the
        # qualified one.
        previous = canonicals_seen.get(matched_canonical)
        if previous is None:
            canonicals_seen[matched_canonical] = dish_phrase
            phrases.append(dish_phrase)
        elif len(dish_phrase) > len(previous):
            canonicals_seen[matched_canonical] = dish_phrase
            phrases = [p if p != previous else dish_phrase for p in phrases]

        i += match_span

    return phrases


def _build_deal_query(cuisine: str, count: str, items: List[str]) -> str:
    """Compose the canonical query string the deal agent understands.

    IMPORTANT: when the user named explicit items, we deliberately DO NOT
    prepend a cuisine word. Two reasons:

    1. The agent's rule-based parser already maps known dishes to a cuisine
       (biryani → Desi, burger → Fast Food) — injecting a potentially stale
       cuisine from a keyword guess can override the right answer.
    2. For mixed utterances like "biryani and burger" our cuisine sniffer
       picks whichever cuisine keyword appears first in its priority list
       — often wrong. Dropping it lets the deal agent's own logic choose
       the cuisine based on the user's actual dishes.

    We still include a cuisine hint when the user named ONLY a cuisine (no
    dishes), because without that hint the agent has nothing to go on.
    """
    items_clause = ""
    if items:
        if len(items) == 1:
            items_clause = f" with {items[0]}"
        else:
            items_clause = f" with {', '.join(items[:-1])} and {items[-1]}"

    # Items take priority: if we have them, don't let a half-guessed
    # cuisine mislead the downstream parser.
    if items and count:
        base = f"create deal for {count} people"
    elif items:
        base = "create custom deal"
    elif cuisine and count:
        base = f"create {cuisine} deal for {count} people"
    elif cuisine:
        base = f"create {cuisine} deal"
    elif count:
        base = f"create deal for {count} people"
    else:
        base = "create custom deal"

    return re.sub(r"\s+", " ", (base + items_clause)).strip()


def _has_devanagari(t): return any('\u0900' <= c <= '\u097f' for c in t)
def _has_urdu(t):
    n = sum(1 for c in t if '\u0600' <= c <= '\u06ff')
    return n > len(t.replace(' ', '')) * 0.1


# ─────────────────────────────────────────────────────────────
# INFO / "TELL ME ABOUT X" DETECTION
# ─────────────────────────────────────────────────────────────
#
# We want to catch requests like:
#   • "spring rolls ke baray mein batao"           (Roman Urdu)
#   • "fast solo A ke baray mein bataiye"          (Roman Urdu)
#   • "اسپرنگ رول کے بارے میں بتاؤ"                (Urdu script)
#   • "fast solo A کی تفصیل بتاؤ"                   (Urdu script)
#   • "tell me about spring rolls"                 (English)
#   • "what is fast solo a"                        (English)
#
# The detection runs on the RAW transcript (before translate_urdu_to_english
# mangles "بتاؤ" → "show") so the item name survives intact. It returns the
# *item phrase* only — the caller (main._detect_info_target) is responsible
# for fuzzy-resolving that phrase to a real deal_name / item_name.

_INFO_PATTERNS = [
    # ── Urdu script ──────────────────────────────────────────────
    # "X کے بارے میں بتاؤ / بتاو / بتائیے / بتاد" — most common phrasing.
    re.compile(
        r"^\s*(?P<item>.+?)\s*کے\s*بارے\s*(?:میں)?\s*"
        r"(?:بتاؤ|بتاو|بتا|بتاد|بتادو|بتاوگے|بتائیے|بتائیں|بتانا)?\s*$"
    ),
    # "X کی تفصیل" / "X کی معلومات"
    re.compile(
        r"^\s*(?P<item>.+?)\s*(?:کی\s*تفصیل|کی\s*معلومات|کا\s*تعارف|کے\s*متعلق).*$"
    ),
    # ── Roman Urdu ───────────────────────────────────────────────
    # "X ke baray mein batao", "X ky bare me btao" etc.
    re.compile(
        r"^\s*(?P<item>.+?)\s*"
        r"\b(?:ke|ky|k|kay)\b\s*"
        r"\b(?:baray|bare|baare|baaray|baary|baray)\b\s*"
        r"\b(?:mein|me|m|main)\b\s*"
        r"(?:batao|btao|bata|bataao|btaao|bataiye|btaiye|batadein|bta\s*do|"
        r"bata\s*do|btado)?\s*(?:please|plz)?\s*$",
        re.IGNORECASE,
    ),
    # "X ki tafseel batao", "X ki maloomat do"
    re.compile(
        r"^\s*(?P<item>.+?)\s*"
        r"\b(?:ki|ka|ke)\b\s*"
        r"\b(?:tafseel|tafsil|maloomat|detail|details|info|information)\b.*$",
        re.IGNORECASE,
    ),
    # ── English ──────────────────────────────────────────────────
    # "tell me about X", "describe X", "what is X", "info on X", "about X",
    # "more about X", "give me details about X".
    re.compile(
        r"^\s*(?:please\s+)?"
        r"(?:tell\s+me\s+about|give\s+me\s+(?:info|information|details)\s+"
        r"(?:on|about)|what(?:'s|\s+is|\s+are)|describe|info\s+(?:on|about)|"
        r"information\s+(?:on|about)|details?\s+(?:on|about|of)|"
        r"more\s+about|about)\s+"
        r"(?P<item>.+?)\s*(?:please)?\s*[\?\.!]?\s*$",
        re.IGNORECASE,
    ),
]


# Trigger words that *confirm* an info request even when the pattern is fuzzy.
# Used as a cheap gate so utterances like "add spring rolls" never get
# misclassified as info requests.
_INFO_TRIGGERS = [
    # Urdu
    "کے بارے میں", "کے بارے",
    "کی تفصیل", "کی معلومات",
    "کا تعارف", "کے متعلق",
    # Roman Urdu
    "baray mein", "bare mein", "baray me", "bare me", "baaray me",
    "baray main", "bare main",
    "ki tafseel", "ka tafseel", "ki maloomat",
    # English
    "tell me about", "what is ", "what's ", "what are ",
    "describe ", "about ", "info on ", "info about ",
    "information on", "information about",
    "details on", "details of", "details about",
    "more about",
]


def _strip_filler(item: str) -> str:
    """Trim common leading / trailing fillers from an extracted item phrase.

    "mujhe spring rolls" → "spring rolls"
    "the chicken tikka" → "chicken tikka"
    """
    if not item:
        return item

    t = item.strip()
    # Strip trailing punctuation.
    t = re.sub(r"[\?\.!،,]+$", "", t).strip()

    # Leading fillers in Urdu / Roman / English.
    leading_strip = [
        "mujhe", "mujhay", "mujh ko", "please", "plz",
        "tell me", "can you", "could you", "would you",
        "kindly",
        "مجھے", "براہ مہربانی",
    ]
    lowered = t.lower()
    for prefix in sorted(leading_strip, key=len, reverse=True):
        if lowered.startswith(prefix + " "):
            t = t[len(prefix):].strip()
            lowered = t.lower()

    # "the / this / that X" → "X"
    t = re.sub(
        r"^(?:the|this|that|a|an)\s+",
        "",
        t,
        flags=re.IGNORECASE,
    )

    # Users routinely include "deal" / "item" / "dish" as a descriptor:
    #   "tell me about the deal with the fast solo" → "fast solo"
    #   "tell me about the dish spring rolls"       → "spring rolls"
    # Strip these wrappers so fuzzy menu/deal lookup has a clean item phrase.
    t = re.sub(
        r"^(?:deal|offer|combo|package|item|dish|menu\s+item)\s+"
        r"(?:with|for|called|named|about)?\s*"
        r"(?:the\s+)?",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    t = re.sub(
        r"^(?:the\s+)?(?:deal|offer|combo|package|dish|item)\s+(?:of\s+)?",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()

    # Collapse whitespace.
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _looks_like_order_status_question(raw: str, lowered: str) -> bool:
    """True if the user is asking for ETA / tracking / progress, not menu info."""
    if not raw and not lowered:
        return False
    # Common English normalisations from the translator.
    if any(
        p in lowered
        for p in (
            "order status",
            "status of my order",
            "track my order",
            "track order",
            "where is my order",
            "order tracking",
            "delivery time",
            "how long",
            "time left",
            "how much time",
        )
    ):
        return True
    if "progress" in lowered and "order" in lowered:
        return True
    if "track" in lowered and (
        "order" in lowered or "delivery" in lowered or "آرڈر" in raw or "آڈر" in raw
    ):
        return True
    # Urdu / mixed fragments (raw transcript).
    if any(
        w in raw
        for w in (
            "آرڈر",
            "اڈر",
            "آڈر",
            "میرا order",
            "میرے order",
            "order track",
        )
    ) and any(
        w in raw or w in lowered
        for w in (
            "track",
            "progress",
            "پروگریس",
            "ستیٹس",
            "status",
            "کتنا",
            "ٹائم",
            "وقت",
            "time",
            "dair",
            "waqt",
        )
    ):
        return True
    return False


def detect_info_intent(text: str):
    """Return {"is_info": True, "item": <phrase>} if the utterance is an
    info / describe request, else None.

    Runs on the RAW transcript so the Urdu item name is preserved before
    ``translate_urdu_to_english`` rewrites "بتاؤ" → "show". For English
    transcripts the same function works because the English branch of the
    pattern list matches "tell me about X" etc.

    The returned ``item`` phrase is already trimmed of common fillers but is
    NOT resolved against the menu / deals DB — that's the caller's job
    (``main._detect_info_target`` does fuzzy resolution via
    ``_resolve_cart_item_name``).
    """
    if not text or not text.strip():
        return None

    # Whisper often wraps translated output in literal quotes
    # (e.g. `' "Tell me about the chicken burger."'`). The regex patterns
    # below are anchored with `^` so the leading quote silently blocks every
    # match. Strip all leading/trailing decorative punctuation before the
    # detector runs so the user never notices the quirk.
    raw = text.strip()
    raw = raw.strip('"\u201C\u201D\u2018\u2019\'`“”‘’')  # ASCII + smart quotes
    raw = raw.strip()
    # Also drop trailing terminal punctuation the regex would otherwise catch
    # — redundant but keeps the cleaned string human-readable for logs.
    raw = raw.rstrip(".?!،,؟ ")
    if not raw:
        return None
    lowered = raw.lower()

    # Cheap gate: the utterance must contain at least one info trigger.
    # This avoids false positives on "show me burgers", "add biryani", etc.
    if not any(trig in lowered or trig in raw for trig in _INFO_TRIGGERS):
        return None

    # "What is the status of my order?" matches the English "what is X" info
    # pattern but must route to order tracking, not describe_item.
    if _looks_like_order_status_question(raw, lowered):
        return None

    # Never treat cart / order / deal-creation utterances as info requests,
    # even if they incidentally contain "about" etc. This guards against
    # phrases like "about to order" or "tell me what's in my cart".
    suppressors = [
        "add to cart", "cart me", "cart mein", "کارٹ میں",
        "place order", "checkout", "pay ", "payment",
        "deal banao", "deal bana do", "ڈیل بنا",
        "remove ", "hatao", "ہٹا",
    ]
    if any(s in lowered for s in suppressors):
        return None

    # Also skip custom-deal requests — they have their own dedicated router.
    if _is_custom_deal_query(raw):
        return None

    for pattern in _INFO_PATTERNS:
        m = pattern.match(raw)
        if not m:
            continue
        item = (m.group("item") or "").strip()
        item = _strip_filler(item)
        if not item:
            continue
        # Ignore if what's left is a bare filler like "it" / "yeh" / "ye".
        if item.lower() in {"it", "this", "that", "yeh", "ye", "یہ", "وہ"}:
            continue
        return {"is_info": True, "item": item}

    return None


def detect_custom_deal_intent(text: str):
    """Public helper used by /voice_chat to short-circuit ambiguous deal queries.

    Returns a dict {"is_custom_deal": bool, "cuisine": str, "people": str|None,
    "query": str} or None if the text is clearly not a custom-deal request.

    Designed to be called on BOTH the raw Whisper transcript (Urdu/Hindi)
    AND the post-translation English text — whichever path triggers wins.
    """
    if not text or not text.strip():
        return None

    if not _is_custom_deal_query(text):
        return None

    people, cuisine = _extract_deal_info(text)
    people_str = people if people else None
    items = _extract_deal_items(text)

    query = _build_deal_query(cuisine, people_str or "", items)

    return {
        "is_custom_deal": True,
        "cuisine": cuisine or "",
        "people": people_str,
        "items": items,
        "query": query,
    }


def translate_urdu_to_english(text: str) -> str:
    if not text or not text.strip():
        return ""

    result = text.strip()
    print(f"[Translator] Input: '{_safe_log_text(result)}'")

    # ── Step 1: Custom deal detection FIRST ───────────────────
    if _is_custom_deal_query(result):
        count, cuisine = _extract_deal_info(result)
        items = _extract_deal_items(result)
        query = _build_deal_query(cuisine, count, items)
        print(f"[Translator] Custom deal -> '{_safe_log_text(query)}'")
        return query

    # ── Step 2: English-in-Urdu-script (Whisper mis-hearings) ─
    for urdu, eng in sorted(ENGLISH_IN_URDU_SCRIPT.items(),
                            key=lambda x: len(x[0]), reverse=True):
        result = result.replace(urdu, f" {eng} ")

    # ── Step 3: Hindi script ───────────────────────────────────
    if _has_devanagari(result):
        for h, e in sorted(HINDI_MAP.items(), key=lambda x: len(x[0]), reverse=True):
            result = result.replace(h, f" {e} ")

    # ── Step 4: Urdu script ────────────────────────────────────
    if _has_urdu(result):
        for u, e in sorted(URDU_SCRIPT_MAP.items(), key=lambda x: len(x[0]), reverse=True):
            result = result.replace(u, f" {e} ")

    # ── Step 5: Roman Urdu ─────────────────────────────────────
    rl = result.lower()
    for r, e in sorted(ROMAN_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        rl = rl.replace(r, f" {e} ")
    result = rl

    # ── Step 6: Clean ──────────────────────────────────────────
    result = re.sub(r'\s+', ' ', result).strip()
    # ASR often writes کنگ/Kung splits as stray "کن" fragments + stray Urdu glyphs.
    result = re.sub(
        r"(?i)\b\d*\s*(?:chicken|چکن)\s*گ\s*(?:پاؤ|pao)\b",
        "kung pao",
        result,
    )

    # ── Step 7: Optional LLM fallback (disabled by default) ───
    if TRANSLATOR_LLM_FALLBACK_ENABLED:
        non_ascii = sum(1 for c in result if ord(c) > 127)
        total     = len(result.replace(' ', ''))
        if total > 0 and non_ascii / total > 0.4:
            print(f"[Translator] Still unclear, trying LLM...")
            result = _llm_translate(text)

    print(f"[Translator] Output: '{_safe_log_text(result)}'")
    return result if result else text


def _llm_translate(text: str) -> str:
    try:
        from langchain_groq import ChatGroq
        from langchain_core.messages import HumanMessage
        llm = ChatGroq(model="llama-3.1-8b-instant",
                       api_key=os.getenv("GROQ_API_KEY"), temperature=0)
        prompt = (
            "Translate this Urdu/Roman Urdu restaurant order to English. "
            "Output ONLY the English translation, one line.\n"
            "Key: 'ek/aik'=1, 'do'=2, 'teen'=3, 'dalo/add'=add, "
            "'dikhao/show'=show, 'hatao'=remove, 'deal banao'=create deal, "
            "'ke liye'=for, 'logon/bando/afraad/mundho'=people, "
            "'gaad/card'=card, 'addar/oddar'=order, "
            "'blais/place'=place, 'chakoup/checkout'=checkout, "
            "'pahment/payment'=payment, 'billah/bill'=bill\n"
            f"Input: {text}\n"
            "English:"
        )
        out = llm.invoke([HumanMessage(content=prompt)]).content.strip()
        return out.split('\n')[0]
    except Exception as e:
        print(f"[Translator] LLM error: {e}")
        return text