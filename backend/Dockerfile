# CloudOps Sentinel backend: FastAPI + Uvicorn, locked dependencies, non-root user.
# Built by compose.yaml (context: backend/). Local data never enters the image
# (.dockerignore excludes data/, *.db and .env).

# uv, pinned to the version used to write uv.lock.
FROM ghcr.io/astral-sh/uv:0.12.10 AS uv

# --- build: install the locked production dependencies into /app/.venv ----------------
FROM python:3.12-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
# --locked: fail if uv.lock does not match pyproject.toml. --no-dev: no pytest or ruff.
# --no-install-project: the app runs from its source tree (below), because config.py finds
# scenarios/ relative to the sentinel package.
RUN uv sync --locked --no-dev --no-install-project

# --- runtime ---------------------------------------------------------------------------
FROM python:3.12-slim
RUN groupadd --system --gid 10001 sentinel \
    && useradd --system --uid 10001 --gid sentinel --home-dir /app --no-create-home sentinel \
    && mkdir /data \
    && chown sentinel:sentinel /data
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY sentinel ./sentinel
COPY scenarios ./scenarios
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SENTINEL_DB_PATH=/data/sentinel-local.db
USER sentinel
EXPOSE 8000
# 0.0.0.0 inside the container only: compose does not publish this port; the host reaches
# the API through the frontend's Nginx proxy on 127.0.0.1:8080.
CMD ["uvicorn", "sentinel.main:app", "--host", "0.0.0.0", "--port", "8000"]
