import re
from typing import Any

from app.models import BillingCodesResult
from app.ramq.reference import RamqCode, get_reference_table
from app.tasks.base import ExtractionTask

SYSTEM_PROMPT = """\
You extract RAMQ billing codes from a structured consultation summary — a set of clinical
facts already extracted from the original transcript (setting, patient context, exam
findings, procedures, etc.), not the raw transcript itself.

Rules:
- Only choose codes from the candidate list provided in the user message. Never invent a
  code that isn't in that list.
- Some candidates carry a trailing "[conditions: ...]" note — read it before deciding the
  code applies. It states a real billing restriction taken directly from the RAMQ manual,
  not a suggestion. Two kinds behave differently:
    - A "patient: ..." condition (age, vulnerability, inscription) or any other billing
      restriction describes something the clinical encounter itself should establish. If
      it's violated, or the consultation summary doesn't establish that it's met, exclude
      the code entirely — do not include it at low confidence "just in case".
    - A "physician eligibility: ..." condition describes a fact about the billing
      physician's own practice (e.g. registered-patient panel size, a practice restricted
      to a specialty) — not something a clinical encounter would ever establish. Don't
      exclude a code solely because this kind of condition can't be confirmed from the
      summary: include the best-fitting candidate anyway, and use the notes field to flag
      that the physician must confirm it (naming the alternative code(s) when multiple
      candidates differ only on this axis, so the physician can pick the right one).
- Some candidates are written as "code1/code2: ... — physician-eligibility variants, pick
  one: code1 if ... ($X); code2 if ... ($Y)" — this is several real codes that are
  otherwise identical, merged onto one line because they only differ by a physician
  eligibility condition (see above). If the visit itself is otherwise supported by the
  summary, pick whichever single code you'd guess is more likely correct, report only
  that one code (not both) in `codes`, and use notes to name the other alternative and say
  the physician needs to confirm which applies.
- Every code you return must include a short verbatim quote from the consultation summary
  provided that describes the specific billed act itself (the exam/service/procedure the
  code's own description names) — not incidental context like the clinic's name alone or a
  medication list. If you can't quote text establishing that the billed act actually
  happened, don't include the code.
- The candidate list is a narrowed search result, not a guarantee the correct code is in
  it. An empty codes list is the correct, expected output whenever no candidate is clearly
  supported by the summary — never select the "closest" or "least wrong" candidate just
  to return something.
- Use the notes field to flag anything ambiguous — e.g. two candidate codes that could both
  apply, a service that was mentioned but not clearly performed, or none of the candidates
  fitting the encounter at all.
- This output is a draft for physician review, not a final billing submission."""

_WHITESPACE_RE = re.compile(r"\s{2,}")
_DOUBLE_PERIOD_RE = re.compile(r"\.\s*\.")


def _base_description(c: RamqCode) -> str:
    """c.description with the physician-eligibility clause (already restated verbatim in
    c.physician, per how this table is ingested) stripped out — the text two candidates
    that differ only by that clause share in common."""
    description = c.description
    if c.physician and c.physician in description:
        description = description.replace(c.physician, "")
    description = _DOUBLE_PERIOD_RE.sub(".", description)
    return _WHITESPACE_RE.sub(" ", description).strip()


def _merge_key(c: RamqCode) -> tuple:
    return (_base_description(c), c.unit, c.patient)


def _patient_condition_text(patient) -> str | None:
    if patient is None:
        return None
    bits = []
    if patient.age:
        bits.append(f"age {patient.age}")
    if patient.vulnerable:
        bits.append("vulnerable")
    if patient.inscription:
        bits.append(patient.inscription)
    return f"patient: {', '.join(bits)}" if bits else None


