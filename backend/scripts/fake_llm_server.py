"""A tiny fake chat completions server, for testing and debugging the extraction
pipeline and the ramq_chatbot task (and the frontend end-to-end) without calling the real
Mistral API.

Speaks the same wire protocol app/extraction/engine.py's and app/ramq_chatbot/factory.py's
MistralAI clients use (POST /v1/chat/completions, Mistral's own request/response shape).
Point the app at it by setting MISTRAL_ENDPOINT=http://localhost:8080 before starting the
backend. It's deliberately "dumb": every request is routed to one of four fake responses by
a marker unique to that caller's fixed prompt text (see _classify_request) — never by which
endpoint was hit, since they all share this one.

- consultation_summary: matched on "encounter_category_hint", only ever present in that
  task's rendered schema. Echoes the transcript's own **Patient :**/**NAM :**/
  **Date/heure :** header fields back as the extracted identity/date (real fixtures under
  consultations/ all carry these — see CLAUDE.md), so the NAM-matching UI path is
  exercisable without a real model. Returns JSON matching that task's schema.
- billing_codes: the default/fallback bucket. Parses the candidate RAMQ codes out of the
  prompt (built by app/ramq_codes/task.py::build_prompt) and picks a fixed number of them
  back, with a placeholder confidence/quote and a real fee parsed out of that same
  candidate's own [fees: ...] bracket (never invented, mirrors what the real model is
  instructed to do). Returns JSON matching that task's schema.
- ramq_chatbot_answer: matched on a fixed line from app/ramq_chatbot/engine.py's
  SYSTEM_PROMPT. Returns plain markdown text (not JSON — RAMQManualQueryEngine reads the
  chat response verbatim) that echoes back the query text pulled from the current turn's
  "Query: ..." line.
- ramq_chatbot_query_gen: app/ramq_chatbot/query_generator.py's LLMQueryGenerator generates
  search-fanout queries via a bare completion call with no system message at all, so this
  bucket is matched on a fixed line from its QUERY_GEN_PROMPT found in the user message
  instead. Returns a couple of plain text lines (no JSON) derived from the real query, which
  LLMQueryGenerator splits on newlines into fake sub-queries.

This exercises each pipeline (retrieval -> prompt -> parse -> API -> frontend)
deterministically, without depending on any real model's behavior or making a real API call
for chat completions. (Embeddings are a separate client with no fake/override — retrieval
still calls the real Mistral embeddings API even under this fake server.)

    python scripts/fake_llm_server.py [--port 8080] [--pick 2]
"""

import argparse
import json
import re
import time

from fastapi import FastAPI, Request

app = FastAPI(title="fake-llm")

# Matches the "- CODE: description" prefix _format_candidate() always emits (see
# app/ramq_codes/task.py) — when-to-use/conditions brackets are ignored, not part of
# this fake's stub output. The fees bracket is pulled separately below, so the fake fee
# is the candidate's own real fee (never invented) same as the real model is instructed to.
_CANDIDATE_RE = re.compile(r"^- (?P<code>\S+): (?P<description>[^\[]+?)(?: \[|$)", re.MULTILINE)

# _format_candidate()/_format_fee() (app/ramq_codes/task.py) always render a line's fees
# as "[fees: AMOUNT — when_to_use — majoration: X; AMOUNT2 — ...]", AMOUNT being "?" when
# the candidate's own fee amount is null.
_LINE_RE = re.compile(r"^- \S+: .*$", re.MULTILINE)
_FEES_BRACKET_RE = re.compile(r"\[fees: (?P<fees>[^\]]*)\]")
_FEE_AMOUNT_RE = re.compile(r"^(\d+(?:\.\d+)?)$")


def _fake_fee_for_code(user_message: str, code: str) -> dict:
    line_match = next(
        (m for m in _LINE_RE.finditer(user_message) if m.group(0).startswith(f"- {code}:")), None
    )
    fees_match = _FEES_BRACKET_RE.search(line_match.group(0)) if line_match else None
    if not fees_match:
        return {"amount": None, "when_to_use": None, "majoration": None}

    first_fee = fees_match.group("fees").split(";")[0].strip()
    parts = [p.strip() for p in first_fee.split(" — ")]
    amount_match = _FEE_AMOUNT_RE.match(parts[0])
    majoration = next((p.removeprefix("majoration:").strip() for p in parts[1:] if p.startswith("majoration:")), None)
    when_to_use = next((p for p in parts[1:] if not p.startswith("majoration:")), None)
    return {
        "amount": float(amount_match.group(1)) if amount_match else None,
        "when_to_use": when_to_use,
        "majoration": majoration,
    }

