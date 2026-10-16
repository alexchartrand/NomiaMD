"""The consultation_summary step: transcript -> structured French clinical facts, no codes."""

from dataclasses import dataclass

from app.llm import StructuredChat, resolve_model
from app.summary.models import ConsultationSummaryResult
from app.summary.prompt import SYSTEM_PROMPT


@dataclass(frozen=True)
class Summarized:
    summary: ConsultationSummaryResult
    # The model id the provider reported for this call.
    model: str


class ConsultationSummarizer:
    # The stored stage name, the call's metered purpose and its LLM_MODEL_<NAME> override.
    NAME = "consultation_summary"
    DEFAULT_MODEL = "mistral-small-latest"

    def __init__(self, chat: StructuredChat | None = None, model: str | None = None):
        """`model`: None = LLM_MODEL_CONSULTATION_SUMMARY, else DEFAULT_MODEL, read per call."""
        self._chat = chat or StructuredChat()
        self._model = model

    def resolved_model(self) -> str:
        return resolve_model(self.NAME, self.DEFAULT_MODEL, self._model)

    async def summarize(self, transcript: str) -> Summarized:
        reply = await self._chat.complete(
            name=self.NAME,
            model=self.resolved_model(),
            system=SYSTEM_PROMPT,
            user=f"Transcript:\n{transcript}\n\nExtract the structured facts per your instructions.",
            output=ConsultationSummaryResult,
        )
        return Summarized(summary=reply.parse_with(ConsultationSummaryResult.model_validate), model=reply.model)
