from app.lancedb import LanceDB
from app.ramq_codes import BillingCodesTask, build_codes_data, build_ramq_retriever
from app.summary import ConsultationSummaryTask
from app.tasks.base import ExtractionTask

_TASKS: dict[str, ExtractionTask] = {}


def register_tasks(tasks: list[ExtractionTask]) -> None:
    """Replaces the registry's contents with exactly these tasks. The low-level entry point
    both init_tasks (real collaborators, wired from an open LanceDB) and tests'
    small_reference_table fixture (stubbed collaborators) call."""
    _TASKS.clear()
    _TASKS.update({task.name: task for task in tasks})


def init_tasks(db: LanceDB) -> None:
    """Builds and registers every extraction task. Called once by the app lifespan
    (app/bootstrap.py's application_services()) — not at import time, since
    BillingCodesTask's retriever needs an already-open LanceDB connection (and building it
    scans the whole `code-embeddings` table)."""
    register_tasks([
        BillingCodesTask(build_ramq_retriever(db.vector_store), build_codes_data(db.codes)),
        ConsultationSummaryTask(),
        # Future tasks (PrescriptionTask, ...) get added here — nothing else in the
        # pipeline needs to change.
    ])


def get_task(name: str) -> ExtractionTask:
    if not _TASKS:
        raise RuntimeError(
            "Task registry not initialized — app/bootstrap.py's application_services() "
            "must run first"
        )
    try:
        return _TASKS[name]
    except KeyError:
        available = ", ".join(sorted(_TASKS))
        raise ValueError(f"Unknown task '{name}'. Available tasks: {available}") from None


def available_tasks() -> list[str]:
    return sorted(_TASKS)
