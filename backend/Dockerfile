# --- builder ---
FROM python:3.11-slim AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml requirements.lock.txt ./
COPY app ./app
# Pinned transitive versions from requirements.lock.txt first, for a reproducible build
# regardless of what's newly released upstream (lancedb/llama-index-* move fast) — then the
# local package itself with --no-deps since its deps are already satisfied by the lockfile.
RUN pip install --no-cache-dir -r requirements.lock.txt && \
    pip install --no-cache-dir --no-deps .

# --- runtime ---
FROM python:3.11-slim AS runtime
RUN useradd --create-home --uid 10001 appuser
COPY --from=builder /opt/venv /opt/venv
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
