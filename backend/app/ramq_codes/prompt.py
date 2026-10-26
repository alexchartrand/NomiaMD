"""The billing_codes prompt: the system rules, and the user message built from the offered
candidates, the established facts, the consultation summary and the redacted transcript."""

import math
from dataclasses import dataclass

from app.care_setting import CARE_SETTING_LABELS_FR, CareSetting
from app.patients import nam
from app.ramq_codes.context import AXIS_LABELS_FR, BillingContext
from app.ramq_codes.eligibility import CandidateSet
from app.ramq_codes.models import Code
from app.summary import ConsultationSummaryResult, render_for_billing_codes

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
    # ExtractedCode.fees' server_only marker); FeeResolver (fees.py) fetches the real list afterward,
    # straight from the candidate's own data, so there's nothing for the prompt to gain by
    # including it.
    return "\n".join(lines)


def _known_facts_text(context: BillingContext) -> str | None:
    lines: list[str] = []
    physician = context.physician
    patient = context.patient

    if physician.panel_size is not None:
        lines.append(f"- Clientèle inscrite du médecin : {physician.panel_size} patients.")
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
    if context.care_setting is not None:
        lines.append(f"- Lieu de la consultation : {CARE_SETTING_LABELS_FR[context.care_setting]}.")
    if context.care_setting is CareSetting.URGENCE:
        lines.append(
            "- Au service d'urgence, « patient inscrit » dans le libellé d'un code désigne un patient "
            "inscrit à l'urgence (par opposition à un patient admis), sans lien avec l'inscription "
            "auprès d'un médecin de famille : ces codes s'appliquent que le patient soit inscrit ou "
            "non auprès de ce médecin."
        )

    if not lines:
        return None
    return "Faits établis pour cette facturation (certains, prioritaires sur toute déduction) :\n" + "\n".join(lines)


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


@dataclass(frozen=True)
class BillingPrompt:
    system: str
    user: str

    @property
    def chars(self) -> int:
        return len(self.system) + len(self.user)


class BillingPromptBuilder:
    """Pure: the same inputs always give the same prompt. Both the summary and the raw
    transcript go in — the summary is denser, but as the only grounding text it's a lossy
    bottleneck: any clinical detail the summarizer dropped would be unrecoverable here."""

    def build(
        self,
        candidates: CandidateSet,
        summary: ConsultationSummaryResult,
        transcript: str,
        context: BillingContext,
    ) -> BillingPrompt:
        candidate_lines = [_format_candidate(c) for c in candidates.candidates]
        sections = [f"Candidate RAMQ codes:\n{chr(10).join(candidate_lines)}"]
        for optional_section in (
            _known_facts_text(context),
            _unresolved_axes_text(candidates.unresolved_axes),
        ):
            if optional_section:
                sections.append(optional_section)
        sections.append(f"Consultation summary (normalized view):\n{render_for_billing_codes(summary)}")
        sections.append(f"Raw transcript (detail-of-record):\n{nam.redact(transcript)}")
        return BillingPrompt(system=SYSTEM_PROMPT, user="\n\n".join(sections))
