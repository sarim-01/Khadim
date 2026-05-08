# Backend API (FastAPI). First build can take several minutes (ML stack).
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Production: no --reload. Override workers via command if needed.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
