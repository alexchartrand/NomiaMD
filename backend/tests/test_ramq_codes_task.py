"""Unit tests for BillingCodesTask (app/ramq_codes/task.py), isolated from the real
retriever via a small fake — the full pipeline (real prompt -> mocked model call -> parse)
is covered end to end in tests/test_extraction.py; these pin build_prompt's
candidate-formatting logic and parse()'s malformed-output handling directly."""

from app.ramq_codes.models import BillingCodesResult, Code, CodeFee
from app.ramq_codes.task import SYSTEM_PROMPT, BillingCodesTask


class _FakeRetriever:
    def __init__(self, candidates: list[Code]):
        self._candidates = candidates

    async def aretrieve(self, query: str) -> list[Code]:
        return self._candidates


def _task(codes: list[Code]) -> BillingCodesTask:
    return BillingCodesTask(_FakeRetriever(codes))


# -- build_prompt -------------------------------------------------------------------------


async def test_build_prompt_returns_the_fixed_system_prompt():
    task = _task([])

    system_prompt, _ = await task.build_prompt("résumé")

    assert system_prompt == SYSTEM_PROMPT


async def test_build_prompt_includes_the_summary_text_verbatim():
    task = _task([])

    _, user_message = await task.build_prompt("Patiente de 58 ans, suivi diabète.")

    assert "Patiente de 58 ans, suivi diabète." in user_message


async def test_build_prompt_formats_full_candidate_line():
    code = Code(
        number="15801",
        libelle="Visite de prise en charge",
        description="Visite de prise en charge d'une maladie chronique",
        when_to_use=("Nouveau patient",),
        rules=("Clientele < 500 patients inscrits",),
        fees=(CodeFee(amount=33.15, amount_text="33,15", context="Par visite", lieu=None, majoration="20%"),),
    )
    task = _task([code])

    _, user_message = await task.build_prompt("résumé")

    assert "- 15801 (Visite de prise en charge): Visite de prise en charge d'une maladie chronique" in user_message
    assert "[when to use: Nouveau patient]" in user_message
    assert "[conditions: Clientele < 500 patients inscrits]" in user_message
    assert "[fees: 33.15 — Par visite — majoration: 20%]" in user_message


async def test_build_prompt_omits_optional_sections_when_absent():
    code = Code(number="15801", libelle="Visite", description="Visite de prise en charge")
    task = _task([code])

    _, user_message = await task.build_prompt("résumé")

    assert "- 15801 (Visite): Visite de prise en charge" in user_message
    assert "[when to use:" not in user_message
    assert "[conditions:" not in user_message
    assert "[fees:" not in user_message


async def test_build_prompt_formats_unknown_fee_amount_as_question_mark():
    code = Code(
        number="15801",
        libelle="Visite",
        description="",
        fees=(CodeFee(amount=None, amount_text=None, context=None, lieu=None, majoration=None),),
    )
    task = _task([code])

    _, user_message = await task.build_prompt("résumé")

    assert "[fees: ?]" in user_message


async def test_build_prompt_with_no_candidates_lists_none():
    task = _task([])

    _, user_message = await task.build_prompt("résumé")

    assert "Candidate RAMQ codes:\n" in user_message


# -- json_schema ----------------------------------------------------------------------------


def test_json_schema_describes_billing_codes_result():
    task = _task([])

    schema = task.json_schema()

    assert schema["type"] == "object"
    assert "codes" in schema["required"]


# -- parse ------------------------------------------------------------------------------


def _extracted_code(code: str = "15801") -> dict:
    return {
        "code": code,
        "description": "Visite de prise en charge",
        "confidence": 0.9,
        "explanation": "quote",
        "fee": {"amount": 33.15, "when_to_use": None, "majoration": None},
    }


def test_parse_returns_well_formed_result_unchanged():
    task = _task([])

    result = task.parse({"codes": [_extracted_code()], "notes": "une note"})

    assert isinstance(result, BillingCodesResult)
    assert [c.code for c in result.codes] == ["15801"]
    assert result.notes == "une note"


def test_parse_drops_bare_string_codes_and_flags_it_in_notes():
    task = _task([])

    result = task.parse({"codes": ["BARE-CODE", _extracted_code()], "notes": None})

    assert [c.code for c in result.codes] == ["15801"]
    assert "1 candidate code" in result.notes


def test_parse_appends_dropped_note_to_existing_notes_rather_than_overwriting():
    task = _task([])

    result = task.parse({"codes": ["BARE-CODE"], "notes": "ambiguïté existante"})

    assert result.notes.startswith("ambiguïté existante")
    assert "1 candidate code" in result.notes


def test_parse_leaves_notes_untouched_when_nothing_was_dropped():
    task = _task([])

    result = task.parse({"codes": [_extracted_code()], "notes": "une note"})

    assert result.notes == "une note"


def test_parse_empty_codes_list_is_valid():
    task = _task([])

    result = task.parse({"codes": [], "notes": None})

    assert result.codes == []
    assert result.notes is None
