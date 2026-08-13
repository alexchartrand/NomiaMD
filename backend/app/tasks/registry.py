from app.ramq_codes import BillingCodesTask
from app.ramq_codes.retriever import get_ramq_retriever
from app.summary import ConsultationSummaryTask
from app.tasks.base import ExtractionTask

_TASKS: dict[str, ExtractionTask] = {
    task.name: task
    for task in [
        BillingCodesTask(get_ramq_retriever()),
        ConsultationSummaryTask(),
        # Future tasks (PrescriptionTask, ...) get added here — nothing else in the
        # pipeline needs to change.
    ]
}


def get_task(name: str) -> ExtractionTask:
    try:
        return _TASKS[name]
    except KeyError:
        available = ", ".join(sorted(_TASKS))
        raise ValueError(f"Unknown task '{name}'. Available tasks: {available}") from None


def available_tasks() -> list[str]:
    return sorted(_TASKS)
