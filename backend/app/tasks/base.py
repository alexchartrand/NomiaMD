"""The pluggable extraction-task interface.

Every output type this system produces (billing codes, consultation summaries; more later)
implements this interface. The transcript ingestion and Mistral API plumbing
(app/extraction/engine.py) is shared and never needs to change when a new task is added —
only a new class implementing ExtractionTask.

Generic on TInput because tasks don't all take the same kind of input: ConsultationSummaryTask
takes a bare transcript string, while BillingCodesTask takes a small bundle (summary text,
raw transcript, resolved billing context — see app/ramq_codes/task.py's BillingCodesInput).
Bolting optional parameters onto a single build_prompt(str) signature would let every task
see every other task's inputs; parameterizing on TInput keeps each task's input shape its
own business.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

TInput = TypeVar("TInput")


@dataclass(frozen=True)
class PreparedPrompt:
    """What build_prompt hands back to run_extraction (app/extraction/engine.py) and, in
    turn, to parse() — bundling the two prompt strings with whatever closed candidate set
    (if any) the model's output must be validated against.

    candidate_numbers is None for a task with no closed set to check against
    (ConsultationSummaryTask extracts free-form facts, not a pick-from-a-list); it is a
    (possibly empty) frozenset for a task like BillingCodesTask, where "the model invented a
    code that was never offered" is a real failure mode parse() must catch — see
    app/ramq_codes/task.py's BACKLOG item this closes."""

    system_prompt: str
    user_message: str
    candidate_numbers: frozenset[str] | None = None


class ExtractionTask(ABC, Generic[TInput]):
    name: str
    # Per-task model override (app/extraction/engine.py's get_client(model) is keyed on
    # this) — a task whose selection step is harder than plain structural extraction can ask
    # for a stronger model without every other task paying for it. See
    # app/ramq_codes/task.py's BillingCodesTask for the one task that overrides this today.
    model: str = "mistral-small-latest"

    @abstractmethod
    async def build_prompt(self, task_input: TInput) -> PreparedPrompt:
        """Returns the system/user prompt (and candidate set, if any) for this task's input.

        For most tasks task_input is the raw transcript. billing_codes is the exception: see
        BillingCodesInput in app/ramq_codes/task.py.
        """

    @abstractmethod
    def json_schema(self) -> dict[str, Any]:
        """JSON schema passed to output_config.format for structured extraction."""

    @abstractmethod
    def parse(self, raw: dict[str, Any], prepared: PreparedPrompt) -> BaseModel:
        """Validate/parse the model's raw JSON output into a typed result. `prepared` is the
        same PreparedPrompt build_prompt returned for this call — tasks with no closed
        candidate set (prepared.candidate_numbers is None) can ignore it."""
