# 🔍 Khadim Project – Full Code Review
> Reviewed: March 2026 | Reviewer: GitHub Copilot  
> Status: Backend running, Flutter UI ready, Integration in progress

---

## 📁 Project Structure (What Exists)

```
Khadim/
├── RAG + agents/               ← Python Backend (FastAPI)
│   ├── main.py                 ← App entry, top-level endpoints
│   ├── auth/                   ← Login, Signup, JWT
│   ├── cart/                   ← Cart management
│   ├── orders/                 ← Order placement, kitchen tasks
│   ├── chat/                   ← AI chat agent (Groq LLM)
│   ├── voice/                  ← Whisper transcription, TTS
│   ├── retrieval/              ← RAG + FAISS vector search
│   ├── infrastructure/         ← DB connections, config
│   ├── monitoring/             ← Health/dashboard (unused in API)
│   ├── .env                    ← Secrets (DB URL, API keys)
│   └── requirements.txt
│
├── App/                        ← Flutter Frontend
│   ├── lib/
│   │   ├── main.dart
│   │   ├── screens/            ← All UI screens
│   │   ├── services/           ← API service layer
│   │   ├── providers/          ← State management
│   │   └── models/
│   └── pubspec.yaml
│
└── voice/                      ← Fine-tuned Whisper model files
    ├── whisper_urdu_final/     ← Model weights + tokenizer
    └── empty.wav               ← Warmup audio file
```

---

## 🔄 How the System Works (Workflow)

### 1. User Opens App (Flutter)
```
Flutter App starts
    → Checks if user is logged in (token stored locally)
    → If not → shows Login/Signup screen
    → If yes → goes to Home/Menu screen
```

### 2. Login / Signup Flow
```
Flutter POST /auth/signup  or  POST /auth/login
    → FastAPI (auth/auth_routes.py)
    → Checks credentials against PostgreSQL (auth.app_users table)
    → Returns JWT token
    → Flutter stores token locally
    → All future requests include: Authorization: Bearer <token>
```

### 3. Browse Menu Flow
```
Flutter GET /menu
    → FastAPI (main.py → get_full_menu)
    → Queries PostgreSQL (menu_item table)
    → Returns list of items with prices, images, descriptions
    → Flutter displays in menu screen
```

### 4. Add to Cart Flow
```
Flutter POST /cart/items
    → FastAPI (cart/cart_routes.py)
    → Validates JWT token (get_current_user)
    → Checks item exists in DB and gets server-side price (security!)
    → Inserts into cart_items table
    → Returns updated cart
```

### 5. Place Order Flow
```
Flutter POST /orders/place_order
    → FastAPI (orders/order_routes.py → orders_service.py)
    → Locks active cart (FOR UPDATE - prevents double orders)
    → Calculates subtotal + tax + delivery fee
    → Creates order in orders table
    → Creates kitchen_tasks for each item
    → Assigns chef based on workload (least busy chef first)
    → Marks cart as inactive
    → Returns order ID, total, estimated prep time
```

### 6. Text Chat Flow
```
Flutter POST /chat  { "message": "بریانی کتنے کی ہے؟" }
    → FastAPI (main.py → chat_text_endpoint)
    → Groq LLM (llama-3.1-8b-instant) decides: search_menu tool needed
    → Backend queries PostgreSQL for matching items
    → Returns formatted Urdu text response
    → Flutter displays in chat bubble
```

### 7. Voice Chat Flow
```
Flutter records audio → POST /voice_chat (multipart audio file)
    → FastAPI (main.py → chat_voice_endpoint)
    → voice/transcribe.py: Whisper model converts audio → Urdu text
    → Same pipeline as Text Chat above
    → Returns transcript + reply
    → Flutter displays text (TTS not yet connected)
```

---

## ✅ What's Working Well

| Component | Assessment |
|-----------|------------|
| FastAPI structure | Clean, well-organized folders |
| Auth system (JWT) | Solid implementation with proper hashing |
| Cart logic | Good - server-side price validation (security win!) |
| Order placement | Clean with idempotency check (no double orders) |
| Chef assignment | Smart workload-based assignment algorithm |
| Kitchen tasks | Auto-created with station routing (GRILL, STOVE, etc.) |
| Whisper integration | Connected and loading from correct path |
| RAG retrieval | FAISS vector search implemented |
| Flutter structure | Well-organized screens by feature |
| Voice packages | flutter_sound, permission_handler already added |

---

## 🚨 Bugs (Must Fix)

