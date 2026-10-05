from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.auth import auth_router
from app.bills import bills_router
from app.bootstrap import application_services
from app.claims import claims_router
from app.contact import contact_router
from app.config import settings
from app.encounters import encounters_router
from app.extraction import extraction_router
from app.extraction.background import extraction_queue
from app.intake import IntakeService, epic_sandbox_router, intake_router
from app.logging_config import configure_logging
from app.patients import patients_router
from app.ramq_chatbot import ramq_chatbot_router
from app.rate_limit import limiter
from app.request_logging import RequestLoggingMiddleware
from app.sample_patients import sample_patients_router
from app.tasks.registry import available_tasks

configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with application_services() as db, extraction_queue() as queue:
        app.state.lancedb = db
        app.state.extraction_queue = queue
        app.state.intake_service = IntakeService(queue)
        yield


app = FastAPI(title="NomiaMD", lifespan=lifespan, debug=settings.debug)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(RequestLoggingMiddleware)
app.include_router(auth_router)
app.include_router(bills_router)
app.include_router(claims_router)
app.include_router(contact_router)
app.include_router(encounters_router)
app.include_router(extraction_router)
app.include_router(intake_router)
app.include_router(epic_sandbox_router)
app.include_router(patients_router)
app.include_router(ramq_chatbot_router)
app.include_router(sample_patients_router)


@app.get("/health")
# Liveness/readiness check. Returns "ok" plus the list of registered task names.
def health() -> dict:
    return {"status": "ok", "tasks": available_tasks()}
