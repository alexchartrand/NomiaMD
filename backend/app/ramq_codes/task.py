import math
from dataclasses import dataclass
from typing import Any

from app.lancedb.repository import ICodeRepository
from app.patients import nam
from app.ramq_codes.context import AXIS_LABELS_FR, BillingContext
from app.ramq_codes.models import BillingCodesOutput, BillingCodesResult, Code, CodeFeeOut
from app.ramq_codes.retriever import ICodesRetriever
from app.summary.models import ConsultationSummaryResult
from app.summary.task import render_for_billing_codes
from app.tasks.base import ExtractionTask, PreparedPrompt
from app.tasks.schema import to_strict_schema

# Selecting among near-identical French tariff variants (differing on axes buried in prose)
# is a harder task than the structural extraction consultation_summary does — mistral-small
# is kept there, but billing_codes gets the stronger model. See app/tasks/base.py's
# ExtractionTask.model and app/extraction/engine.py's per-model client cache.
MODEL = "mistral-medium-latest"


@dataclass(frozen=True)
class BillingCodesInput:
    """BillingCodesTask's input bundle — see app/tasks/base.py's ExtractionTask docstring
    for why this task doesn't just take a string like ConsultationSummaryTask does.

    `summary` is the structured consultation_summary result, not its rendered text: both
    RAMQCodesRetriever (query planning per procedure/add-on) and this task's own prompt
    (rendering + PHI stripping via render_for_billing_codes) need the structured object.
    `transcript` is the raw encounter transcript, sent alongside the summary so the
    selection step isn't bottlenecked by whatever detail the summarizer happened to drop —
    see app/extraction/pipeline.py's docstring for why the summary alone isn't enough here.
    `context` is whatever administrative facts app/ramq_codes/context_builder.py could
    resolve for this encounter."""

    summary: ConsultationSummaryResult
    transcript: str
    context: BillingContext


SYSTEM_PROMPT = """\
You extract RAMQ billing codes from a clinical encounter for physician review — never a
final billing submission. You are given three things: a candidate list of RAMQ codes (the
only codes you may choose from), a structured consultation summary, and the raw encounter
transcript the summary was built from.

Your answer has four parts, written in this order:

1. `analysis` — before choosing any code, 3 to 6 short sentences: the setting and kind of
   encounter; then every distinct billable service actually performed, one by one — the
   visit itself, and each procedure, test, supplement (travel, time of day, interpreter...),
   meeting, form or certificate done during the same encounter; which visit family fits
   and why its sibling variants don't; anything in the summary or transcript that rules a
   candidate out. The codes you then give must follow from this analysis.

2. `codes` — the codes you are sure of: what you would bill for this encounter as it is
   documented. Precision matters here: the physician starts their review with these codes
   ticked, and may approve them without opening the encounter.
   - Retain one code for every distinct service your analysis lists: the visit, plus each
     procedure, supplement, meeting, form or certificate performed in the same encounter.
     These are billed together; one never replaces another, unless a candidate's own
     description or conditions say it includes the other (e.g. a procedure "incluant la
     visite").
   - For one given service, candidates are alternatives (sibling variants of the same act,
     or two visit codes describing the same visit): retain only the one that fits, and list
     the others in `other_possible_codes`. Several visit codes only when the encounter
     really holds several visits (e.g. an admission and a discharge).
   - When a general code and a more specific one both describe the service, retain the
     specific one only if everything its description and conditions require is documented
     (a physician designation, a visit dedicated to that assessment, a duration, a
     setting...). Otherwise retain the general code and list the specific one in
     `other_possible_codes`.

3. `other_possible_codes` — every other candidate you would rate "high" or "medium", not
   already in `codes`: alternatives to a code you kept, variants that differ only on an axis
   that could not be established, additions whose support is partial. Recall matters here:
   the physician sees these unticked, and a correct code you never surfaced is a missed
   claim they will not think to add back. Leave out what you would only rate "low": it
   clutters the review without being billed.

4. `notes` — anything ambiguous not already captured per code: two candidates that could
   both apply, a service mentioned but not clearly performed.

Excluded from both lists: a candidate the summary or transcript contradicts (wrong age,
setting, time of day, an act that was not performed...). If your explanation for a code
would have to say it does not apply, leave the code out entirely.

An empty answer is correct when nothing in the encounter is billable — an insurer form only,
a prescription renewal without a visit, a no-show: both lists empty, and `notes` says why.

Reading the candidate list:
- Each candidate carries its manual taxonomy path, its description, and may carry "when to
  use" guidance and "conditions" (billing restrictions). Candidates sharing a taxonomy path
  are near-identical variants (e.g. differing only on panel size, patient vulnerability,
  registration status, or an age threshold) — read the path and description to understand
  what distinguishes this candidate from its siblings, if any appear in the list. Variants
  contradicting an established fact below have already been removed.
- Only choose codes from the candidate list. Never invent a code that isn't in it.

Established facts and open questions for this encounter:
- The user message may state facts about the billing physician's practice or the identified
  patient (panel size, registration, vulnerability, exact age) as established and
  authoritative. Treat them as certain and prioritize them over anything the transcript or
  summary implies to the contrary — they come from the physician's own records, not from
  inference.
- The user message may also list axes that could NOT be established for this encounter.
  This list is authoritative: an axis on it stays unresolved no matter what the summary or
  transcript says about it — including a clinician's own descriptive language (e.g. a
  transcript calling someone "une patiente vulnérable" is clinical narrative, not the RAMQ
  administrative determination this axis represents). When candidates differ only on such
  an axis, keep the likeliest in `codes` and the others in `other_possible_codes`.
- The user message may also give unconfirmed indications for an unresolved axis (e.g. the
  physician's likely panel size, from a profile entered after the encounter). Use them only
  to decide which variant goes in `codes`; the axis stays unresolved.

For every code you return, in either list:
- `confidence`: "high", "medium", or "low" — how well the summary/transcript supports it.
- `explanation`: short, concrete reason this code fits. Doubts about the encounter itself
  (duration, place, what exactly was done) belong here or in `notes`.
- `supporting_quote`: a verbatim quote from the summary or transcript that grounds it. Never
  paraphrase this field or invent a quote that isn't actually present in either text.
- `needs_confirmation`: only for the unresolved axes listed in the user message. For a code
  whose applicability depends on one of them, one short, specific, physician-facing sentence
  per axis, naming the sibling candidate that differs from it only on that axis, if any.
  Empty in every other case — when no axis is listed, it is always empty.

Rules:
- Everything in your answer must be in french"""


