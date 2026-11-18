# Stage 1: Build React 19 + Vite Frontend
FROM node:22-slim AS frontend-builder
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
RUN uv sync --frozen --no-dev

COPY backend/app ./app
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Pre-download BTC 170-chord neural checkpoint during image build for instant cold starts
RUN mkdir -p /app/backend/models && \
    curl -sSL "https://raw.githubusercontent.com/ptnghia-j/ChordMini/main/checkpoints/btc_model_best.pth" \
      -o /app/backend/models/btc_model_best.pth

EXPOSE 8000
CMD ["sh", "-c", "/app/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
