.PHONY: dev backend frontend

dev:
	@echo "Starting backend and frontend..."
	@trap 'kill 0' EXIT; \
	(cd backend && . .venv/bin/activate && uvicorn app.main:app --reload) & \
	(cd frontend && npm run dev) & \
	wait

backend:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev -- --host 0.0.0.0 --port 5173
