from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Must run before app.db / app.extraction.engine are imported below — app.db reads
# DATABASE_URL at import time, and app.extraction.engine.get_client() reads
# MISTRAL_API_KEY. Loaded from an explicit path (not a bare load_dotenv()) because
# python-dotenv falls back to os.getcwd() instead of walking up from this file whenever
# a debugger is attached (sys.gettrace() set) — which silently no-ops if the debugger's
# working directory isn't backend/.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

from app.db import init_db, save_extraction  # noqa: E402
from app.extraction.engine import run_extraction  # noqa: E402
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
from app.summary import ConsultationSummaryResult  # noqa: E402
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
def health() -> dict:
    return {"status": "ok", "tasks": available_tasks()}


@app.get("/patients", response_model=list[SamplePatientSummary])
def list_patients() -> list[SamplePatientSummary]:
    """Synthetic test patients from consultations/, for the frontend's patient picker."""
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
@limiter.limit("10/minute")
async def extract(
    request: Request,
    body: ExtractionRequest,
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
    # `request: Request` (unused beyond slowapi's @limiter.limit, which requires a
    # literally-named `request` param to find it) sits alongside the Pydantic body,
    # renamed to `body` to avoid the name collision.
    try:
        task = get_task(body.task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    source_system = body.source.system if body.source else None

    if task.name == "billing_codes":
        # billing_codes no longer runs off the raw transcript directly — it's a two-stage
        # pipeline (transcript -> consultation_summary -> billing_codes), see
        # app/extraction/pipeline.py. Store the intermediate summary too, since it's the
        # actual input the billing model reasoned over and a physician reviewing a
        # surprising code needs to see it, not just the raw transcript.
        summary_result, result = run_billing_codes_pipeline(body.transcript)
        await save_extraction(
            task=summary_result.task,
            transcript=body.transcript,
            result=summary_result.result.model_dump(),
            model=summary_result.model,
            source_system=source_system,
        )
    else:
        result = run_extraction(task, body.transcript)

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
