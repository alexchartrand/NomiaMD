"""Unit tests for the billing_codes step's pieces (app/ramq_codes/): BillingPromptBuilder's
candidate-formatting/context-rendering, SelectionParser's malformed-/uncandidated-output
handling, CodeSelector's call (mocked model), and FeeResolver — the full pipeline is covered
end to end in tests/test_extraction.py and tests/test_pipeline.py."""

from datetime import date, time
from unittest.mock import AsyncMock, patch

from app.care_setting import CareSetting
from app.lancedb.models import CodeRow, CodeRowFee
from app.lancedb.repository import ICodeRepository
from app.llm.schema import to_strict_schema
from app.ramq_codes import BillingPrompt, BillingPromptBuilder, CodeSelector, FeeResolver, SelectionParser
from app.ramq_codes.context import BillingContext, PatientContext, PhysicianContext, ShiftContext
from app.ramq_codes.eligibility import CandidateSet
from app.ramq_codes.models import BillingCodesOutput, BillingCodesResult, Code, CodeFee
from app.ramq_codes.prompt import SYSTEM_PROMPT
from app.shifts import DayType, ShiftPeriod
from app.summary import ConsultationSummaryResult
from tests.llm_helpers import fake_chat_result
from tests.test_consultation_summary import MOCK_RESULT

TRANSCRIPT = "Patiente de 58 ans, suivi diabète, tension artérielle 138/86."
SUMMARY = ConsultationSummaryResult.model_validate(MOCK_RESULT)


class _FakeCodeRepository(ICodeRepository):
    def __init__(self, rows: list[CodeRow] | None = None):
        self._rows_by_number = {row.number: row for row in (rows or [])}
        self.list_by_numbers_calls: list[list[str]] = []

    async def get_by_number(self, number: str) -> CodeRow:
        return self._rows_by_number[number]

    async def list_by_numbers(self, numbers: list[str]) -> list[CodeRow]:
        self.list_by_numbers_calls.append(list(numbers))
        return [self._rows_by_number[n] for n in numbers if n in self._rows_by_number]

    async def hybrid_search(self, text: str, vector: list[float], k: int, eligibility=None, sections=None) -> list:
        raise NotImplementedError("not exercised by FeeResolver")

    async def list_by_header_paths(self, header_paths: list[str], eligibility=None) -> list:
        raise NotImplementedError("not exercised by FeeResolver")


def _prompt(
    codes: list[Code] | None = None,
    context: BillingContext | None = None,
    unresolved_axes: tuple[str, ...] = (),
    transcript: str = TRANSCRIPT,
) -> BillingPrompt:
    candidates = CandidateSet(candidates=codes or [], unresolved_axes=unresolved_axes)
    return BillingPromptBuilder().build(candidates, SUMMARY, transcript, context or BillingContext())


# -- BillingPromptBuilder ---------------------------------------------------------------


def test_build_prompt_returns_the_fixed_system_prompt():
    prompt = _prompt()

    assert prompt.system == SYSTEM_PROMPT


def test_build_prompt_includes_the_raw_transcript_verbatim():
    prompt = _prompt()

    assert TRANSCRIPT in prompt.user


def test_build_prompt_redacts_a_nam_embedded_in_the_transcript():
    prompt = _prompt(transcript="Patient DESR81021001 se présente pour suivi.")

    assert "DESR81021001" not in prompt.user
    assert "[NAM]" in prompt.user


def test_build_prompt_formats_full_candidate_block():
    code = Code(
        number="15801",
        description="Visite de prise en charge d'une maladie chronique",
        header_path="B > Visites sur rendez-vous > Visite de prise en charge",
        when_to_use=("Nouveau patient",),
        rules=("Clientele < 500 patients inscrits",),
        fees=(CodeFee(amount=33.15, amount_text="33,15", context="Par visite", majoration="20%"),),
    )
    prompt = _prompt([code])

    assert "- 15801 | B > Visites sur rendez-vous > Visite de prise en charge" in prompt.user
    assert "Visite de prise en charge d'une maladie chronique" in prompt.user
    assert "Utilisation : Nouveau patient" in prompt.user
    assert "Conditions : Clientele < 500 patients inscrits" in prompt.user


def test_build_prompt_never_shows_fee_data_even_when_the_candidate_has_it():
    # The model doesn't pick a fee any more (see ExtractedCode.fees' server_only marker) —
    # fee data must never reach the prompt at all, even for a candidate that carries it.
    code = Code(
        number="15801",
        description="Visite de prise en charge",
        header_path="x",
        fees=(CodeFee(amount=33.15, amount_text="33,15", context="Par visite", majoration="20%"),),
    )
    prompt = _prompt([code])

    assert "Tarifs" not in prompt.user
    assert "33.15" not in prompt.user