### Bug 1: Missing `langchain-groq` in requirements.txt
**File:** `requirements.txt`  
**Impact:** 🔴 CRITICAL – Chat agent crashes on import
```python
# chat/chat_agent.py line 4 - uses this
from langchain_groq import ChatGroq
# But langchain-groq is NOT in requirements.txt!
```
**Fix:**
```
# Add to requirements.txt under Agents section
langchain-groq
```

---

### Bug 2: Wrong passlib scheme
**File:** `auth/auth_utils.py` line 12  
**Impact:** 🔴 CRITICAL – Signup/Login crashes
```python
# Currently uses argon2 scheme
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
# But requirements.txt has passlib[bcrypt] - argon2 backend not installed!
```
**Fix – Option A:** Change scheme to match installed package:
```python
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
```
**Fix – Option B:** Install argon2 support:
```
# Add to requirements.txt
argon2-cffi
```

---

### Bug 3: Dead code in order_routes.py
**File:** `orders/order_routes.py` lines 78-477  
**Impact:** 🟠 HIGH – All code after `return res` never executes
```python
@router.post("/place_order")
def place_order(req, current_user):
    res = place_order_sync(...)
    if not res.get("success"):
        raise HTTPException(...)
    return res          # ← function ends HERE
    user_id = ...       # ← DEAD CODE - never runs (lines 78-477)
    with SQL_ENGINE.begin() as conn:
        ...             # ← entire second implementation unreachable
```
**Fix:** Delete everything after `return res` in the `place_order` function. The `orders_service.py` already handles the full logic correctly.

---

### Bug 4: `place_order_sync` signature mismatch
**File:** `orders/order_routes.py` vs `orders/orders_service.py`  
**Impact:** 🔴 CRITICAL – Order placement fails
```python
# order_routes.py calls it with user_id:
place_order_sync(user_id=user_id, delivery_address=..., ...)

# orders_service.py expects cart_id as first param:
def place_order_sync(cart_id: str, delivery_address=..., ...):
# Missing: it never received user_id to look up the cart!
```
**Fix:** Update `orders_service.py` to accept `user_id` and look up the active cart inside:
```python
def place_order_sync(user_id: str, delivery_address: str = "N/A", ...):
    # First get active cart for this user
    with SQL_ENGINE.connect() as conn:
        cart_row = conn.execute(
            text("SELECT cart_id FROM cart WHERE user_id=:uid AND status='active'"),
            {"uid": user_id}
        ).fetchone()
    cart_id = str(cart_row[0])
    # ... rest of logic
```

---

### Bug 5: `flutter_secure_storage` in wrong section
**File:** `App/pubspec.yaml` line 38  
**Impact:** 🟠 HIGH – Token storage won't work in production builds
```yaml
dev_dependencies:          # ← WRONG! dev_dependencies excluded from release
  flutter_secure_storage: ^9.2.2
```
**Fix:** Move to `dependencies`:
```yaml
dependencies:
  flutter_secure_storage: ^9.2.2   # ← Correct placement
```

---

## ⚠️ Issues & Improvements (Non-Breaking)

### Issue 1: Two database connection systems
**Files:** `infrastructure/config.py` (psycopg2) + `infrastructure/db.py` (SQLAlchemy)  
**Impact:** 🟡 MEDIUM – Confusing, inconsistent
- Old agents use `database_connection.py` (raw psycopg2)
- New FastAPI code uses `db.py` (SQLAlchemy)
- Both work but maintainability suffers

**Suggestion:** Gradually migrate old agents to use `SQL_ENGINE` from `db.py`

---

### Issue 2: Fake cart tools in chat agent
**File:** `chat/chat_agent.py` lines 65-80  
**Impact:** 🟡 MEDIUM – Voice/chat ordering via agent doesn't actually work
```python
@tool
def add_to_cart(item_name: str, quantity: int = 1) -> str:
    return f"Added {quantity}x {item_name} to your cart."  # ← MOCK! Not real!

@tool
def show_cart() -> str:
    return "Your cart is empty."  # ← Always returns empty!
```
**Suggestion:** Connect these tools to the actual cart DB logic when implementing voice ordering.

---

### Issue 3: `app.on_event("startup")` deprecated
**File:** `main.py` line 74  
**Impact:** 🟢 LOW – Works but shows deprecation warning in newer FastAPI
```python
@app.on_event("startup")   # Deprecated
def warmup_whisper():
```
**Suggestion (future cleanup):**
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    warmup_whisper()     # runs on startup
    yield
    # cleanup on shutdown (if needed)

