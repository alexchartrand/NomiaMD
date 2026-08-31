from dataclasses import dataclass
from typing import Any

from app.patients import nam
from app.ramq_codes.context import (
    AXIS_AGE_BAND,
    AXIS_PANEL_SIZE,
    AXIS_REGISTRATION,
    AXIS_VULNERABILITY,
    BillingContext,
)
from app.ramq_codes.models import BillingCodesResult, Code, CodeFee
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

# Shared vocabulary with app/ramq_codes/family.py — the axis names CodeFamilySelector
# resolves or leaves unresolved, in the French wording shown to both the model (as an
# established fact, or as something it must ask the physician to confirm) and, via
# ExtractedCode.needs_confirmation, ultimately the physician.
_AXIS_LABELS_FR = {
    AXIS_PANEL_SIZE: "la taille de la clientèle inscrite du médecin (moins de 500 / 500 patients ou plus)",
    AXIS_REGISTRATION: "le statut d'inscription du patient auprès de ce médecin (inscrit ou non)",
    AXIS_VULNERABILITY: "le statut de vulnérabilité du patient au sens de la RAMQ",
    AXIS_AGE_BAND: "l'âge exact du patient (pertinent pour les seuils de 70 ans et 80 ans)",
}


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

Recall matters more than precision here: a physician reviews every suggestion you return
before anything is billed, so a plausible code they reject costs them one glance, while a
correct code you never surfaced is a missed claim they will not think to add back. Include
any candidate with plausible support from the summary or transcript — do not require
certainty. An empty `codes` list is correct only when genuinely nothing in the candidate
list relates to this encounter at all.

Reading the candidate list:
- Each candidate carries its manual taxonomy path, its description, and may carry "when to
  use" guidance, "conditions" (billing restrictions), and a fee list. Its taxonomy path
  groups it with near-identical variants (e.g. differing only on panel size, patient
  vulnerability, registration status, or an age threshold) — read it to understand what
  distinguishes this candidate from its siblings, if any appear in the list.
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
  administrative determination this axis represents). For any candidate whose applicability
  depends on one of those axes, still include it (per the recall-first policy above) but add
  a short, specific, physician-facing sentence to its `needs_confirmation` list naming the
  axis and, if another candidate in the list differs from it only on that axis, naming that
  candidate too so the physician can pick between them. Do this even when the summary or
  transcript reads as if it already answers the question — an unresolved axis is only
  resolved by the established facts above, never by inference from either text.
- A condition about the encounter itself (age, what was performed, referral) that the
  summary/transcript actively contradicts means the candidate does not apply — exclude it
  entirely, don't include it at low confidence "just in case".

For every code you return:
- `confidence`: "high", "medium", or "low" — how well the summary/transcript supports it.
- `explanation`: short, concrete reason this code fits.
- `supporting_quote`: a verbatim quote from the summary or transcript that grounds it. Never
  paraphrase this field or invent a quote that isn't actually present in either text.
- `needs_confirmation`: as described above; empty list when nothing needs confirming.
- `fee`: filled in from that candidate's own fee list, never invented:
    - One fee on the candidate → use it.
    - Several fees tied to different conditions (time of day, practice setting) → pick the
      one the summary/transcript establishes; if you can't tell, pick the most defensible
      one and say so in `notes`, naming the other fee.
    - No fee data at all → return `fee` with every sub-field null.

Use `notes` for anything ambiguous that isn't already captured per-code in
`needs_confirmation` — e.g. two candidates that could both apply for a reason other than an
unresolved axis, or a service mentioned but not clearly performed.

Rules:
- Everything in your answer must be in french"""


def _format_fee(f: CodeFee) -> str:
    amount = f"{f.amount:.2f}" if f.amount is not None else "?"
    parts = [amount]
    if f.context:
        parts.append(f.context)
    if f.lieu:
        parts.append(f"lieu: {f.lieu}")
    if f.majoration:
        parts.append(f"majoration: {f.majoration}")
    return " — ".join(parts)


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
    if c.fees:
        lines.append(f"  Tarifs : {'; '.join(_format_fee(f) for f in c.fees)}")
    return "\n".join(lines)


def _known_facts_text(context: BillingContext) -> str | None:
    lines: list[str] = []
    physician = context.physician
    patient = context.patient

    if physician.number_of_patients is not None:
        band = "moins de 500" if physician.number_of_patients < 500 else "500 patients ou plus"
        lines.append(f"- Clientèle inscrite du médecin : {physician.number_of_patients} patients ({band}).")
    if patient.is_registered is not None:
        state = "est inscrit" if patient.is_registered else "n'est pas inscrit"
        lines.append(f"- Le patient {state} auprès de ce médecin.")
    if patient.is_vulnerable is not None:
        state = "est désigné vulnérable" if patient.is_vulnerable else "n'est pas désigné vulnérable"
        lines.append(f"- Le patient {state} au sens de la RAMQ.")
    if patient.age_years is not None:
        lines.append(f"- Âge du patient au moment de la consultation : {patient.age_years:.0f} ans.")

    if not lines:
        return None
    return "Faits établis pour cette facturation (certains, prioritaires sur toute déduction) :\n" + "\n".join(lines)


def _unresolved_axes_text(unresolved_axes: tuple[str, ...]) -> str | None:
    if not unresolved_axes:
        return None
    lines = [f"- {_AXIS_LABELS_FR[axis]}" for axis in unresolved_axes if axis in _AXIS_LABELS_FR]
    if not lines:
        return None
    return (
        "Éléments non disponibles pour cette facturation — signalez dans `needs_confirmation` "
        "tout code candidat dont l'admissibilité en dépend :\n" + "\n".join(lines)
    )


class BillingCodesTask(ExtractionTask[BillingCodesInput]):
    name = "billing_codes"
    model = MODEL

    def __init__(self, retriever: ICodesRetriever):
        self._retriever = retriever

    async def build_prompt(self, task_input: BillingCodesInput) -> PreparedPrompt:
        collapse_result = await self._retriever.aretrieve(task_input.summary, task_input.context)
        candidate_lines = [_format_candidate(c) for c in collapse_result.candidates]

        prompt_sections = [f"Candidate RAMQ codes:\n{chr(10).join(candidate_lines)}"]

        known_facts = _known_facts_text(task_input.context)
        if known_facts:
            prompt_sections.append(known_facts)

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
        return to_strict_schema(BillingCodesResult)

    def parse(self, raw: dict[str, Any], prepared: PreparedPrompt) -> BillingCodesResult:
        # Small local models (freeform JSON, no grammar constraint) sometimes collapse the
        # `codes` array to bare code strings instead of the required object shape,
        # especially with a large real candidate list. Drop anything malformed rather than
        # crashing the request — and rather than fabricating an explanation for it, since
        # that field exists specifically so a physician can see the model's reasoning for
        # the suggestion; a made-up explanation would defeat that.
        codes = raw.get("codes") or []
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

        raw = {**raw, "codes": well_formed}
        result = BillingCodesResult.model_validate(raw)

        if notes:
            combined = " ".join(notes)
            result.notes = f"{result.notes} {combined}".strip() if result.notes else combined

        return result