def _format_candidate(c: Code) -> str:
    lines = [f"- {c.number} | {c.header_path}", f"  {c.description}"]
    # when_to_use on visit-family codes is typically a near-verbatim restatement of
    # description (it's derived from the same manual paragraph) — only show entries that add
    # information description doesn't already carry.
    extra_when_to_use = [w for w in c.when_to_use if w not in c.description]
    if extra_when_to_use:
        lines.append(f"  Utilisation : {'; '.join(extra_when_to_use)}")
    if c.rules:
        lines.append(f"  Conditions : {'; '.join(c.rules)}")
    # Fee data is deliberately never shown here — the model doesn't pick a fee (see
    # ExtractedCode.fees' server_only marker); resolve_fees fetches the real list afterward,
    # straight from the candidate's own data, so there's nothing for the prompt to gain by
    # including it.
    return "\n".join(lines)


def _known_facts_text(context: BillingContext) -> str | None:
    lines: list[str] = []
    physician = context.physician
    patient = context.patient

    if physician.confirmed_panel_size is not None:
        lines.append(f"- Clientèle inscrite du médecin : {physician.confirmed_panel_size} patients.")
    if patient.is_registered is not None:
        state = "est inscrit" if patient.is_registered else "n'est pas inscrit"
        lines.append(f"- Le patient {state} auprès de ce médecin.")
    if patient.is_vulnerable is not None:
        state = "est désigné vulnérable" if patient.is_vulnerable else "n'est pas désigné vulnérable"
        lines.append(f"- Le patient {state} au sens de la RAMQ.")
    if patient.age_years is not None:
        # Floored, not rounded: the manual's age bands are in completed years, so a 79.6-year-
        # old is 79 ("moins de 80 ans"), never 80.
        lines.append(f"- Âge du patient au moment de la consultation : {math.floor(patient.age_years)} ans.")

    if not lines:
        return None
    return "Faits établis pour cette facturation (certains, prioritaires sur toute déduction) :\n" + "\n".join(lines)


def _assumed_facts_text(context: BillingContext) -> str | None:
    panel_size = context.physician.assumed_panel_size
    if panel_size is None:
        return None
    return (
        "Indications non confirmées (aucun profil du médecin n'était en vigueur à la date de la "
        "consultation ; valeurs tirées de son plus ancien profil au dossier) :\n"
        f"- Clientèle inscrite du médecin : probablement {panel_size} patients."
    )


def _unresolved_axes_text(unresolved_axes: tuple[str, ...]) -> str | None:
    if not unresolved_axes:
        return None
    lines = [f"- {AXIS_LABELS_FR[axis]}" for axis in unresolved_axes if axis in AXIS_LABELS_FR]
    if not lines:
        return None
    return (
        "Éléments non disponibles pour cette facturation — signalez dans `needs_confirmation` "
        "tout code candidat dont l'admissibilité en dépend :\n" + "\n".join(lines)
    )