app = FastAPI(lifespan=lifespan)
```

---

### Issue 4: CORS too open
**File:** `main.py` line 33  
**Impact:** 🟢 LOW for development, 🔴 HIGH for production
```python
allow_origins=["*"]   # Any domain can call your API
```
**Suggestion (before deployment):**
```python
allow_origins=["http://localhost:3000", "https://yourdomain.com"]
```

---

### Issue 5: Temp voice files never deleted
**File:** `main.py` line 335 (voice_chat endpoint)  
**Impact:** 🟡 MEDIUM – Disk fills up over time
```python
audio_path = f"temp_voice/{file.filename}"
# File is written but never deleted after transcription
```
**Suggestion:**
```python
import os
try:
    transcript = transcribe_audio(audio_path)
finally:
    if os.path.exists(audio_path):
        os.remove(audio_path)   # Always cleanup
```

---

### Issue 6: `load_dotenv()` not called in main.py
**File:** `main.py`  
**Impact:** 🟢 LOW – Works because sub-modules call it, but fragile
```python
from dotenv import load_dotenv   # imported but never called!
```
**Suggestion:** Add `load_dotenv()` call at top of main.py for clarity.

---

### Issue 7: Duplicate response formatting functions
**File:** `main.py`  
**Impact:** 🟢 LOW – Code smell
- `format_items_urdu()` (line 43) and `format_results_response()` (line 188) do similar things
- Both format menu items/deals for display
- Both used in same endpoints

**Suggestion:** Merge into one function with a `language` parameter.

---

## 📦 Requirements.txt – Missing Packages

```txt
# Currently missing - must add:
langchain-groq          # Used by chat/chat_agent.py
argon2-cffi             # If keeping argon2 in auth_utils.py
```

**Install now:**
```bash
pip install langchain-groq argon2-cffi
```

---

## 🏗️ What's Not Yet Built

| Feature | Status | Who Should Build |
|---------|--------|-----------------|
| Voice TTS response (speak back) | ❌ Not connected | Voice engineer |
| WebSocket (real-time order tracking) | ❌ Not started | Backend |
| Payment integration | ❌ Not started | Backend |
| Order status updates to Flutter | ❌ Not started | Backend + Flutter |
| Flutter voice recording UI | ⚠️ Packages added, UI missing | Flutter |
| Admin portal | ❌ Not started | Backend + Flutter |
| Notifications | ❌ Not started | Backend |
| Personalization agent | ❌ Not started | Backend |

---

## 🎯 Priority Fix Order

```
1. CRITICAL - Fix NOW (app won't work without these):
   □ pip install langchain-groq argon2-cffi
   □ Add langchain-groq to requirements.txt
   □ Fix passlib scheme (bcrypt vs argon2)
   □ Fix place_order_sync signature mismatch (Bug 4)

2. HIGH - Fix before testing order flow:
   □ Delete dead code in order_routes.py (Bug 3)
   □ Move flutter_secure_storage to dependencies (Bug 5)

3. MEDIUM - Fix before adding new features:
   □ Delete temp voice files after transcription (Issue 5)
   □ Connect real cart tools in chat agent (Issue 2)

4. LOW - Clean up before final submission:
   □ Add load_dotenv() in main.py (Issue 6)
   □ Merge duplicate format functions (Issue 7)
   □ Update deprecated on_event to lifespan (Issue 3)
   □ Restrict CORS origins (Issue 4)
```

---

## 🚀 How to Run

### Backend:
```bash
cd "d:\FAST\FYP\Khadim\RAG + agents"
venv\Scripts\activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Then open: `http://localhost:8000/docs`

### Flutter:
```bash
cd "d:\FAST\FYP\Khadim\App"
flutter pub get
flutter run
```

### Database (PostgreSQL must be running):
```
Host: localhost:5432
Database: restaurantDB
User: postgres
Password: 7980  (from .env)
```

---

## 📊 Overall Assessment

| Area | Score | Notes |
|------|-------|-------|
| Architecture | 8/10 | Clean separation, good structure |
| Backend Code Quality | 7/10 | Good patterns, few critical bugs |
| Security | 6/10 | JWT good, CORS open, fix before prod |
| Flutter Structure | 8/10 | Well organized |
| Voice Integration | 5/10 | Whisper loads, TTS not connected |
| Agent Integration | 4/10 | Fake cart tools, chat not wired to real cart |
| Test Coverage | 2/10 | No tests written yet |
| Documentation | 7/10 | Good inline comments |

**Overall: 6/10 – Solid foundation, fix the 4 critical bugs and it's ready for full testing**
