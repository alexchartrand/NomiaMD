"""A tiny fake chat completions server, for testing and debugging the extraction
pipeline (and the frontend end-to-end) without calling the real Mistral API.

Speaks the same wire protocol app/extraction/engine.py's MistralAI client uses (POST
/v1/chat/completions, Mistral's own request/response shape). Point the app at it by
setting MISTRAL_ENDPOINT=http://localhost:8080 before starting the backend. It's
deliberately "dumb": billing_codes/pipeline.py's two calls are told apart by a marker
unique to consultation_summary's rendered schema (see _is_consultation_summary_request).
For consultation_summary it echoes the transcript's own **Patient :**/**NAM :**/
**Date/heure :** header fields back as the extracted identity/date (real fixtures under
consultations/ all carry these — see CLAUDE.md), so the NAM-matching UI path is exercisable
without a real model. For billing_codes it parses the candidate RAMQ codes out of the
prompt (built by app/ramq_codes/task.py::build_prompt) and picks a fixed number of them
back, with placeholder confidence/quote/fee values. This exercises the whole pipeline
(retrieval -> prompt -> parse -> API -> frontend) deterministically, without depending on
any real model's behavior.

    python scripts/fake_llm_server.py [--port 8080] [--pick 2]
"""

import argparse
import json
import re
import time

from fastapi import FastAPI, Request

app = FastAPI(title="fake-llm")

# Matches the "- CODE: description" prefix _format_candidate() always emits (see
# app/ramq_codes/task.py) — the rest of the line (when-to-use/conditions/fees
# brackets) is ignored, not part of this fake's stub output.
_CANDIDATE_RE = re.compile(r"^- (?P<code>\S+): (?P<description>[^\[]+?)(?: \[|$)", re.MULTILINE)

# Same field format sample_patients.py parses (**Field :** value), used to echo identity
# back out of the transcript embedded in consultation_summary's user message.
_FIELD_RE = re.compile(r"^\*\*(.+?)\s*:\*\*\s*(.*)$", re.MULTILINE)
_AGE_SEX_RE = re.compile(r"(\d+)\s*(ans|mois)\s*\((\w)\)")

PICK = 2  # overridden by --pick at startup


def _is_consultation_summary_request(system_message: str) -> bool:
    # "encounter_category_hint" only ever appears in consultation_summary's rendered
    # schema (app/summary/models.py) — billing_codes' system prompt never mentions it.
    return "encounter_category_hint" in system_message


def _fake_consultation_summary_content(user_message: str) -> str:
    fields = dict(_FIELD_RE.findall(user_message))

    patient_field = fields.get("Patient", "")
    name_as_stated = patient_field.split("—")[0].strip() or None

    age_years = age_months = None
    sex = None
    age_match = _AGE_SEX_RE.search(patient_field)
    if age_match:
        value, unit, sex_letter = age_match.groups()
        sex = sex_letter
        if unit == "ans":
            age_years = float(value)
        else:
            age_months = float(value)

    ramq_number_as_stated = fields.get("NAM") or None
    date_raw = fields.get("Date/heure")
    date_value = date_raw.split(",")[0].strip() if date_raw else None

    result = {
        "short_description": "Résumé généré par le faux LLM (fake_llm_server.py) — aucune analyse réelle.",
        "encounter_setting": {
            "location_type": "cabinet",
            "location_detail": None,
            "date": date_value,
            "time_start": None,
            "time_end": None,
            "duration_minutes": None,
            "duration_explicitly_stated": False,
            "appointment_type": "inconnu",
        },
        "patient_information": {
            "age_years": age_years,
            "age_months_if_infant": age_months,
            "sex_if_stated": sex,
            "name_as_stated": name_as_stated,
            "ramq_number_as_stated": ramq_number_as_stated,
            "pregnancy_context": {"present": False, "trimester": None},
            "relevant_vulnerability_or_context_mentioned": [],
            "new_or_established_patient_language": None,
        },
        "referral_information": {
            "present": False,
            "referral_type": "aucune",
            "requester_role": None,
            "requester_identifier_mentioned": None,
            "reason_for_referral": None,
            "written_report_back_required_or_produced": None,
        },
        "clinical_summary": {
            "chief_complaint_or_reason_for_visit": "Motif non déterminé (faux LLM).",
            "systems_or_body_regions_involved": [],
            "single_vs_multi_system": "unclear",
            "history_taken": None,
            "new_treatment_initiated": None,
            "existing_treatment_reviewed_or_adjusted": None,
            "diagnosis_or_impression_stated": None,
            "recommendations_given_to_patient": None,
            "orders_or_prescriptions_mentioned": None,
        },
        "physical_examination": {
            "performed": None,
            "regions_or_systems_examined": [],
            "special_exam_type": [],
            "notable_findings": None,
        },
        "procedures_performed": [],
        "encounter_category_hint": {
            "best_guess_category": "autre_ou_indetermine",
            "confidence": "low",
            "rationale": "Faux LLM (fake_llm_server.py) — aucune analyse réelle effectuée.",
        },
        "possible_billable_add_ons": [],
        "notes_uncertain_items": [],
    }
    return json.dumps(result)


def _fake_billing_codes_content(user_message: str) -> str:
    candidates = _CANDIDATE_RE.findall(user_message)
    chosen = candidates[:PICK]
    codes = [
        {
            "code": code,
            "description": description,
            "confidence": 0.5,
            "supporting_quote": "(stub quote — fake LLM, not a real extraction)",
            "fee": {"amount": None, "when_to_use": None, "majoration": None},
        }
        for code, description in chosen
    ]
    notes = (
        None
        if codes
        else "Fake LLM: no candidate codes were present in the prompt to pick from."
    )
    return json.dumps({"codes": codes, "notes": notes})


@app.get("/v1/models")
def list_models():
    return {"object": "list", "data": [{"id": "fake-llm", "object": "model"}]}


def _content_to_text(content) -> str:
    """Message content is a bare string over the OpenAI wire format, but the Mistral
    client (llama_index's MistralAI) always sends it as a list of {"type": "text", ...}
    chunks instead — handle both."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(chunk.get("text", "") for chunk in content if isinstance(chunk, dict))
    return ""


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    system_message = _content_to_text(
        next((m["content"] for m in messages if m.get("role") == "system"), "")
    )
    user_message = _content_to_text(
        next((m["content"] for m in messages if m.get("role") == "user"), "")
    )

    content = (
        _fake_consultation_summary_content(user_message)
        if _is_consultation_summary_request(system_message)
        else _fake_billing_codes_content(user_message)
    )

    return {
        "id": "fake-llm-0",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model", "fake-llm"),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        # Required by mistralai's ChatCompletionResponse model, unused by the pipeline.
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument(
        "--pick", type=int, default=2, help="How many candidate codes to echo back per request."
    )
    args = parser.parse_args()

    global PICK
    PICK = args.pick

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