def test_build_prompt_omits_when_to_use_entries_already_in_the_description():
    code = Code(
        number="15801",
        description="Visite de prise en charge d'une maladie chronique",
        header_path="x",
        when_to_use=("Visite de prise en charge d'une maladie chronique",),
    )
    prompt = _prompt([code])

    assert "Utilisation :" not in prompt.user


def test_build_prompt_omits_optional_sections_when_absent():
    code = Code(number="15801", description="Visite de prise en charge", header_path="x")
    prompt = _prompt([code])

    assert "- 15801 | x" in prompt.user
    assert "Utilisation :" not in prompt.user
    assert "Conditions :" not in prompt.user


def test_build_prompt_with_no_candidates_lists_none():
    prompt = _prompt()

    assert "Candidate RAMQ codes:\n" in prompt.user


def test_build_prompt_states_known_facts_as_established():
    context = BillingContext(
        physician=PhysicianContext(panel_size=320),
        patient=PatientContext(age_years=58, is_registered=True, is_vulnerable=False),
    )
    prompt = _prompt(context=context)

    assert "Clientèle inscrite du médecin : 320 patients." in prompt.user
    assert "est inscrit auprès de ce médecin" in prompt.user
    assert "n'est pas désigné vulnérable" in prompt.user
    assert "58 ans" in prompt.user


def test_build_prompt_floors_the_patient_age_to_completed_years():
    # The manual's age bands are in completed years: a 79.6-year-old is "moins de 80 ans",
    # so the prompt must say 79, never round up to 80.
    context = BillingContext(patient=PatientContext(age_years=79.6))
    prompt = _prompt(context=context)

    assert "consultation : 79 ans." in prompt.user


def test_build_prompt_states_a_known_care_setting_as_established():
    prompt = _prompt(context=BillingContext(care_setting=CareSetting.URGENCE))

    assert "Faits établis" in prompt.user
    assert "Lieu de la consultation : service d'urgence" in prompt.user
    # The ER codes' « patient inscrit » means registered at the ER, not with this physician
    # — without saying so, the model rules every ER code out for a non-registered patient.
    assert "« patient inscrit » dans le libellé d'un code désigne un patient inscrit à l'urgence" in prompt.user


def test_build_prompt_explains_the_er_meaning_of_inscrit_only_at_the_er():
    prompt = _prompt(context=BillingContext(care_setting=CareSetting.CABINET))

    assert "Lieu de la consultation : cabinet" in prompt.user
    assert "inscrit à l'urgence" not in prompt.user


def test_build_prompt_states_the_shift_the_day_type_and_the_start_time():
    shift = ShiftContext(ShiftPeriod.SOIR, date(2026, 10, 27), time(16), time(0))
    context = BillingContext(shift=shift, day_type=DayType.SEMAINE, encounter_time=time(18, 30))
    prompt = _prompt(context=context)

    # Midnight as an end reads "24 h", the manual's own wording ("de 20 h à 24 h").
    assert "Quart de travail du médecin : soir, de 16 h à 24 h." in prompt.user
    assert "Jour de la consultation : jour de semaine." in prompt.user
    assert "Heure de début de la consultation : 18 h 30." in prompt.user


def test_build_prompt_says_when_a_shift_ends_the_next_day():
    shift = ShiftContext(ShiftPeriod.NUIT, date(2026, 10, 31), time(23), time(7))
    prompt = _prompt(context=BillingContext(shift=shift, day_type=DayType.FIN_DE_SEMAINE))

    assert "Quart de travail du médecin : nuit, de 23 h à 7 h le lendemain." in prompt.user
    assert "Jour de la consultation : fin de semaine." in prompt.user
    assert "Heure de début" not in prompt.user


def test_build_prompt_omits_known_facts_section_when_context_is_empty():
    prompt = _prompt(context=BillingContext())

    assert "Faits établis" not in prompt.user


def test_build_prompt_names_unresolved_axes_from_the_retriever():
    prompt = _prompt(unresolved_axes=("panel_size",))

    assert "clientèle inscrite" in prompt.user
    assert "needs_confirmation" in prompt.user


# -- the answer's schema ----------------------------------------------------------------


def test_the_schema_describes_the_billing_codes_answer():
    schema = to_strict_schema(BillingCodesOutput)

    assert schema["type"] == "object"
    assert "codes" in schema["required"]


def test_the_schema_never_asks_the_model_for_a_fee():
    # The model never picks a fee (ExtractedCode.fees is resolved server-side after the LLM
    # call, see FeeResolver below) — its server_only marker must keep it out of the schema
    # entirely, at every nesting depth, not just make it optional.
    schema = to_strict_schema(BillingCodesOutput)
    code_schema = schema["properties"]["codes"]["items"]

    assert "fees" not in code_schema["properties"]
    assert "fees" not in code_schema["required"]


