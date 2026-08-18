from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.auth import auth_router, get_current_user
from app.config import settings
from app.extraction import extraction_router
from app.models import SamplePatientDetail, SamplePatientSummary
from app.postgresdb import init_db
from app.ramq_chatbot import ramq_chatbot_router
from app.rate_limit import limiter
from app.request_logging import RequestLoggingMiddleware
from app.sample_patients import get_sample_patient, get_sample_patients
from app.tasks.registry import available_tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="NomiaMD", lifespan=lifespan, debug=settings.debug)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(RequestLoggingMiddleware)
app.include_router(auth_router)
app.include_router(extraction_router)
app.include_router(ramq_chatbot_router)


@app.get("/health")
# Liveness/readiness check. Returns "ok" plus the list of registered task names.
def health() -> dict:
    return {"status": "ok", "tasks": available_tasks()}


@app.get("/patients", response_model=list[SamplePatientSummary], dependencies=[Depends(get_current_user)])
# Lists the synthetic demo patients from consultations/, for the frontend's patient picker.
def list_patients() -> list[SamplePatientSummary]:
    return [
        SamplePatientSummary(id=p.id, label=p.label) for p in get_sample_patients()
    ]


@app.get(
    "/patients/{patient_id}",
    response_model=SamplePatientDetail,
    dependencies=[Depends(get_current_user)],
)
# Fetches one demo patient's full transcript by id; 404 if the id doesn't match a file in consultations/.
def get_patient(patient_id: str) -> SamplePatientDetail:
    patient = get_sample_patient(patient_id)
    if patient is None:
        raise HTTPException(
            status_code=404, detail=f"No sample patient with id '{patient_id}'"
        )
    return SamplePatientDetail(id=patient.id, label=patient.label, transcript=patient.transcript)
