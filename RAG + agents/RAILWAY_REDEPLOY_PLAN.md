# Khadim backend — Railway redeploy plan (do in order)

Keep your **existing Railway project** unless you want a new public URL. Prefer **edit variables + redeploy**.

---

## Phase A — Postgres

1. Open **Railway → your project → Postgres** (or add **PostgreSQL** if missing).
2. Copy **internal** `DATABASE_URL` (reference variable `${{Postgres.DATABASE_URL}}` or the raw URL from the Postgres service **Variables** tab).
3. On the **Khadim API service → Variables**, set **`DATABASE_URL`** to that value (literal copy is fine if Railway reference does not resolve).
4. **Restore schema + data** using your canonical dump (e.g. `Database/db_new(USE THIS).sql` or `pg_restore` for custom format).
5. **Admin user** (if you use `admin@gmail.com` / docs password): run the `INSERT` comment at the top of `admin/admin_routes.py` against prod DB, or create the user and align email with `ADMIN_EMAIL`.

**Verify:** From your machine (or Railway shell), `psql` / GUI: `SELECT COUNT(*) FROM menu_item;`

---

## Phase B — Redis

1. Add **Redis** plugin (or use existing).
2. Railway usually provides **`REDIS_URL`**. Copy it into the **Khadim** service variables as **`REDIS_URL`**.
3. Optionally also set **`REDIS_HOST`** and **`REDIS_PORT`** from the Redis **private** hostname/port (if Railway shows them). The codebase now uses **`infrastructure/redis_client.get_sync_redis()`** everywhere important: **`REDIS_URL` wins** if set.

**Verify:** Deploy Khadim; check logs for Redis connection errors when you use features that publish to Redis.

---

## Phase C — API service (Khadim)

| Variable | Purpose |
|----------|---------|
| **`DATABASE_URL`** | Required (Postgres). |
| **`REDIS_URL`** | Recommended (single source for Redis). |
| **`GROQ_API_KEY`** | Chat / tools / personalization LLM. |
| **`GROQ_API2_KEY`** | Some admin AI endpoints (`admin_routes.py`). |
| **`ELEVENLABS_API_KEY`** | Voice STT when `STT_BACKEND=elevenlabs` (default). |
| **`STT_BACKEND`** | `elevenlabs` or `whisper` (Whisper needs model + resources). |
| **`JWT_SECRET`** / algo / expiry | Match `auth` if you changed from defaults. |
| **`PORT`** | Set by Railway — do not override unless you know why. |

Deploy from **Git** (push) or **Dockerfile** root = `RAG + agents` repo.

**Verify:**

- `GET https://YOUR_PUBLIC_URL/health`
- `GET https://YOUR_PUBLIC_URL/docs`
- `GET https://YOUR_PUBLIC_URL/menu`
- `POST https://YOUR_PUBLIC_URL/auth/login` with a known user.

---

## Phase D — Flutter + Netlify (client)

1. Copy **exact** public API URL from **Khadim → Networking** (must match HTTPS host Railway shows).
2. Rebuild APKs and admin web:

```text
flutter build apk --release --flavor customer --split-per-abi --dart-define=API_BASE_URL=https://YOUR_PUBLIC_URL
flutter build apk --release --flavor kiosk --split-per-abi --dart-define=API_BASE_URL=https://YOUR_PUBLIC_URL
flutter build web --release -t lib/main_admin.dart --base-href /admin/ --dart-define=API_BASE_URL=https://YOUR_PUBLIC_URL
```

3. Copy **`install-site`**: APKs → `apk/`, `build/web/*` → `install-site/admin/`, deploy folder to Netlify.

---

## Phase E — Known gaps (not Railway wiring)

| Issue | Fix |
|-------|-----|
| **Menu photos 404** | DB `image_url` points at `assets/...`; API does not serve files. Host images on CDN/S3 **or** add static routes + bake files into deploy. |
| **Voice 503** | `VOICE_ENABLED` false if STT fails to load; set **`ELEVENLABS_API_KEY`** or `STT_BACKEND=whisper` + model. |
| **Admin 401** | User missing or wrong password in **`auth.app_users`** on prod. |

---

## Delete vs modify?

- **Modify** existing Railway services and **redeploy** for normal fixes.
- **Delete** a service/project only if you accept losing data/URL and you have backups.

---

## Code change in this repo (Redis)

All of these use **`get_sync_redis()`** so **`REDIS_URL`** works consistently:

- `main.py`
- `infrastructure/redis_connection.py`
- `orders/order_coordinator.py`
- `kitchen/kitchen_dashboard.py`
