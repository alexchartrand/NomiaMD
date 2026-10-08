.PHONY: dev backend frontend fake-llm dev-fake worker redis bench

dev:
	@echo "Starting backend and frontend..."
	@trap 'kill 0' EXIT; \
	(cd backend && uv run uvicorn app.main:app --reload) & \
	(cd frontend && npm run dev) & \
	wait

# Background extraction needs a Redis (`make redis`, in its own terminal) and
# REDIS_URL=redis://localhost:6379/0 in the root .env, for both the API and `make worker`.
# Without a real REDIS_URL (comment it out), extraction runs inline and no worker is needed.
redis:
	docker run --rm --name nomiamd-dev-redis -p 6379:6379 redis:7-alpine

worker:
	cd backend && uv run arq app.worker.WorkerSettings

# Backend + frontend + the fake LLM dev server (scripts/fake_llm_server.py) instead of a
# real chat-model call (embeddings still hit the real Mistral API) — use this when you don't want to burn real API calls/credits.
dev-fake:
	@echo "Starting backend, frontend, and the fake LLM dev server..."
	@trap 'kill 0' EXIT; \
	(cd backend && uv run python scripts/fake_llm_server.py) & \
	(cd backend && LLM_PROVIDER=openai_compatible LLM_ENDPOINT=http://localhost:8080/v1 LLM_API_KEY=fake uv run uvicorn app.main:app --reload) & \
	(cd backend && if echo "$$REDIS_URL" | grep -q '^redis'; then LLM_PROVIDER=openai_compatible LLM_ENDPOINT=http://localhost:8080/v1 LLM_API_KEY=fake uv run arq app.worker.WorkerSettings; fi) & \
	(cd frontend && npm run dev) & \
	wait

backend:
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev -- --host 0.0.0.0 --port 5173

fake-llm:
	cd backend && uv run python scripts/fake_llm_server.py

# Benchmark the extraction pipeline stage by stage, e.g.
#   make bench ARGS="run --name mistral-base"
#   make bench ARGS="report mistral-base"
# See backend/scripts/benchmark.py.
bench:
	cd backend && uv run python scripts/benchmark.py $(ARGS)
