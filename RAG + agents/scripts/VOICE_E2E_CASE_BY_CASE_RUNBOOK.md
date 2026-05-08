# Voice E2E — case-by-case manual runbook (customer app)

Use this **one case at a time**: speak → watch **SnackBar** (transcript + intent/tools) → watch **screen / cart**.

## Pipeline (what actually happens)

1. **Mic** records audio → app uploads to **`POST /voice_chat`** (Urdu path).
2. **Server** runs ASR → **transcript** (often mixed Urdu/English after translation).
3. **Server** infers **intent** + **tool_calls** (and may return **menu_items** / **deals** in JSON).
4. **App** (`VoiceCommandService`) runs each tool: **nav callbacks**, **CartService** add/remove, **checkout** opening, etc.
5. You see **SnackBar** with what the server routed, then **TTS** + **navigation** if a tool requested it.

**Urdu mic button** = full pipeline above. **English mic** = device speech-to-text → **`/chat`** text (no ASR on server); behavior should match after text is known.

---

## Before you start

- API running; phone/emulator can reach `API_BASE_URL` (same Wi‑Fi as PC, or emulator `10.0.2.2` for host).
- Logged in if your API requires auth for `/voice_chat`.
- Customer flavor (`AppFlavor.customer`).

---

## Case 1 — Transcript + intent visible (sanity)

**Say (Urdu):**  
*"Fast food deals dikhao do log ke liye."*

**Expect**

- SnackBar line 1: your words (or ASR variant).
- SnackBar line 2: `Intent: search_deal` (or similar) and tools like `search_deal`.
- App: **Deals** opens or filters toward fast food / 2 people (per `VoiceNavCallbacks.openDealsWithFilter`).

**Pass if:** intent line appears and deals UI reacts; **Fail if:** empty transcript or timeout.

---

## Case 2 — Menu browse (navigation)

**Say:**  
*"Chinese menu dikhao."*

**Expect**

- Tools include `search_menu` or navigation to menu tab with Chinese filter.
- **Menu** screen with **Chinese** chip/filter.

---

## Case 3 — Add item to cart (delivery cart)

**Say:**  
*"Zinger burger cart mein add karo."*

**Expect**

- Tools: `add_to_cart` with item name resolved.
- SnackBar shows **Tools: add_to_cart** (possibly after reorder in pipeline).
- Cart count increases OR app navigates to **cart** after add (handler may `openCart` on added_to_cart — check `VoiceOrderHandler._handleResult`).

---

## Case 4 — Multiple adds in one utterance

**Say:**  
*"Biryani aur cola cart mein daalo."*

**Expect**

- Multiple `add_to_cart` in tool list (or one LLM call that expands).
- TTS confirmation; cart has both if names resolved.

---

## Case 5 — Show cart

**Say:**  
*"Cart dikhao"* / *"Show cart"*

**Expect**

- `show_cart` tool → **`openCart()`** — **Cart** screen visible.

---

## Case 6 — Remove from cart

**Say:**  
*"Cola cart se hata do."*

**Expect**

- `remove_from_cart` → item removed via cart API; TTS confirms.

(Requires cola already in cart — do Case 3/4 first.)

---

## Case 7 — Checkout / place order (delivery)

**Say:**  
*"Place order COD se."*

**Expect**

- `place_order` with **`COD`** / cash flavor.
- **`openCheckout(paymentMethod: ...)`** — **checkout / payment** screen opens (non-kiosk).

---

## Case 8 — Payment wording conflict

**Say:**  
*"Order place karo card se aur COD dono."*

**Expect**

- Backend or client normalizes to **ask** one method; SnackBar tools may show **`ASK`** / `settle_payment` with ask — user should be prompted, not two contradictory payments.

---

## Case 9 — Custom deal path

**Say:**  
*"Do logon ke liye desi custom deal banao."*

**Expect**

- Tools may include `create_custom_deal` OR backend routes to custom-deal flow; custom deal UI / confirmation.

(Depends on `_route_custom_deal` vs search_deal — both may appear in SnackBar.)

---

## Case 10 — Order status

**Say:**  
*"Mera order kahan hai?"* / *"Order status"*

**Expect**

- `get_order_status` / spoken summary; may use global voice handler if intercepted.

---

## Case 11 — Navigate (tab / screen)

**Say:**  
*"Orders screen kholo."*

**Expect**

- `navigate_to` with `screen: orders` → **`openOrders()`**.

---

## Case 12 — Favourites (if backend emits tool)

**Say:**  
*"Cheeseburger ko favourite mein add karo."*

**Expect**

- `manage_favourites` with add; heart/state updates if IDs resolved.

---

## How this differs from the Python `test_delivery_scenarios.py` script

| Script (`/chat`) | Real voice (`/voice_chat`) |
|-------------------|----------------------------|
| Sends **text only** — no mic, no ASR. | Sends **audio** — ASR can mis-hear. |
| Good for **fast** API regression. | This runbook is the **real user** test. |
| Output in **terminal**. | Output on **phone**: SnackBar + screens + TTS. |

Run script for speed; run **this runbook** when you want to verify **the full chain** including **ASR** and **Flutter** actions.

---

## Order of execution (recommended)

Do **Case 1 → 3 → 4 → 5 → 6** first (deals/menu → add → show → remove).  
Then **7 → 8** (checkout / payment).  
Then **9–12** as needed.

Record **Pass/Fail** and a one-line note (e.g. “ASR heard X instead of Y”) for each case.
