# Team Setup Notes

This guide is for new team members to run:
- FastAPI backend
- Kitchen Dashboard (FastAPI web page)
- Admin Dashboard
- Restaurant-side Ordering App (Kiosk)
- Delivery-side App (Customer)

---

## 1. One-Time Setup

### 1.1 Backend environment
```powershell
cd "D:\FAST\FYP\Khadim\RAG + agents"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Install ffmpeg once (system-wide):
```powershell
winget install ffmpeg
```

### 1.2 Backend `.env` file
Create this file manually:

Path:
```text
RAG + agents/.env
```

Contents:
```env
DATABASE_URL=postgresql://postgres:<YOUR_PG_PASSWORD>@localhost:5432/KhadimDB
GROQ_API_KEY=<YOUR_GROQ_API_KEY>
```

### 1.3 Database import (first time or full reset)
Use the team SQL dump file:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d KhadimDB -f "D:\FAST\FYP\Khadim\Database\db_new(USE THIS).sql"
```

---

## 2. API URL Configuration (Flutter)

File:
```text
App/lib/services/api_config.dart
```

Current logic:
- Web uses `http://localhost:8000`
- Mobile uses `http://192.168.100.30:8000`

If backend host changes, update this file before running mobile builds.

---

## 3. Start Backend (Every Session)

Open a terminal:
```powershell
cd "D:\FAST\FYP\Khadim\RAG + agents"
venv\Scripts\activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Backend health check URL:
```text
http://127.0.0.1:8000/docs
```

---

## 4. Run Kitchen Dashboard (FastAPI)

Kitchen dashboard is served by FastAPI (no separate Streamlit process required).

After backend is running, open:
```text
http://127.0.0.1:8000/kitchen/dashboard
```

---

## 5. Run Delivery App (Customer)

### 5.1 Web
```powershell
cd "D:\FAST\FYP\Khadim\App"
flutter pub get
flutter run -d chrome --target lib/main.dart
```

### 5.2 Mobile (Android flavor: customer)
```powershell
cd "D:\FAST\FYP\Khadim\App"
flutter pub get
flutter run --flavor customer --target lib/main.dart
```

---

## 6. Run Restaurant App (Kiosk / Dine-In)

### 6.1 Web
```powershell
cd "D:\FAST\FYP\Khadim\App"
flutter pub get
flutter run -d chrome --target lib/main_kiosk.dart
```

### 6.2 Mobile (Android flavor: kiosk)
```powershell
cd "D:\FAST\FYP\Khadim\App"
flutter pub get
flutter run --flavor kiosk --target lib/main_kiosk.dart
```

---

## 7. Run Admin Dashboard

Admin dashboard is inside the customer app routes.

### 7.1 Web (direct route)
```powershell
cd "D:\FAST\FYP\Khadim\App"
flutter run -d chrome --target lib/main.dart --route /admin
```

### 7.2 Mobile (direct route)
```powershell
cd "D:\FAST\FYP\Khadim\App"
flutter run --flavor customer --target lib/main.dart --route /admin
```

Alternative: run the customer app normally and navigate to Admin from inside the app.
admin credentials are: 
username = admin@gmail.com
password = 123456

---

## 8. Recommended Daily Run Order

1. Start FastAPI backend first.
2. Open Kitchen Dashboard URL in browser.
3. Start the app you need:
	- Delivery (customer)
	- Restaurant (kiosk)
	- Admin

---

## 9. Voice Model Note

Large Whisper model files are not fully tracked in git. Ensure this file exists:
```text
D:\FAST\FYP\Khadim\voice\whisper_urdu_final\model.safetensors
```

One-time training scripts in `voice/` are not required for normal app runtime.