def test_the_schema_asks_for_the_analysis_first_then_sure_and_possible_codes():
    """Generation follows property order: the model reasons before it commits to codes."""
    schema = to_strict_schema(BillingCodesOutput)

    assert list(schema["properties"]) == ["analysis", "codes", "other_possible_codes", "notes"]
    for key in ("codes", "other_possible_codes"):
        assert "retained" not in schema["properties"][key]["items"]["properties"]


# -- SelectionParser --------------------------------------------------------------------


def _extracted_code(code: str = "15801") -> dict:
    return {
        "code": code,
        "description": "Visite de prise en charge",
        "confidence": "high",
        "explanation": "quote",
        "supporting_quote": "suivi diabète",
        "needs_confirmation": [],
    }


def _parse(raw: dict, offered: set[str]) -> BillingCodesResult:
    return SelectionParser().parse(raw, offered).result


def test_parse_returns_well_formed_result_unchanged():
    result = _parse({"codes": [_extracted_code()], "notes": "une note"}, {"15801"})

    assert isinstance(result, BillingCodesResult)
    assert [c.code for c in result.codes] == ["15801"]
    assert result.notes == "une note"


def test_parse_drops_bare_string_codes_and_flags_it_in_notes():
    result = _parse(
        {"codes": ["BARE-CODE", _extracted_code()], "notes": None}, {"15801"}
    )

    assert [c.code for c in result.codes] == ["15801"]
    assert "1 candidate code" in result.notes


def test_parse_appends_dropped_note_to_existing_notes_rather_than_overwriting():
    result = _parse({"codes": ["BARE-CODE"], "notes": "ambiguïté existante"}, set())

    assert result.notes.startswith("ambiguïté existante")
    assert "1 candidate code" in result.notes


def test_parse_leaves_notes_untouched_when_nothing_was_dropped():
    result = _parse({"codes": [_extracted_code()], "notes": "une note"}, {"15801"})

    assert result.notes == "une note"


def test_parse_empty_codes_list_is_valid():
    result = _parse({"codes": [], "notes": None}, set())

    assert result.codes == []
    assert result.notes is None


def test_parse_drops_a_code_the_model_invented_outside_the_candidate_set():
    result = _parse(
        {"codes": [_extracted_code("15801"), _extracted_code("99999")], "notes": None},
        {"15801"},
    )

    assert [c.code for c in result.codes] == ["15801"]
    assert "not in the offered candidate list" in result.notes


def test_parse_keeps_every_code_when_all_are_in_the_candidate_set():
    result = _parse(
        {"codes": [_extracted_code("15801")], "notes": None}, {"15801", "15802"}
    )

    assert [c.code for c in result.codes] == ["15801"]
    assert result.notes is None


def test_parse_marks_the_sure_codes_retained_and_lists_them_first():
    result = _parse(
        {
            "analysis": "Visite de suivi.",
            "codes": [_extracted_code("15801")],
            "other_possible_codes": [_extracted_code("15802")],
            "notes": None,
        },
        {"15801", "15802"},
    )

    assert [(c.code, c.retained) for c in result.codes] == [("15801", True), ("15802", False)]
    assert result.analysis == "Visite de suivi."


def test_parse_makes_a_retained_code_without_high_confidence_a_possible_one():
    result = _parse(
        {
            "codes": [_extracted_code("15801") | {"confidence": "medium"}, _extracted_code("15802")],
            "other_possible_codes": [],
            "notes": None,
        },
        {"15801", "15802"},
    )

    assert [(c.code, c.retained) for c in result.codes] == [("15802", True), ("15801", False)]


def test_parse_keeps_a_code_given_in_both_lists_once_as_retained():
    result = _parse(
        {"codes": [_extracted_code("15801")], "other_possible_codes": [_extracted_code("15801")], "notes": None},
        {"15801"},
    )

    assert [(c.code, c.retained) for c in result.codes] == [("15801", True)]


def test_parse_drops_an_invented_or_malformed_possible_code_too():
    result = _parse(
        {"codes": [], "other_possible_codes": [_extracted_code("99999"), "15801"], "notes": None},
        {"15801"},
    )

    assert result.codes == []
    assert "not in the offered candidate list" in result.notes and "unexpected format" in result.notes


def test_a_result_stored_before_the_split_keeps_its_high_confidence_codes_as_retained():
    stored = {"codes": [_extracted_code("15801") | {"confidence": "high"}, _extracted_code("15802") | {"confidence": "medium"}]}

    result = BillingCodesResult.model_validate(stored)

    assert [c.retained for c in result.codes] == [True, False]
    assert result.analysis is None


