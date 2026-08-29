from typing import Any

from app.ramq_codes.models import BillingCodesResult, Code, CodeFee
from app.ramq_codes.retriever import ICodesRetriever
from app.tasks.base import ExtractionTask
from app.tasks.schema import to_strict_schema

SYSTEM_PROMPT = """\
You extract RAMQ billing codes from a structured consultation summary — a set of clinical
facts already extracted from the original transcript (setting, patient context, exam
findings, procedures, etc.), not the raw transcript itself.

Rules:
- Only choose codes from the candidate list provided in the user message. Never invent a
  code that isn't in that list.
- Each candidate carries a description and may carry "when to use" guidance (extra context
  on the scenario the code is meant for) and/or "conditions" (billing restrictions) taken
  directly from the RAMQ manual. Read them before deciding the code applies:
    - A condition about the patient or the encounter itself (age, vulnerability,
      registration status, what was performed) should be established by the consultation
      summary. If it's violated, or the summary doesn't establish that it's met, exclude
      the code entirely — do not include it at low confidence "just in case".
    - A condition about the billing physician's own practice (e.g. the size of their
      registered-patient panel, a practice restricted to a specialty) is not something a
      clinical encounter would ever establish. Don't exclude a code solely because this
      kind of condition can't be confirmed from the summary: include the best-fitting
      candidate anyway, and use the notes field to flag that the physician must confirm it
      (naming any other candidate that differs only on this axis, so the physician can pick
      the right one).
- Every code's `fee` field must be filled in from that candidate's fee list, never invented:
    - If a candidate has exactly one fee, use it.
    - If a candidate has several fees tied to different conditions (e.g. time of day,
      practice setting), pick the one whose condition the consultation summary establishes.
      If you can't tell which one applies, pick the most defensible one and flag the
      ambiguity in notes (naming the other candidate fee), same as the physician-practice
      condition handling above — don't leave fee blank just because it's ambiguous.
    - If a candidate has no fee data at all, return `fee` with every sub-field null rather
      than omitting it or guessing an amount.
- Every code you return must include an explanation that describes why you choose this code. Explanation should be short and concise.
- The candidate list is a narrowed search result, not a guarantee the correct code is in
  it. An empty codes list is the correct, expected output whenever no candidate is clearly
  supported by the summary — never select the "closest" or "least wrong" candidate just
  to return something.
- Use the notes field to flag anything ambiguous — e.g. two candidate codes that could both
  apply, a service that was mentioned but not clearly performed, or none of the candidates
  fitting the encounter at all.
- This output is a draft for physician review, not a final billing submission."""


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
    line = f"- {c.number} ({c.libelle}): {c.description}"
    if c.when_to_use:
        line += f" [when to use: {'; '.join(c.when_to_use)}]"
    if c.rules:
        line += f" [conditions: {'; '.join(c.rules)}]"
    if c.fees:
        line += f" [fees: {'; '.join(_format_fee(f) for f in c.fees)}]"
    return line


class BillingCodesTask(ExtractionTask):
    name = "billing_codes"

    def __init__(self, retriever: ICodesRetriever):
        self._retriever = retriever

    async def build_prompt(self, consultation_summary_text: str) -> tuple[str, str]:
        candidates = await self._retriever.aretrieve(consultation_summary_text)
        candidate_lines = [_format_candidate(c) for c in candidates]

        prompt_sections = [f"Candidate RAMQ codes:\n{chr(10).join(candidate_lines)}"]
        prompt_sections.append(f"Consultation summary:\n{consultation_summary_text}")

        return SYSTEM_PROMPT, "\n\n".join(prompt_sections)

    def json_schema(self) -> dict[str, Any]:
        return to_strict_schema(BillingCodesResult)

    def parse(self, raw: dict[str, Any]) -> BillingCodesResult:
        # Small local models (freeform JSON, no grammar constraint) sometimes collapse the
        # `codes` array to bare code strings instead of the required {code, description,
        # confidence, explanation} objects, especially with a large real candidate
        # list. Drop anything malformed rather than crashing the request — and rather than
        # fabricating an explanation for it, since that field exists specifically so a
        # physician can see the model's reasoning for the suggestion; a made-up explanation
        # would defeat that.
        codes = raw.get("codes") or []
        well_formed = [c for c in codes if isinstance(c, dict)]
        dropped = len(codes) - len(well_formed)
        raw = {**raw, "codes": well_formed}

        result = BillingCodesResult.model_validate(raw)
        if dropped:
            note = (
                f"{dropped} candidate code(s) came back from the model in an unexpected "
                "format (missing an explanation) and were dropped rather than shown "
                "unverified."
            )
            result.notes = f"{result.notes} {note}".strip() if result.notes else note

        return result
