"""Fans a consultation summary out into several retrieval queries instead of one blended
query for the whole encounter. A structural planner over ConsultationSummaryResult's own
fields, not an LLM one: the summary is already structured — a visit, and separately zero or
more procedures and possible add-ons — so building one query per concept is deterministic,
adds no LLM latency or cost, and is strictly better than asking a model to paraphrase data
that's already explicit. (ramq_chatbot's retriever handled its own, free-form-question fan-
out with an LLM paraphraser, app/ramq_chatbot/query_generator.py's LLMQueryGenerator — since
removed; that retriever now runs a single query.)

Without this, a note describing both a routine visit and a minor procedure gets one blended
embedding query that retrieves neither the visit family nor the procedure family well —
retrieval dilution the two-part summary structure already tells us how to avoid."""

from dataclasses import dataclass
from typing import Literal

from app.patients import nam
from app.summary.models import ConsultationSummaryResult
from app.summary.task import render_for_billing_codes

QuerySource = Literal["visit", "procedure", "add_on", "transcript"]


@dataclass(frozen=True)
class PlannedQuery:
    text: str
    # Which part of the input the query came from — lets a retrieval trace say which query
    # surfaced a code.
    source: QuerySource


class SummaryQueryPlanner:
    def plan_labeled(self, summary: ConsultationSummaryResult) -> list[PlannedQuery]:
        """The first query is always the full rendered summary (today's single-query
        behavior, preserved as the baseline) — everything after it narrows in on one
        specific concept the summary called out separately. Order matters for RRF only in
        that it doesn't: fusion is rank-based per query list, not query-list order, so this
        list can grow without needing to stay in any particular sequence."""
        queries = [PlannedQuery(render_for_billing_codes(summary), "visit")]

        for procedure in summary.procedures_performed:
            queries.append(PlannedQuery(procedure.procedure_description, "procedure"))

        queries.extend(PlannedQuery(add_on, "add_on") for add_on in summary.possible_billable_add_ons)

        return queries

    def plan(self, summary: ConsultationSummaryResult) -> list[str]:
        return [query.text for query in self.plan_labeled(summary)]


class TranscriptQueryPlanner:
    """One query over the whole note, NAM redacted (as BillingCodesTask sends it). Not used
    by the pipeline: it's the benchmark's control for what the structured summary adds to
    retrieval, and a candidate to fuse with SummaryQueryPlanner's queries if it helps."""

    def plan(self, transcript: str) -> list[PlannedQuery]:
        return [PlannedQuery(nam.redact(transcript), "transcript")]
