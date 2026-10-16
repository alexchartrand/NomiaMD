"""The billing_codes step: the model picks codes from an already-retrieved candidate set."""

from dataclasses import dataclass

from app.llm import StructuredChat, resolve_model
from app.ramq_codes.context import BillingContext
from app.ramq_codes.eligibility import CandidateSet
from app.ramq_codes.models import BillingCodesOutput, BillingCodesResult
from app.ramq_codes.prompt import BillingPromptBuilder
from app.ramq_codes.selection_parser import SelectionDrops, SelectionParser
from app.summary import ConsultationSummaryResult


@dataclass(frozen=True)
class CodeSelection:
    result: BillingCodesResult
    # The model id the provider reported for this call.
    model: str
    drops: SelectionDrops


class CodeSelector:
    # The stored stage name, the call's metered purpose and its LLM_MODEL_<NAME> override.
    NAME = "billing_codes"
    # Selecting among near-identical French tariff variants (differing on axes buried in
    # prose) is harder than the structural extraction consultation_summary does, so this
    # step gets the stronger model.
    DEFAULT_MODEL = "mistral-medium-latest"

    def __init__(
        self,
        chat: StructuredChat | None = None,
        model: str | None = None,
        prompt_builder: BillingPromptBuilder | None = None,
        parser: SelectionParser | None = None,
    ):
        """`model`: None = LLM_MODEL_BILLING_CODES, else DEFAULT_MODEL, read per call."""
        self._chat = chat or StructuredChat()
        self._model = model
        self._prompt_builder = prompt_builder or BillingPromptBuilder()
        self._parser = parser or SelectionParser()

    def resolved_model(self) -> str:
        return resolve_model(self.NAME, self.DEFAULT_MODEL, self._model)

    async def select(
        self,
        candidates: CandidateSet,
        summary: ConsultationSummaryResult,
        transcript: str,
        context: BillingContext,
    ) -> CodeSelection:
        prompt = self._prompt_builder.build(candidates, summary, transcript, context)
        reply = await self._chat.complete(
            name=self.NAME,
            model=self.resolved_model(),
            system=prompt.system,
            user=prompt.user,
            output=BillingCodesOutput,
        )
        offered = frozenset(c.number for c in candidates.candidates)
        parsed = reply.parse_with(lambda raw: self._parser.parse(raw, offered))
        return CodeSelection(result=parsed.result, model=reply.model, drops=parsed.drops)
