# One image, one port: the API also serves the built website.
# Works on Hugging Face Spaces (Docker SDK), Render, Railway, Fly.io or any Docker host.
# Build and run locally:
#   docker build -t docuforensic .
#   docker run -p 7860:7860 --env-file .env docuforensic
# then open http://localhost:7860

# ---- 1. Build the website ----
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. The app ----
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces runs the container as user 1000.
RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.lock

COPY config ./config
COPY models ./models
COPY pipeline ./pipeline
COPY backend ./backend
COPY llm ./llm
COPY audit ./audit
COPY scripts ./scripts
COPY data ./data
COPY --from=web /web/dist ./frontend/dist

RUN mkdir -p /app/var && chown -R app /app/var
USER app

# Keys are never baked in. Add them as secrets on the host (see docs/DEPLOY.md).
# Without any key the app still works: checks run locally and AI notes are replayed, labelled.
ENV HOME=/home/app \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/var \
    LLM_CHAIN=groq,gemini,openrouter \
    PORT=7860

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD curl -fsS "http://localhost:${PORT}/api/health" || exit 1
CMD ["sh", "-c", "exec python -m uvicorn backend.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
