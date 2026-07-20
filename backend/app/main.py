from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Must run before app.db / app.extraction.engine are imported below — both read
# environment variables (DATABASE_URL, NOMIAMD_BASE_URL, NOMIAMD_API_KEY, NOMIAMD_MODEL,
# NOMIAMD_STRUCTURED_OUTPUT) at import time. Loaded from an explicit path (not a bare
# load_dotenv()) because
# python-dotenv falls back to os.getcwd() instead of walking up from this file whenever
# a debugger is attached (sys.gettrace() set) — which silently no-ops if the debugger's
# working directory isn't backend/.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, HTTPException  # noqa: E402

from app.db import init_db, save_extraction  # noqa: E402
from app.extraction.engine import run_extraction  # noqa: E402
from app.extraction.pipeline import run_billing_codes_pipeline  # noqa: E402
from app.models import (  # noqa: E402
    BillingCodesResult,
    ConsultationSummaryResult,
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
    """Synthetic test patients from notes_consultation_simulees.md, for the frontend's patient picker."""
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


@app.post("/extract", response_model=None)
def extract(
    request: ExtractionRequest,
) -> ExtractionResult[BillingCodesResult] | ExtractionResult[ConsultationSummaryResult]:
    # response_model=None (bypassing FastAPI's automatic use of the return-type annotation
    # above for response validation/filtering) because Pydantic's Union matching for two
    # *parameterized-generic* ExtractionResult types picks the wrong member here: neither
    # BillingCodesResult nor ConsultationSummaryResult has every field required, so
    # revalidating an already-correct instance against the *other* union member silently
    # "succeeds" by falling back to that member's defaults for whatever fields don't exist
    # on the real object, instead of keeping the real one. The return type above is still
    # accurate documentation of what this actually returns — result is already a properly
    # typed, task-specific pydantic model by the time it gets here (see run_extraction),
    # so there's nothing left to validate; only accurate per-task OpenAPI schema docs are
    # lost, which matters once there's a second consumer of this API beyond the frontend.
    try:
        task = get_task(request.task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    source_system = request.source.system if request.source else None

    if task.name == "billing_codes":
        # billing_codes no longer runs off the raw transcript directly — it's a two-stage
        # pipeline (transcript -> consultation_summary -> billing_codes), see
        # app/extraction/pipeline.py. Store the intermediate summary too, since it's the
        # actual input the billing model reasoned over and a physician reviewing a
        # surprising code needs to see it, not just the raw transcript.
        summary_result, result = run_billing_codes_pipeline(request.transcript)
        save_extraction(
            task=summary_result.task,
            transcript=request.transcript,
            result=summary_result.result.model_dump(),
            model=summary_result.model,
            source_system=source_system,
        )
    else:
        result = run_extraction(task, request.transcript)

    save_extraction(
        task=result.task,
        transcript=request.transcript,
        result=result.result.model_dump(),
        model=result.model,
        source_system=source_system,
    )

    return result
