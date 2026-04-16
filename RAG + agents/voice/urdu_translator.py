"""
voice/urdu_translator.py
Normalizes Whisper output to English for keyword matching.
"""

import re, os
from dotenv import load_dotenv
load_dotenv()

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
    "کارٹ":    "cart",
    "منیو":    "menu",  "منیوم":"menu",   "مینیو":"menu",
    "میلیو":   "menu",
    "ڈیل":     "deal",  "ڈیلز": "deals", "ڈیم": "deal",
    "لکھو":    "write",  # NEW: handle "لکھو" (write) as a deal request variant
    # ── Food ─────────────────────────────────────────────────
    "فرائز":   "fries", "فرائیز":"fries",
    "چکن":     "chicken","چیکن": "chicken","جیکن": "chicken","چکا": "chicken","کن": "chicken","برگر": "burger","بردر": "burger",
    "چکر":     "chicken","کولا": "cola",  "ڈرنک": "drink",
    "نگٹس":    "nuggets","نیگٹس":"nuggets","نیکٹس":"nuggets","نیگسٹ":"nuggets","نیکٹ":"nuggets","نیگٹسٹو":"nuggets",
    "زنگر":    "zinger","زیگر": "zinger","زینگر":"zinger","زیلگر":"zinger",
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
    "کارڈ سے پیمنٹ":             "card payment",
    "کارڈ سے":                   "card payment",
    "کارڈ کے ذریعے":             "card payment",
    "کارڈ پیمنٹ":                "card payment",
    "کیش آن ڈیلیوری":           "cash on delivery",
    "کیش سے":                    "cash payment",
    "کیش پیمنٹ":                 "cash payment",
    "نقد ادائیگی":               "cash payment",
    # ── Show cart ────────────────────────────────────────────
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
    "شامل کر دو":                "add",
    "ڈالو":                      "add",
    "ڈال دو":                    "add",
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
    "زنگر":                      "zinger burger",
    "زندھر":                     "zinger burger",
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
    "zinger":                     "zinger burger",
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
    """Only trigger custom deal if explicitly asking to CREATE/MAKE a deal.
    Don't trigger on 'show' or 'dikhao' commands."""
    lowered = text.lower()

    # If this is a favourites command, do not hijack it as create-custom-deal.
    if any(w in lowered for w in ["favourite", "favorite", "favourites", "favorites", "فریوٹس", "فیوٹس", "فیورٹس", "فیوڈز", "فریورٹس", "پھرائیوٹس", "فریوٹ", "فریوٹنی"]):
        return False

    # If user says "show" or "dikhao", it's NOT a custom deal request
    if any(w in lowered for w in ["دکھاؤ", "دکھائیں", "دیکھو", "بتاؤ", "show", "dikhao", "batao"]):
        return False
    
    # Only trigger if explicit "create/make deal" patterns
    explicit_create_patterns = [
        "ڈیل بنا", "ڈیل چاہیے", "ڈیل پیدا",
        "deal banao", "deal bana do", "deal chahiye",
        "custom deal", "apni deal", "custom bill", "create the bill", "make the bill"
    ]
    return any(p in lowered for p in explicit_create_patterns)

def _extract_deal_info(text: str):
    m = re.search(
        r'(ایک|دو|تین|چار|پانچ|چھ|1|2|3|4|5|6)\s*'
        r'(?:پرسن|پرسند|پرسندوں|بندوں|بندے|لوگوں|مندھوں|مندوں|افراد|person|people|log)',
        text
    )
    count = _COUNT_MAP.get(m.group(1), "") if m else ""
    if not count:
        # Fallback for utterances like "chinese deal show 2" (bare number near deal phrase).
        m2 = re.search(r'\b(1|2|3|4|5|6|ek|do|teen|chaar|paanch)\b', text.lower())
        if m2 and ("deal" in text.lower() or "ڈیل" in text):
            count = _COUNT_MAP.get(m2.group(1), m2.group(1))
    t = text.lower()
    cuisine = ""
    if any(w in t for w in ["چائنیز","چینیز","chinese","چینی"]):  cuisine = "chinese"
    elif any(w in t for w in ["دیسی","desi","پاکستانی"]):          cuisine = "desi"
    elif any(w in t for w in ["بی بی کیو","bbq","ٹکہ"]):          cuisine = "bbq"
    elif any(w in t for w in ["فاسٹ","fast","فاس فوٹ","فاصد خوب","فاصد","فاسد خوب","زنگر","برگر"]): cuisine = "fast food"
    return count, cuisine


def _has_devanagari(t): return any('\u0900' <= c <= '\u097f' for c in t)
def _has_urdu(t):
    n = sum(1 for c in t if '\u0600' <= c <= '\u06ff')
    return n > len(t.replace(' ', '')) * 0.1


def translate_urdu_to_english(text: str) -> str:
    if not text or not text.strip():
        return ""

    result = text.strip()
    print(f"[Translator] Input: '{result}'")

    # ── Step 1: Custom deal detection FIRST ───────────────────
    if _is_custom_deal_query(result):
        count, cuisine = _extract_deal_info(result)
        if cuisine and count:
            query = f"create {cuisine} deal for {count} people"
        elif cuisine:
            query = f"create {cuisine} deal"
        else:
            query = "create custom deal"
        query = re.sub(r'\s+', ' ', query)
        print(f"[Translator] Custom deal → '{query}'")
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

    # ── Step 7: LLM only if still mostly non-ASCII ────────────
    non_ascii = sum(1 for c in result if ord(c) > 127)
    total     = len(result.replace(' ', ''))
    if total > 0 and non_ascii / total > 0.4:
        print(f"[Translator] Still unclear, trying LLM...")
        result = _llm_translate(text)

    print(f"[Translator] Output: '{result}'")
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