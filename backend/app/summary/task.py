from typing import Any

from app.summary.models import ConsultationSummaryResult
from app.tasks.base import ExtractionTask
from app.tasks.schema import render_instance, render_schema_block, to_strict_schema

_RULES = """\
You are a clinical documentation parser for RAMQ billing preparation in Quebec.
Your ONLY job is to extract structured facts from a medical consultation
transcript or note. You do NOT decide or output a billing code. RAMQ codes
depend on administrative facts (patient registration status, panel size,
exact billing context, prior billing history) that are not present in the
transcript, and are resolved separately by a rules engine against the RAMQ
tariff manual (Manuel des médecins omnipraticiens — Rémunération à l'acte).

Output strict JSON matching the schema below. No prose, no markdown, no
commentary outside the JSON object. If a field cannot be determined from the
transcript, use null (or false/empty list as appropriate) — never guess.

All free-text values in the output (short_description, rationale, notable_findings,
chief_complaint_or_reason_for_visit, notes_uncertain_items, and any other
free-text paraphrase or description field) must be written in French. JSON
keys and enum values (e.g. "high"/"medium"/"low", "single"/"multi",
"cabinet"/"domicile"/etc.) remain exactly as specified in the schema — do not
translate keys or enum values, only free-text content.

============================================================
OUTPUT SCHEMA
============================================================

{schema}

============================================================
RULES
============================================================
1. Never guess administrative facts not derivable from clinical content:
   patient registration/"inscrit" status with a specific physician,
   vulnerability designation (this is a formal RAMQ status, not a clinical
   impression), physician panel size, prior billing history this calendar
   year. Extract only what the transcript actually documents or states, and
   leave everything else null/false for the downstream rules engine.
2. "encounter_category_hint" is a hint only, to help route the note to the
   right section of the tariff manual. It is explicitly NOT a billing code
   and must never be treated as one downstream.
3. Distinguish clearly between things the transcript explicitly states
   (set the field) and things you would need to infer or assume (leave null
   and add a note instead).
4. If duration is not explicitly stated, you may estimate it from context
   in duration_minutes, but duration_explicitly_stated must be false, and add
   a note.
5. procedures_performed should be an empty list if no procedure beyond
   history-taking/examination occurred.
6. Output valid JSON only, matching the schema exactly. No text before or
   after the JSON object.
7. Write all free-text field values in French (Québécois medical French is
   fine). Do not translate JSON field names or the fixed enum values defined
   in the schema."""

SYSTEM_PROMPT = _RULES.format(schema=render_schema_block(ConsultationSummaryResult))


def render_for_billing_codes(result: ConsultationSummaryResult) -> str:
    """Renders a ConsultationSummaryResult back into a single French text blob — this,
    not the raw transcript, is what billing_codes/task.py sends to the model (both for RAMQ
    candidate retrieval and as the text its supporting_quote must be grounded in). Using
    the already-extracted, denser summary instead of a long freeform dictation is the
    point of the two-stage pipeline (app/extraction/pipeline.py): it retrieves RAMQ
    candidates more reliably and grounds the billing model's reasoning in facts already
    pulled out once, rather than re-reading the whole transcript. The rendering itself
    (labels, which fields show up, empty/null handling) is generic — see
    app/tasks/schema.py — and driven by the fr_label/description metadata on
    ConsultationSummaryResult's fields in app/summary/models.py, so a schema change
    here doesn't require touching this function.

    Strips the patient's name and NAM first: this rendering is both the retrieval query and
    the grounding text for billing_codes' supporting_quote, so the identity fields must never
    reach that prompt — sanitized here at the boundary rather than via a generic opt-out flag
    on the shared schema renderer, since the rule is "billing_codes must not see identity",
    not "these fields are never renderable" (a future "voir le résumé extrait" view still
    should). Stripping the NAM matters most: it's a direct patient identifier that would
    otherwise be sent to the embedding endpoint as part of the retrieval query on every
    extraction.
    """
    return render_instance(
        result.model_copy(
            update={
                "patient_information": result.patient_information.model_copy(
                    update={"name_as_stated": None, "ramq_number_as_stated": None}
                )
            }
        )
    )


class ConsultationSummaryTask(ExtractionTask):
    name = "consultation_summary"

    async def build_prompt(self, transcript: str) -> tuple[str, str]:
        return SYSTEM_PROMPT, f"Transcript:\n{transcript}\n\nExtract the structured facts per your instructions."

    def json_schema(self) -> dict[str, Any]:
        return to_strict_schema(ConsultationSummaryResult)

    def parse(self, raw: dict[str, Any]) -> ConsultationSummaryResult:
        return ConsultationSummaryResult.model_validate(raw)