def test_parse_counts_what_it_dropped():
    drops = SelectionParser().parse(
        {"codes": [_extracted_code("15801"), "BARE"], "other_possible_codes": [_extracted_code("99999")], "notes": None},
        {"15801"},
    ).drops

    assert (drops.raw_code_count, drops.malformed, drops.not_offered) == (3, 1, ("99999",))


# -- CodeSelector -----------------------------------------------------------------------


def _candidates(*numbers: str) -> CandidateSet:
    return CandidateSet(
        candidates=[Code(number=n, description=f"Code {n}", header_path="x") for n in numbers], unresolved_axes=()
    )


async def _select(answer: dict, candidates: CandidateSet, selector: CodeSelector | None = None):
    with patch("app.llm.structured.get_client") as mock_get_client:
        mock_get_client.return_value.chat = AsyncMock(return_value=fake_chat_result(answer, model="mistral-medium-2508"))
        selection = await (selector or CodeSelector()).select(candidates, SUMMARY, TRANSCRIPT, BillingContext())
    return selection, mock_get_client


async def test_select_sends_the_built_prompt_and_parses_the_answer_in_order():
    answer = {
        "codes": [_extracted_code("15801")],
        "other_possible_codes": [_extracted_code("15802") | {"confidence": "medium"}],
        "notes": None,
    }
    selection, mock_get_client = await _select(answer, _candidates("15801", "15802"))

    assert [(c.code, c.retained) for c in selection.result.codes] == [("15801", True), ("15802", False)]
    assert selection.model == "mistral-medium-2508"
    mock_get_client.assert_called_once_with(CodeSelector.DEFAULT_MODEL)
    kwargs = mock_get_client.return_value.chat.call_args.kwargs
    assert kwargs["messages"][0].content == SYSTEM_PROMPT
    assert "- 15801 | x" in kwargs["messages"][1].content
    assert kwargs["response_format"]["json_schema"]["name"] == "billing_codes"
    assert kwargs["response_format"]["json_schema"]["schema"] == to_strict_schema(BillingCodesOutput)


async def test_select_only_keeps_codes_from_the_candidates_it_was_given():
    answer = {"codes": [_extracted_code("15801"), _extracted_code("99999")], "notes": None}
    selection, _ = await _select(answer, _candidates("15801"))

    assert [c.code for c in selection.result.codes] == ["15801"]
    assert selection.drops.not_offered == ("99999",)


async def test_select_drops_malformed_bare_string_codes():
    """A small local model sometimes collapses the codes array to bare code strings
    instead of {code, description, confidence, explanation} objects, especially with
    a large real candidate list — this must not crash the request, and must not fabricate
    an explanation for something the model didn't actually justify."""
    answer = {"codes": ["15801", _extracted_code("15802") | {"confidence": "medium"}], "notes": None}
    selection, _ = await _select(answer, _candidates("15801", "15802"))

    assert [c.code for c in selection.result.codes] == ["15802"]
    assert "1 candidate code" in selection.result.notes


async def test_select_runs_on_its_explicit_model():
    _, mock_get_client = await _select({"codes": [], "notes": None}, _candidates(), CodeSelector(model="qwen3-32b"))

    mock_get_client.assert_called_once_with("qwen3-32b")


# -- FeeResolver ------------------------------------------------------------------------


def _row(number: str, *fees: CodeRowFee) -> CodeRow:
    return CodeRow(number=number, description="", header_path="", fees=list(fees))


async def test_fee_resolver_attaches_every_fee_for_each_code_in_order():
    repository = _FakeCodeRepository(
        [
            _row(
                "15801",
                CodeRowFee(amount=33.15, context="Jour", lieux=["cabinet"]),
                CodeRowFee(amount=40.0, context="Soir", lieux=["domicile"], majoration="20%"),
                CodeRowFee(amount=17, amount_text="17", role=2, unit="unités"),
            )
        ]
    )
    result = _parse({"codes": [_extracted_code("15801")], "notes": None}, {"15801"})

    await FeeResolver(repository).attach(result)

    [code] = result.codes
    assert [f.amount for f in code.fees] == [33.15, 40.0, 17]
    assert code.fees[1].lieux == ["domicile"]
    assert code.fees[1].majoration == "20%"
    assert (code.fees[2].role, code.fees[2].unit) == (2, "unités")


async def test_fee_resolver_leaves_a_code_with_no_matching_row_with_an_empty_list():
    result = _parse({"codes": [_extracted_code("15801")], "notes": None}, {"15801"})

    await FeeResolver(_FakeCodeRepository([])).attach(result)

    assert result.codes[0].fees == []


async def test_fee_resolver_does_not_query_the_repository_for_an_empty_codes_list():
    repository = _FakeCodeRepository([])
    result = _parse({"codes": [], "notes": None}, set())

    await FeeResolver(repository).attach(result)

    assert repository.list_by_numbers_calls == []
