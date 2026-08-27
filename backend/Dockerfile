# --- builder ---
FROM python:3.11-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.6 /uv /uvx /bin/
WORKDIR /build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
# Deps first (--no-install-project), then the local package, so the deps layer stays cached
# across app/ changes. --frozen refuses to touch uv.lock, for a reproducible build
# regardless of what's newly released upstream (lancedb/llama-index-* move fast).
RUN uv sync --frozen --no-install-project --no-dev
COPY app ./app
RUN uv sync --frozen --no-dev

# --- runtime ---
FROM python:3.11-slim AS runtime
RUN useradd --create-home --uid 10001 appuser
COPY --from=builder /build/.venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY app ./app
COPY scripts ./scripts
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# One worker per container — let the orchestrator scale via replicas instead of
# multiplexing inside one container. --proxy-headers trusts X-Forwarded-For, but only from
# nginx's static compose IP (172.28.0.10, see docker-compose.yml's `frontend` service) —
# not from any peer that can reach this container — so rate limiting sees real client IPs
# and can't be reset by a forged header from elsewhere on the Docker network. Keep this in
# sync with docker-compose.yml's `internal` network / `frontend`'s ipv4_address.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=172.28.0.10"]
