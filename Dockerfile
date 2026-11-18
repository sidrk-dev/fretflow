# Stage 1: Build React 19 + Vite Frontend
FROM node:22-slim AS frontend-builder
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
WORKDIR /app/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# Stage 2: Production Python 3.12 + FFmpeg + FastAPI + PyTorch CPU Runtime
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-cache

COPY backend/app ./app
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Pre-download BTC 170-chord neural checkpoint during image build and verify SHA-256
RUN mkdir -p /app/backend/models /app/backend/cache && \
    curl -fsSL "https://raw.githubusercontent.com/ptnghia-j/ChordMini/main/checkpoints/btc_model_best.pth" \
      -o /app/backend/models/btc_model_best.pth && \
    echo "e0a12ca6d881f81e01dfb459b4836ec7dac8d8f87b0170a412b5807256b3a1fc  /app/backend/models/btc_model_best.pth" | sha256sum -c - && \
    useradd --create-home --uid 10001 fretflow && \
    chown -R fretflow:fretflow /app

USER fretflow

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/api/health" || exit 1
CMD ["sh", "-c", "/app/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
