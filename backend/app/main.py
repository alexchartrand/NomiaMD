from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Must run before app.db / app.extraction.engine are imported below — both read
# environment variables (DATABASE_URL, ANTHROPIC_API_KEY, NOMIAMD_MODEL) at import time.
load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402

from app.db import init_db, save_extraction  # noqa: E402
from app.extraction.engine import run_extraction  # noqa: E402
from app.models import (  # noqa: E402
    BillingCodesResult,
    ExtractionRequest,
    ExtractionResult,
    SamplePatientDetail,
    SamplePatientSummary,
)
from app.sample_patients import get_sample_patient, get_sample_patients  # noqa: E402
from app.tasks.registry import available_tasks, get_task  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="NomiaMD", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "tasks": available_tasks()}


@app.get("/patients", response_model=list[SamplePatientSummary])
def list_patients() -> list[SamplePatientSummary]:
    """Synthetic test patients from train.jsonl, for the frontend's patient picker."""
    return [
        SamplePatientSummary(id=p.id, label=p.label) for p in get_sample_patients()
    ]


@app.get("/patients/{patient_id}", response_model=SamplePatientDetail)
def get_patient(patient_id: str) -> SamplePatientDetail:
    patient = get_sample_patient(patient_id)
    if patient is None:
        raise HTTPException(
            status_code=404, detail=f"No sample patient with id '{patient_id}'"
        )
    return SamplePatientDetail(id=patient.id, label=patient.label, transcript=patient.transcript)


@app.post("/extract", response_model=ExtractionResult[BillingCodesResult])
def extract(request: ExtractionRequest) -> ExtractionResult[BillingCodesResult]:
    # NOTE: hardcoded to BillingCodesResult since it's the only registered task today.
    # Adding a second task type (prescriptions, consultation_notes) means this response_model
    # needs to become a Union of parameterized ExtractionResult types, or this endpoint needs
    # to split per task — either way, revisit this line then.
    try:
        task = get_task(request.task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = run_extraction(task, request.transcript)

    save_extraction(
        task=result.task,
        transcript=request.transcript,
        result=result.result.model_dump(),
        model=result.model,
        source_system=request.source.system if request.source else None,
    )

    return result