# Same field format app/sample_patients/service.py parses (**Field :** value), used to echo identity
# back out of the transcript embedded in consultation_summary's user message.
_FIELD_RE = re.compile(r"^\*\*(.+?)\s*:\*\*\s*(.*)$", re.MULTILINE)
_AGE_SEX_RE = re.compile(r"(\d+)\s*(ans|mois)\s*\((\w)\)")

PICK = 2  # overridden by --pick at startup

# Fixed, non-templated first line of each prompt (see module docstring) — used to tell the
# four request shapes apart. ramq_chatbot's query-gen call carries no system message at all
# (see module docstring), so it's matched on the user message instead of the other two.
_RAMQ_CHATBOT_SYSTEM_MARKER = "RAMQ billing specialist chatbot"  # app/ramq_chatbot/engine.py SYSTEM_PROMPT
_RAMQ_CHATBOT_QUERY_GEN_MARKER = "generates multiple search queries based on a single input query"  # app/ramq_chatbot/query_generator.py QUERY_GEN_PROMPT

# Matches the trailing "Query: {query_str}" line both engine.py's USER_MESSAGE_TEMPLATE and
# query_generator.py's QUERY_GEN_PROMPT render. Context/instruction text always precedes it
# in both templates, so taking the LAST match is always the real query, never a coincidental
# "Query:" elsewhere in the message.
_QUERY_LINE_RE = re.compile(r"^\s*Query:\s*(?P<query>.*)$", re.MULTILINE)


def _extract_query_text(user_message: str) -> str:
    matches = _QUERY_LINE_RE.findall(user_message)
    return matches[-1].strip() if matches else user_message.strip()


def _classify_request(system_message: str, user_message: str) -> str:
    # "encounter_category_hint" only ever appears in consultation_summary's rendered
    # schema (app/summary/models.py) — no other caller's system prompt mentions it.
    if "encounter_category_hint" in system_message:
        return "consultation_summary"
    if _RAMQ_CHATBOT_SYSTEM_MARKER in system_message:
        return "ramq_chatbot_answer"
    if _RAMQ_CHATBOT_QUERY_GEN_MARKER in user_message:
        return "ramq_chatbot_query_gen"
    return "billing_codes"


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
            "explanation": "(stub explanation — fake LLM, not a real extraction)",
            "fee": _fake_fee_for_code(user_message, code),
        }
        for code, description in chosen
    ]
    notes = (
        None
        if codes
        else "Fake LLM: no candidate codes were present in the prompt to pick from."
    )
    return json.dumps({"codes": codes, "notes": notes})


def _fake_ramq_chatbot_answer_content(user_message: str) -> str:
    query = _extract_query_text(user_message)
    return (
        "**Réponse générée par le faux LLM (fake_llm_server.py)** — aucune analyse réelle "
        "du manuel RAMQ effectuée.\n\n"
        f"Question reçue : {query}"
    )


def _fake_query_gen_content(user_message: str) -> str:
    query = _extract_query_text(user_message)
    return (
        f"Recherche RAMQ (faux LLM) — variante 1 pour : {query}\n"
        f"Recherche RAMQ (faux LLM) — variante 2 pour : {query}"
    )


_FAKE_CONTENT_BY_BUCKET = {
    "consultation_summary": _fake_consultation_summary_content,
    "ramq_chatbot_answer": _fake_ramq_chatbot_answer_content,
    "ramq_chatbot_query_gen": _fake_query_gen_content,
    "billing_codes": _fake_billing_codes_content,
}


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


def _last_message_content(messages: list, role: str) -> str:
    # The LAST matching-role message, not the first: extraction calls only ever carry one
    # message per role, but ramq_chatbot's final-answer call can carry prior turns from
    # `history` before the current-turn message — taking the first would grab a stale turn.
    return _content_to_text(next((m["content"] for m in reversed(messages) if m.get("role") == role), ""))


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    system_message = _last_message_content(messages, "system")
    user_message = _last_message_content(messages, "user")

    content = _FAKE_CONTENT_BY_BUCKET[_classify_request(system_message, user_message)](user_message)

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