def _format_candidate_group(group: list[RamqCode]) -> str:
    if len(group) == 1:
        c = group[0]
        # No category suffix here — it's the manual's section/heading breadcrumb, mainly
        # useful for debugging which part of the table a candidate came from, and today's
        # descriptions already restate it inline anyway.
        line = f"- {c.code}: {c.description}"
        conditions = []
        if c.rules:
            conditions.append(c.rules)
        if c.physician:
            conditions.append(f"physician eligibility: {c.physician}")
        patient_text = _patient_condition_text(c.patient)
        if patient_text:
            conditions.append(patient_text)
        if conditions:
            line += f" [conditions: {'; '.join(conditions)}]"
        return line

    # Merged: every member is identical (description, category, unit, rules, patient
    # conditions) except for its physician-eligibility clause and the price that clause
    # determines — list each code as an alternate on one line instead of repeating an
    # otherwise-identical line per code (see build_prompt's docstring comment for why).
    base = group[0]
    base_desc = _base_description(base)
    line = f"- {'/'.join(c.code for c in group)}: {base_desc}"
    conditions = []
    if base.rules:
        conditions.append(base.rules)
    patient_text = _patient_condition_text(base.patient)
    if patient_text:
        conditions.append(patient_text)
    if conditions:
        line += f" [conditions: {'; '.join(conditions)}]"

    alternates = [
        f"{c.code} if {c.physician} ({f'${c.price_cad:.2f}' if c.price_cad is not None else 'price n/a'})"
        for c in group
    ]
    line += f" — physician-eligibility variants, pick one: {'; '.join(alternates)}"
    return line


class BillingCodesTask(ExtractionTask):
    name = "billing_codes"

    def build_prompt(self, consultation_summary_text: str) -> tuple[str, str]:
        reference = get_reference_table()
        candidates = reference.candidates_for(consultation_summary_text)

        # Group candidates that are identical except for their physician-eligibility split
        # (e.g. a "clientèle inscrite de moins/plus de 500 patients" pair) into one merged
        # line instead of N near-duplicate lines. This isn't cosmetic: a real candidate
        # list can carry ~15 lines that differ from each other only in a clause like this,
        # and spreading them across separate lines caused the model to lose track of which
        # was which and pattern-match/reject the whole cluster — verified by isolating one
        # such pair outside the full list, where the same model reasoned about it
        # correctly. Only candidates that share everything (description minus the
        # physician-condition text, category, unit, rules, patient conditions) are merged;
        # anything that also differs clinically (age bracket, vulnerability, pregnancy
        # stage) stays on its own line since that's a real distinction, not noise.
        groups: dict[tuple, list[RamqCode]] = {}
        for c in candidates:
            groups.setdefault(_merge_key(c), []).append(c)

        candidate_lines = [_format_candidate_group(g) for g in groups.values()]

        prompt_sections = [f"Candidate RAMQ codes:\n{chr(10).join(candidate_lines)}"]
        prompt_sections.append(f"Consultation summary:\n{consultation_summary_text}")

        return SYSTEM_PROMPT, "\n\n".join(prompt_sections)

    def json_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "codes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "description": {"type": "string"},
                            "confidence": {"type": "number"},
                            "supporting_quote": {"type": "string"},
                        },
                        "required": [
                            "code",
                            "description",
                            "confidence",
                            "supporting_quote",
                        ],
                        "additionalProperties": False,
                    },
                },
                "notes": {"type": ["string", "null"]},
            },
            "required": ["codes", "notes"],
            "additionalProperties": False,
        }

    def parse(self, raw: dict[str, Any]) -> BillingCodesResult:
        # Small local models (freeform JSON, no grammar constraint) sometimes collapse the
        # `codes` array to bare code strings instead of the required {code, description,
        # confidence, supporting_quote} objects, especially with a large real candidate
        # list. Drop anything malformed rather than crashing the request — and rather than
        # fabricating a supporting_quote for it, since that field exists specifically so a
        # physician can verify the suggestion against the transcript; showing a code with a
        # made-up quote would defeat that.
        codes = raw.get("codes") or []
        well_formed = [c for c in codes if isinstance(c, dict)]
        dropped = len(codes) - len(well_formed)
        raw = {**raw, "codes": well_formed}

        result = BillingCodesResult.model_validate(raw)
        if dropped:
            note = (
                f"{dropped} candidate code(s) came back from the model in an unexpected "
                "format (missing a supporting quote) and were dropped rather than shown "
                "unverified."
            )
            result.notes = f"{result.notes} {note}".strip() if result.notes else note

        # Price is looked up here, deterministically, from the reference table — never
        # taken from the model's output. Claude's JSON schema (above) has no price field,
        # so there's nothing for it to hallucinate; a monetary figure should come from a
        # known source, not LLM recall.
        reference = get_reference_table()
        prices: list[float] = []
        for extracted in result.codes:
            entry = reference.get(extracted.code)
            if entry is not None and entry.price_cad is not None:
                extracted.price_cad = entry.price_cad
                prices.append(entry.price_cad)

        result.total_price_cad = sum(prices) if prices else None
        return result
