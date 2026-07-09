from app.tasks.base import ExtractionTask
from app.tasks.billing_codes import BillingCodesTask

_TASKS: dict[str, ExtractionTask] = {
    task.name: task
    for task in [
        BillingCodesTask(),
        # Future tasks (PrescriptionTask, ConsultationNoteTask, ...) get added here —
        # nothing else in the pipeline needs to change.
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
