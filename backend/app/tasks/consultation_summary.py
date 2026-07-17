from typing import Any

from app.models import ConsultationSummaryResult
from app.tasks.base import ExtractionTask

SYSTEM_PROMPT = """\
You extract a structured summary of a clinical encounter transcript, focused on the facts
that matter for RAMQ billing — visit type/location, and the patient-eligibility axes that
gate which RAMQ codes apply (age, vulnerability, inscription status) — plus a short
clinical summary (chief complaint, acts performed, diagnoses, plan) for physician review.

Rules:
- Every field is null/empty unless the transcript actually establishes it — do not infer or
  guess a value (e.g. don't assume "non vulnérable" just because vulnerability wasn't
  mentioned; leave it null instead). This output may inform which RAMQ codes apply, so a
  wrong guess is worse than an honest null.
- patient.evidence must be a short verbatim quote from the transcript backing whichever of
  patient.age/vulnerable/inscription_status you filled in — leave it null if none of those
  three fields were filled in.
- Keep chief_complaint, acts_performed, diagnoses, and plan in the same language as the
  transcript and grounded in it — don't translate, embellish, or add clinical detail the
  transcript doesn't contain.
- acts_performed should list exams/procedures/interventions the transcript says actually
  happened during this encounter, not things merely discussed, ordered for later, or part
  of the patient's history.
- Use notes to flag anything ambiguous or that needs physician review before this summary
  is used to inform billing.
- This output is a draft for physician review, not a final medical record entry."""


class ConsultationSummaryTask(ExtractionTask):
    name = "consultation_summary"

    def build_prompt(self, transcript: str) -> tuple[str, str]:
        return SYSTEM_PROMPT, f"Transcript:\n{transcript}"

    def json_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "chief_complaint": {"type": ["string", "null"]},
                "visit_type": {"type": ["string", "null"]},
                "visit_location": {"type": ["string", "null"]},
                "acts_performed": {"type": "array", "items": {"type": "string"}},
                "diagnoses": {"type": "array", "items": {"type": "string"}},
                "patient": {
                    "type": "object",
                    "properties": {
                        "age": {"type": ["integer", "null"]},
                        "vulnerable": {"type": ["boolean", "null"]},
                        "inscription_status": {"type": ["string", "null"]},
                        "evidence": {"type": ["string", "null"]},
                    },
                    "required": ["age", "vulnerable", "inscription_status", "evidence"],
                    "additionalProperties": False,
                },
                "plan": {"type": ["string", "null"]},
                "notes": {"type": ["string", "null"]},
            },
            "required": [
                "chief_complaint",
                "visit_type",
                "visit_location",
                "acts_performed",
                "diagnoses",
                "patient",
                "plan",
                "notes",
            ],
            "additionalProperties": False,
        }

    def parse(self, raw: dict[str, Any]) -> ConsultationSummaryResult:
        return ConsultationSummaryResult.model_validate(raw)
