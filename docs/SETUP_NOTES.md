# Team Setup Notes
> Read this every time you pull new code.

---

## 1. Flutter App — Change Your IP (EVERY PULL)
**File:** `App/lib/services/api_config.dart`

Change the IP to YOUR machine's local WiFi IP:
```dart
static String baseUrl = "http://<YOUR_IP>:8000";
```

Find your IP:
```powershell
ipconfig
# Look for "IPv4 Address" under your WiFi adapter
```

> ⚠️ This file WILL conflict on every pull because everyone has a different IP.
> After pulling, just fix it to your own IP and continue.

---

## 2. Create Your `.env` File (FIRST TIME ONLY)
**Location:** `RAG + agents/.env`

This file is NOT on git (intentionally). Create it manually:
```
DATABASE_URL=postgresql://postgres:<YOUR_PG_PASSWORD>@localhost:5432/restaurantDB
GROQ_API_KEY=<your_groq_api_key>
```

Replace `<YOUR_PG_PASSWORD>` with your PostgreSQL password.
Get a free GROQ API key from: https://console.groq.com

---

## 3. Database Setup (FIRST TIME ONLY)
Run this to create all tables and seed data:
```powershell
# Drop old DB if exists
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "DROP DATABASE IF EXISTS restaurantDB;"

# Create fresh DB
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "CREATE DATABASE restaurantDB;"

# Load schema + data (use db_updated.sql, NOT restaurantDB.sql)
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d restaurantDB -f "D:\FAST\FYP\Khadim\RAG + agents\Databse\db_updated.sql"
```

> ⚠️ Always use `db_updated.sql` — it has the correct schema with all columns.
> `restaurantDB.sql` is outdated (missing `image_url` columns).

---

## 4. Python Virtual Environment (FIRST TIME ONLY)
```powershell
cd "D:\FAST\FYP\Khadim\RAG + agents"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

> Also install ffmpeg separately (not pip):
> ```powershell
> winget install ffmpeg
> ```

---

## 5. Running the App (EVERY SESSION)

**Terminal 1 — FastAPI backend:**
```powershell
cd "D:\FAST\FYP\Khadim\RAG + agents"
venv\Scripts\activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Wait for: `Application startup complete`

**Terminal 2 — Flutter app:**
```powershell
cd "D:\FAST\FYP\Khadim\App"
flutter run
```

---

## 6. Voice Model (FIRST TIME ONLY)
The Whisper model (`voice/whisper_urdu_final/`) is NOT on git (model files are too large).
Get `model.safetensors` from the team (share via USB/Drive) and place it at:
```
D:\FAST\FYP\Khadim\voice\whisper_urdu_final\model.safetensors
```
All other files in that folder ARE on git.

---

## 7. Files That Are Safe to Ignore
These scripts in `voice/` have hardcoded paths for training — they are one-time training scripts, not needed to run the app:
- `voice/save_model.py`
- `voice/finetune_whisper.py`
- `voice/denoise.py`

---

## 8. Database usage

- Always make changes inside vs code and not in your pg admin 
- Then use this command (change name to your exact db name in pg admin) to make changes to your pg admin
- All te changes will sync and eveyone will have updated db at every push 

"C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d KhadimDB -f "D:\FAST\FYP\Khadim\database\db_new(USE THIS).sql"

