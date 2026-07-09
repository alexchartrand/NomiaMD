from typing import Any

from app.models import BillingCodesResult
from app.ramq.reference import get_reference_table
from app.tasks.base import ExtractionTask

SYSTEM_PROMPT = """\
You extract RAMQ billing codes from a clinical encounter transcript for physician review.

Rules:
- Only choose codes from the candidate list provided in the user message. Never invent a
  code that isn't in that list.
- Every code you return must include a short verbatim quote from the transcript that
  justifies it — a physician will use this to verify the suggestion before submitting it.
- If the transcript doesn't clearly support any candidate code, return an empty codes list
  rather than guessing.
- Use the notes field to flag anything ambiguous (e.g. two candidate codes that could both
  apply, or a service that was mentioned but not clearly performed).
- This output is a draft for physician review, not a final billing submission."""


class BillingCodesTask(ExtractionTask):
    name = "billing_codes"

    def build_prompt(self, transcript: str) -> tuple[str, str]:
        candidates = get_reference_table().candidates_for(transcript)
        candidate_lines = "\n".join(
            f"- {c.code}: {c.description} (category: {c.category})" for c in candidates
        )
        user_message = (
            f"Candidate RAMQ codes:\n{candidate_lines}\n\n"
            f"Transcript:\n{transcript}"
        )
        return SYSTEM_PROMPT, user_message

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
        result = BillingCodesResult.model_validate(raw)

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
