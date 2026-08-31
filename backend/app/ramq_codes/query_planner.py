"""Fans a consultation summary out into several retrieval queries instead of one blended
query for the whole encounter. A structural planner over ConsultationSummaryResult's own
fields, not an LLM one: unlike app/ramq_chatbot/query_generator.py's LLMQueryGenerator
(which paraphrases a free-form user question because there's no structure to read), the
summary is already structured — a visit, and separately zero or more procedures and
possible add-ons — so building one query per concept is deterministic, adds no LLM latency
or cost, and is strictly better than asking a model to paraphrase data that's already
explicit.

Without this, a note describing both a routine visit and a minor procedure gets one blended
embedding query that retrieves neither the visit family nor the procedure family well —
retrieval dilution the two-part summary structure already tells us how to avoid."""

from app.summary.models import ConsultationSummaryResult
from app.summary.task import render_for_billing_codes


class SummaryQueryPlanner:
    def plan(self, summary: ConsultationSummaryResult) -> list[str]:
        """The first query is always the full rendered summary (today's single-query
        behavior, preserved as the baseline) — everything after it narrows in on one
        specific concept the summary called out separately. Order matters for RRF only in
        that it doesn't: fusion is rank-based per query list, not query-list order, so this
        list can grow without needing to stay in any particular sequence."""
        queries = [render_for_billing_codes(summary)]

        for procedure in summary.procedures_performed:
            queries.append(procedure.procedure_description)

        queries.extend(summary.possible_billable_add_ons)

        return queries
