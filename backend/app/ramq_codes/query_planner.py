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
retrieval dilution the two-part summary structure already tells us how to avoid.

The visit query is the encounter's form only, scoped to the manual's visit section (see
visit_query.py) — and run a second time within the care setting's own subsection when the
encounter's setting has one; the whole rendered summary still runs as the `overview` query,
so a code only the full clinical picture surfaces isn't lost."""

from dataclasses import dataclass
from typing import Literal

from app.care_setting import CareSetting
from app.patients import nam
from app.ramq_codes.visit_query import CARE_SETTING_VISIT_SECTIONS, VISIT_SECTION_PREFIX, VisitQueryRenderer
from app.summary.models import ConsultationSummaryResult, ProcedurePerformed
from app.summary.task import render_for_billing_codes

QuerySource = Literal["visit", "care_setting_visit", "overview", "procedure", "procedure_detail", "add_on", "transcript"]


@dataclass(frozen=True)
class PlannedQuery:
    text: str
    # Which part of the input the query came from — lets a retrieval trace say which query
    # surfaced a code.
    source: QuerySource
    # `header_path` prefixes the search is limited to (any of them); None = the whole table.
    section_prefixes: tuple[str, ...] | None = None


class SummaryQueryPlanner:
    def __init__(self, visit_renderer: VisitQueryRenderer | None = None):
        self._visit_renderer = visit_renderer or VisitQueryRenderer()

    def plan_labeled(
        self, summary: ConsultationSummaryResult, care_setting: CareSetting | None = None
    ) -> list[PlannedQuery]:
        """The visit query (section B only) — plus the same query within `care_setting`'s
        own subsection, if it has one — then the full rendered summary (`overview`, the
        whole table), then each procedure's queries and one query per add-on. Order doesn't
        matter to RRF: fusion is rank-based per query list, so this list can grow without
        needing to stay in any particular sequence.

        The subsection query is labeled `care_setting_visit`, whose hits CandidateFuser
        pins first. The section-B-wide visit query stays alongside it, so a wrong care
        setting only adds candidates, never removes the right one."""
        visit = self._visit_renderer.render(summary)
        queries = [PlannedQuery(visit, "visit", section_prefixes=(VISIT_SECTION_PREFIX,))]
        setting_section = CARE_SETTING_VISIT_SECTIONS.get(care_setting) if care_setting else None
        if setting_section:
            queries.append(PlannedQuery(visit, "care_setting_visit", section_prefixes=(setting_section,)))
        queries.append(PlannedQuery(render_for_billing_codes(summary), "overview"))

        for procedure in summary.procedures_performed:
            queries.extend(self._procedure_queries(procedure))

        queries.extend(PlannedQuery(add_on, "add_on") for add_on in summary.possible_billable_add_ons)

        return queries

    def plan(self, summary: ConsultationSummaryResult, care_setting: CareSetting | None = None) -> list[str]:
        return [query.text for query in self.plan_labeled(summary, care_setting)]

    @staticmethod
    def _procedure_queries(procedure: ProcedurePerformed) -> list[PlannedQuery]:
        """The act named generically, in the fee schedule's own terms, is what matches its
        code; the note's detailed wording (side, size, site) mostly matches unrelated
        surgery on the same body part, so it runs as a query of its own (`procedure_detail`)
        rather than diluting the generic one. A summary without a generic name (recorded
        before the field existed) searches with the detailed wording alone."""
        if not procedure.generic_act:
            return [PlannedQuery(procedure.procedure_description, "procedure")]
        return [
            PlannedQuery(procedure.generic_act, "procedure"),
            PlannedQuery(procedure.procedure_description, "procedure_detail"),
        ]


class TranscriptQueryPlanner:
    """One query over the whole note, NAM redacted (as BillingCodesTask sends it). Not used
    by the pipeline: it's the benchmark's control for what the structured summary adds to
    retrieval, and a candidate to fuse with SummaryQueryPlanner's queries if it helps."""

    def plan(self, transcript: str) -> list[PlannedQuery]:
        return [PlannedQuery(nam.redact(transcript), "transcript")]
