from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

from app.db import init_db, save_extraction  # noqa: E402
from app.extraction.pipeline import run_billing_codes_pipeline  # noqa: E402
from app.models import (  # noqa: E402
    ExtractionRequest,
    ExtractionResult,
    SamplePatientDetail,
    SamplePatientSummary,
)
from app.ramq_codes import BillingCodesResult  # noqa: E402
from app.ramq_chatbot import RAMQQueryRequest, RAMQQueryResult, get_ramq_query_engine  # noqa: E402
from app.rate_limit import limiter  # noqa: E402
from app.request_logging import RequestLoggingMiddleware  # noqa: E402
from app.sample_patients import get_sample_patient, get_sample_patients  # noqa: E402
from app.tasks.registry import available_tasks, get_task  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="NomiaMD", lifespan=lifespan, debug=False)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(RequestLoggingMiddleware)


@app.get("/health")
# Liveness/readiness check. Returns "ok" plus the list of registered task names.
def health() -> dict:
    return {"status": "ok", "tasks": available_tasks()}


@app.get("/patients", response_model=list[SamplePatientSummary])
# Lists the synthetic demo patients from consultations/, for the frontend's patient picker.
def list_patients() -> list[SamplePatientSummary]:
    return [
        SamplePatientSummary(id=p.id, label=p.label) for p in get_sample_patients()
    ]


@app.get("/patients/{patient_id}", response_model=SamplePatientDetail)
# Fetches one demo patient's full transcript by id; 404 if the id doesn't match a file in consultations/.
def get_patient(patient_id: str) -> SamplePatientDetail:
    patient = get_sample_patient(patient_id)
    if patient is None:
        raise HTTPException(
            status_code=404, detail=f"No sample patient with id '{patient_id}'"
        )
    return SamplePatientDetail(id=patient.id, label=patient.label, transcript=patient.transcript)


@app.post("/extract", response_model=ExtractionResult[BillingCodesResult])
@limiter.limit("10/minute")
async def extract(
    request: Request,
    body: ExtractionRequest,
) -> ExtractionResult[BillingCodesResult]:
    # `request: Request` (unused beyond slowapi's @limiter.limit, which requires a
    # literally-named `request` param to find it) sits alongside the Pydantic body,
    # renamed to `body` to avoid the name collision.
    try:
        task = get_task(body.task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # billing_codes is the only task wired to /extract — consultation_summary exists only
    # as billing_codes' internal first stage (see run_billing_codes_pipeline below), not as
    # something a client can invoke directly here.
    if task.name != "billing_codes":
        raise HTTPException(
            status_code=400,
            detail="Only 'billing_codes' is available via /extract",
        )

    source_system = body.source.system if body.source else None

    # billing_codes runs off a two-stage pipeline (transcript -> consultation_summary ->
    # billing_codes), see app/extraction/pipeline.py. Store the intermediate summary too,
    # since it's the actual input the billing model reasoned over and a physician
    # reviewing a surprising code needs to see it, not just the raw transcript.
    summary_result, result = run_billing_codes_pipeline(body.transcript)
    await save_extraction(
        task=summary_result.task,
        transcript=body.transcript,
        result=summary_result.result.model_dump(),
        model=summary_result.model,
        source_system=source_system,
    )

    await save_extraction(
        task=result.task,
        transcript=body.transcript,
        result=result.result.model_dump(),
        model=result.model,
        source_system=source_system,
    )

    return result


@app.post("/query", response_model=RAMQQueryResult)
@limiter.limit("20/minute")
def query_ramq_manual(request: Request, body: RAMQQueryRequest) -> RAMQQueryResult:
    """Free-form, multi-turn billing question answered from the RAMQ omnipraticien manual —
    not tied to any specific encounter/transcript, unlike /extract. History is stateless:
    the client resends prior turns each request, nothing is persisted server-side."""
    engine = get_ramq_query_engine()
    answer = engine.custom_query(body.query, chat_history=body.history)
    return RAMQQueryResult(answer=answer)
