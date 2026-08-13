.PHONY: dev backend frontend fake-llm dev-fake

dev:
	@echo "Starting backend and frontend..."
	@trap 'kill 0' EXIT; \
	(cd backend && . .venv/bin/activate && uvicorn app.main:app --reload) & \
	(cd frontend && npm run dev) & \
	wait

# Backend + frontend + the fake LLM dev server (scripts/fake_llm_server.py) instead of a
# real Mistral API call — use this when you don't want to burn real API calls/credits.
dev-fake:
	@echo "Starting backend, frontend, and the fake LLM dev server..."
	@trap 'kill 0' EXIT; \
	(cd backend && . .venv/bin/activate && python scripts/fake_llm_server.py) & \
	(cd backend && . .venv/bin/activate && MISTRAL_ENDPOINT=http://localhost:8080 uvicorn app.main:app --reload) & \
	(cd frontend && npm run dev) & \
	wait

backend:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev -- --host 0.0.0.0 --port 5173

fake-llm:
	cd backend && . .venv/bin/activate && python scripts/fake_llm_server.py
