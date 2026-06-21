# syntax=docker/dockerfile:1
#
# Unified production image for SubTracker — works for BOTH:
#   • docker compose / plain docker  (uses SUBTRACKER_* env vars)
#   • a Home Assistant local add-on  (reads /data/options.json)
# The entrypoint auto-detects which one it's running under.
#
#   docker build -t subtracker .
#   docker run -p 5001:5001 -e SUBTRACKER_SECRET=$(openssl rand -hex 32) \
#              -v subtracker-data:/data subtracker
#
# BUILD_FROM lets the Home Assistant builder inject a per-arch base; it defaults
# to the upstream python image for a normal `docker build`.
ARG BUILD_FROM=python:3.13-slim
FROM ${BUILD_FROM}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local

# uv: copied from the official distroless image (no extra apt needed).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Install runtime deps first (cached unless the lockfile changes), no project, no dev group.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --no-dev

# App source + entrypoint.
COPY app/ ./app/
COPY main.py README.md ./
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Persistent SQLite lives on a mounted volume (/data is persistent for HA add-ons
# automatically; mount a volume there for compose). Never bake a DB into the image.
ENV SUBTRACKER_DB=/data/subscriptions.db \
    SUBTRACKER_PORT=5001
VOLUME ["/data"]
EXPOSE 5001

ENTRYPOINT ["docker-entrypoint.sh"]