class BillingCodesTask(ExtractionTask[BillingCodesInput]):
    name = "billing_codes"
    model = MODEL

    def __init__(self, retriever: ICodesRetriever, codes: ICodeRepository):
        self._retriever = retriever
        self._codes = codes

    async def build_prompt(self, task_input: BillingCodesInput) -> PreparedPrompt:
        collapse_result = await self._retriever.aretrieve(task_input.summary, task_input.context)
        candidate_lines = [_format_candidate(c) for c in collapse_result.candidates]

        prompt_sections = [f"Candidate RAMQ codes:\n{chr(10).join(candidate_lines)}"]

        known_facts = _known_facts_text(task_input.context)
        if known_facts:
            prompt_sections.append(known_facts)

        assumed_facts = _assumed_facts_text(task_input.context)
        if assumed_facts:
            prompt_sections.append(assumed_facts)

        unresolved = _unresolved_axes_text(collapse_result.unresolved_axes)
        if unresolved:
            prompt_sections.append(unresolved)

        summary_text = render_for_billing_codes(task_input.summary)
        prompt_sections.append(f"Consultation summary (normalized view):\n{summary_text}")

        redacted_transcript = nam.redact(task_input.transcript)
        prompt_sections.append(f"Raw transcript (detail-of-record):\n{redacted_transcript}")

        user_message = "\n\n".join(prompt_sections)
        candidate_numbers = frozenset(c.number for c in collapse_result.candidates)

        return PreparedPrompt(
            system_prompt=SYSTEM_PROMPT, user_message=user_message, candidate_numbers=candidate_numbers
        )

    def json_schema(self) -> dict[str, Any]:
        return to_strict_schema(BillingCodesOutput)

    def parse(self, raw: dict[str, Any], prepared: PreparedPrompt) -> BillingCodesResult:
        """The model's two lists (BillingCodesOutput) -> one list, its sure codes first,
        each marked `retained` or not; a code in both lists counts as retained."""
        # Small local models (freeform JSON, no grammar constraint) sometimes collapse a
        # code array to bare code strings instead of the required object shape,
        # especially with a large real candidate list. Drop anything malformed rather than
        # crashing the request — and rather than fabricating an explanation for it, since
        # that field exists specifically so a physician can see the model's reasoning for
        # the suggestion; a made-up explanation would defeat that.
        codes = []
        for key, retained in (("codes", True), ("other_possible_codes", False)):
            codes += [{**c, "retained": retained} if isinstance(c, dict) else c for c in raw.get(key) or []]
        well_formed = [c for c in codes if isinstance(c, dict)]
        dropped_malformed = len(codes) - len(well_formed)

        notes: list[str] = []
        if dropped_malformed:
            notes.append(
                f"{dropped_malformed} candidate code(s) came back from the model in an unexpected "
                "format (missing an explanation) and were dropped rather than shown unverified."
            )

        # Defense in depth: the "only choose from candidates" constraint is stated in the
        # prompt, but nothing before this enforced it server-side (see BACKLOG.md's item on
        # this). candidate_numbers is None for a task with no closed set to check against —
        # never true for this task, but the check is written generically off PreparedPrompt.
        if prepared.candidate_numbers is not None:
            in_set = [c for c in well_formed if c.get("code") in prepared.candidate_numbers]
            dropped_uncandidated = len(well_formed) - len(in_set)
            if dropped_uncandidated:
                notes.append(
                    f"{dropped_uncandidated} code(s) returned by the model were not in the offered "
                    "candidate list and were dropped rather than shown unverified."
                )
            well_formed = in_set

        # Retained codes come first, so a code in both lists keeps its retained entry.
        unique: dict[str, dict] = {}
        for c in well_formed:
            unique.setdefault(c.get("code"), c)
        result = BillingCodesResult.model_validate(
            {"codes": list(unique.values()), "notes": raw.get("notes"), "analysis": raw.get("analysis")}
        )
        self._demote_unsure_retained(result)

        if notes:
            combined = " ".join(notes)
            result.notes = f"{result.notes} {combined}".strip() if result.notes else combined

        return result

    @staticmethod
    def _demote_unsure_retained(result: BillingCodesResult) -> None:
        """A code the model says it is sure of, but without high confidence, is only a
        possible one: over the selection benchmark (backend/benchmarks/README.md), retained
        codes rated medium or low were right 2 times in 26, high ones about 2 in 3. Retained
        codes stay first."""
        for code in result.codes:
            if code.retained and code.confidence != "high":
                code.retained = False
        result.codes.sort(key=lambda code: not code.retained)

    async def resolve_fees(self, result: BillingCodesResult) -> None:
        """Attaches each returned code's real fee list, in place — the model never picks a
        fee (see SYSTEM_PROMPT and ExtractedCode.fees' server_only marker); the physician
        picks among these in the review UI when there's more than one. A by-key lookup, same
        convention as ramq_chatbot's ReferenceExpander: a code with no matching row is left
        with an empty fee list rather than surfaced as missing data."""
        if not result.codes:
            return  # list_by_numbers([]) would build a malformed "IN ()" query

        rows = await self._codes.list_by_numbers([c.code for c in result.codes])
        fees_by_code = {row.number: row.fees for row in rows}
        for code in result.codes:
            code.fees = [CodeFeeOut.model_validate(f.model_dump()) for f in fees_by_code.get(code.code, [])]
