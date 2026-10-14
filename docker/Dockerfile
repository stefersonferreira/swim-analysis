# syntax=docker/dockerfile:1.7
#
# Alvos:
#   web         API + site (porta 8080)
#   worker      pipeline em CPU (padrão, roda em qualquer máquina)
#   worker-gpu  pipeline com CUDA (placa NVIDIA)
#
# Versões travadas: imagens base por tag exata (o CI pode fixar por digest), Python pelo
# uv.lock, Node pelo package-lock.json. Nada é baixado na primeira execução.

ARG PYTHON_IMAGE=python:3.12.7-slim-bookworm
ARG NODE_IMAGE=node:22.11.0-bookworm-slim
ARG CUDA_IMAGE=nvidia/cuda:12.4.1-runtime-ubuntu22.04
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.32

FROM ${UV_IMAGE} AS uv

# ---- Front-end -------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Base Python (CPU) -------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    SWIM_DATA_DIR=/data
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg curl \
 && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY pipeline ./pipeline
COPY brand ./brand
COPY backend ./backend
RUN uv sync --frozen --no-dev

# ---- API + site ------------------------------------------------------------------------
FROM base AS web
COPY --from=frontend /src/frontend/dist /app/static
COPY docker/web-entrypoint.sh /usr/local/bin/web-entrypoint.sh
RUN chmod +x /usr/local/bin/web-entrypoint.sh
ENV SWIM_STATIC_DIR=/app/static
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=6 \
  CMD curl -fsS http://localhost:8080/api/health || exit 1
CMD ["web-entrypoint.sh"]

# ---- Worker CPU ------------------------------------------------------------------------
FROM base AS worker
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD celery -A app.worker.celery_app inspect ping -d celery@$HOSTNAME --timeout 8 || exit 1
CMD ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=INFO", "--concurrency=1"]

# ---- Worker GPU ------------------------------------------------------------------------
# Base CUDA (Ubuntu 22.04). O driver fica no Windows/Linux hospedeiro; dentro do contêiner
# só vão as bibliotecas de runtime. Python 3.12 instalado pelo uv (sem depender do sistema).
FROM ${CUDA_IMAGE} AS worker-gpu
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    SWIM_DATA_DIR=/data
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md .python-version ./
RUN uv python install \
 && uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY pipeline ./pipeline
COPY brand ./brand
COPY backend ./backend
RUN uv sync --frozen --no-dev
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD celery -A app.worker.celery_app inspect ping -d celery@$HOSTNAME --timeout 8 || exit 1
CMD ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=INFO", "--concurrency=1"]
