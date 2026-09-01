"""Unit tests for BillingCodesTask (app/ramq_codes/task.py), isolated from the real
retriever via a small fake — the full pipeline (real prompt -> mocked model call -> parse)
is covered end to end in tests/test_extraction.py; these pin build_prompt's
candidate-formatting/context-rendering logic and parse()'s malformed-/uncandidated-output
handling directly."""

from app.lancedb.models import CodeRow, CodeRowFee
from app.lancedb.repository import ICodeRepository
from app.ramq_codes.context import BillingContext, PatientContext, PhysicianContext
from app.ramq_codes.family import FamilyCollapseResult
from app.ramq_codes.models import BillingCodesResult, Code, CodeFee
from app.ramq_codes.task import SYSTEM_PROMPT, BillingCodesInput, BillingCodesTask
from app.tasks.base import PreparedPrompt
from tests.test_consultation_summary import MOCK_RESULT
from app.summary import ConsultationSummaryResult

TRANSCRIPT = "Patiente de 58 ans, suivi diabète, tension artérielle 138/86."
SUMMARY = ConsultationSummaryResult.model_validate(MOCK_RESULT)


class _FakeRetriever:
    def __init__(self, candidates: list[Code], unresolved_axes: tuple[str, ...] = ()):
        self._result = FamilyCollapseResult(candidates=candidates, unresolved_axes=unresolved_axes)
        self.last_call: tuple | None = None

    async def aretrieve(self, summary, context) -> FamilyCollapseResult:
        self.last_call = (summary, context)
        return self._result


class _FakeCodeRepository(ICodeRepository):
    def __init__(self, rows: list[CodeRow] | None = None):
        self._rows_by_number = {row.number: row for row in (rows or [])}
        self.list_by_numbers_calls: list[list[str]] = []

    async def get_by_number(self, number: str) -> CodeRow:
        return self._rows_by_number[number]

    async def list_by_numbers(self, numbers: list[str]) -> list[CodeRow]:
        self.list_by_numbers_calls.append(list(numbers))
        return [self._rows_by_number[n] for n in numbers if n in self._rows_by_number]

    async def hybrid_search(self, text: str, vector: list[float], k: int) -> list:
        raise NotImplementedError("not exercised by BillingCodesTask")


def _task(
    codes: list[Code], unresolved_axes: tuple[str, ...] = (), code_repository: ICodeRepository | None = None
) -> BillingCodesTask:
    return BillingCodesTask(_FakeRetriever(codes, unresolved_axes), code_repository or _FakeCodeRepository())


def _input(context: BillingContext | None = None) -> BillingCodesInput:
    return BillingCodesInput(summary=SUMMARY, transcript=TRANSCRIPT, context=context or BillingContext())


# -- build_prompt -------------------------------------------------------------------------


async def test_build_prompt_returns_the_fixed_system_prompt():
    task = _task([])

    prepared = await task.build_prompt(_input())

    assert prepared.system_prompt == SYSTEM_PROMPT


async def test_build_prompt_includes_the_raw_transcript_verbatim():
    task = _task([])

    prepared = await task.build_prompt(_input())

    assert TRANSCRIPT in prepared.user_message


async def test_build_prompt_redacts_a_nam_embedded_in_the_transcript():
    task = _task([])
    task_input = BillingCodesInput(
        summary=SUMMARY, transcript="Patient DESR81021001 se présente pour suivi.", context=BillingContext()
    )

    prepared = await task.build_prompt(task_input)

    assert "DESR81021001" not in prepared.user_message
    assert "[NAM]" in prepared.user_message


async def test_build_prompt_formats_full_candidate_block():
    code = Code(
        number="15801",
        libelle="ignored",
        description="Visite de prise en charge d'une maladie chronique",
        header_path="B > Visites sur rendez-vous > Visite de prise en charge",
        when_to_use=("Nouveau patient",),
        rules=("Clientele < 500 patients inscrits",),
        fees=(CodeFee(amount=33.15, amount_text="33,15", context="Par visite", lieu=None, majoration="20%"),),
    )
    task = _task([code])

    prepared = await task.build_prompt(_input())

    assert "- 15801 | B > Visites sur rendez-vous > Visite de prise en charge" in prepared.user_message
    assert "Visite de prise en charge d'une maladie chronique" in prepared.user_message
    assert "Utilisation : Nouveau patient" in prepared.user_message
    assert "Conditions : Clientele < 500 patients inscrits" in prepared.user_message


async def test_build_prompt_never_shows_fee_data_even_when_the_candidate_has_it():
    # The model doesn't pick a fee any more (see ExtractedCode.fees' server_only marker) —
    # fee data must never reach the prompt at all, even for a candidate that carries it.
    code = Code(
        number="15801",
        libelle="",
        description="Visite de prise en charge",
        header_path="x",
        fees=(CodeFee(amount=33.15, amount_text="33,15", context="Par visite", lieu=None, majoration="20%"),),
    )
    task = _task([code])

    prepared = await task.build_prompt(_input())

    assert "Tarifs" not in prepared.user_message
    assert "33.15" not in prepared.user_message


async def test_build_prompt_omits_when_to_use_entries_already_in_the_description():
    code = Code(
        number="15801",
        libelle="",
        description="Visite de prise en charge d'une maladie chronique",
        header_path="x",
        when_to_use=("Visite de prise en charge d'une maladie chronique",),
    )
    task = _task([code])

    prepared = await task.build_prompt(_input())

    assert "Utilisation :" not in prepared.user_message


async def test_build_prompt_omits_optional_sections_when_absent():
    code = Code(number="15801", libelle="", description="Visite de prise en charge", header_path="x")
    task = _task([code])

    prepared = await task.build_prompt(_input())

    assert "- 15801 | x" in prepared.user_message
    assert "Utilisation :" not in prepared.user_message
    assert "Conditions :" not in prepared.user_message


async def test_build_prompt_with_no_candidates_lists_none():
    task = _task([])

    prepared = await task.build_prompt(_input())

    assert "Candidate RAMQ codes:\n" in prepared.user_message


async def test_build_prompt_candidate_numbers_matches_the_retrieved_candidates():
    code_a = Code(number="A", libelle="", description="", header_path="x")
    code_b = Code(number="B", libelle="", description="", header_path="x")
    task = _task([code_a, code_b])

    prepared = await task.build_prompt(_input())

    assert prepared.candidate_numbers == frozenset({"A", "B"})


async def test_build_prompt_states_known_facts_as_established():
    context = BillingContext(
        physician=PhysicianContext(number_of_patients=320),
        patient=PatientContext(age_years=58, is_registered=True, is_vulnerable=False),
    )
    task = _task([])

    prepared = await task.build_prompt(_input(context))

    assert "320 patients (moins de 500)" in prepared.user_message
    assert "est inscrit auprès de ce médecin" in prepared.user_message
    assert "n'est pas désigné vulnérable" in prepared.user_message
    assert "58 ans" in prepared.user_message


async def test_build_prompt_omits_known_facts_section_when_context_is_empty():
    task = _task([])

    prepared = await task.build_prompt(_input(BillingContext()))

    assert "Faits établis" not in prepared.user_message


async def test_build_prompt_names_unresolved_axes_from_the_retriever():
    task = _task([], unresolved_axes=("panel_size",))

    prepared = await task.build_prompt(_input())

    assert "clientèle inscrite" in prepared.user_message
    assert "needs_confirmation" in prepared.user_message


async def test_build_prompt_passes_the_summary_and_context_to_the_retriever():
    context = BillingContext(physician=PhysicianContext(number_of_patients=320))
    retriever = _FakeRetriever([])
    task = BillingCodesTask(retriever, _FakeCodeRepository())

    await task.build_prompt(BillingCodesInput(summary=SUMMARY, transcript=TRANSCRIPT, context=context))

    assert retriever.last_call == (SUMMARY, context)


# -- json_schema ----------------------------------------------------------------------------


def test_json_schema_describes_billing_codes_result():
    task = _task([])

    schema = task.json_schema()

    assert schema["type"] == "object"
    assert "codes" in schema["required"]


def test_json_schema_never_asks_the_model_for_a_fee():
    # The model never picks a fee (ExtractedCode.fees is resolved server-side after the LLM
    # call, see resolve_fees below) — its server_only marker must keep it out of the schema
    # entirely, at every nesting depth, not just make it optional.
    task = _task([])

    schema = task.json_schema()
    code_schema = schema["properties"]["codes"]["items"]

    assert "fees" not in code_schema["properties"]
    assert "fees" not in code_schema["required"]


# -- parse ------------------------------------------------------------------------------


def _extracted_code(code: str = "15801") -> dict:
    return {
        "code": code,
        "description": "Visite de prise en charge",
        "confidence": "high",
        "explanation": "quote",
        "supporting_quote": "suivi diabète",
        "needs_confirmation": [],
    }


def _prepared(candidate_numbers: frozenset[str]) -> PreparedPrompt:
    return PreparedPrompt(system_prompt="", user_message="", candidate_numbers=candidate_numbers)


def test_parse_returns_well_formed_result_unchanged():
    task = _task([])

    result = task.parse({"codes": [_extracted_code()], "notes": "une note"}, _prepared(frozenset({"15801"})))

    assert isinstance(result, BillingCodesResult)
    assert [c.code for c in result.codes] == ["15801"]
    assert result.notes == "une note"


def test_parse_drops_bare_string_codes_and_flags_it_in_notes():
    task = _task([])

    result = task.parse(
        {"codes": ["BARE-CODE", _extracted_code()], "notes": None}, _prepared(frozenset({"15801"}))
    )

    assert [c.code for c in result.codes] == ["15801"]
    assert "1 candidate code" in result.notes


def test_parse_appends_dropped_note_to_existing_notes_rather_than_overwriting():
    task = _task([])

    result = task.parse({"codes": ["BARE-CODE"], "notes": "ambiguïté existante"}, _prepared(frozenset()))

    assert result.notes.startswith("ambiguïté existante")
    assert "1 candidate code" in result.notes


def test_parse_leaves_notes_untouched_when_nothing_was_dropped():
    task = _task([])

    result = task.parse({"codes": [_extracted_code()], "notes": "une note"}, _prepared(frozenset({"15801"})))

    assert result.notes == "une note"


def test_parse_empty_codes_list_is_valid():
    task = _task([])

    result = task.parse({"codes": [], "notes": None}, _prepared(frozenset()))

    assert result.codes == []
    assert result.notes is None


def test_parse_drops_a_code_the_model_invented_outside_the_candidate_set():
    task = _task([])

    result = task.parse(
        {"codes": [_extracted_code("15801"), _extracted_code("99999")], "notes": None},
        _prepared(frozenset({"15801"})),
    )

    assert [c.code for c in result.codes] == ["15801"]
    assert "not in the offered candidate list" in result.notes


def test_parse_keeps_every_code_when_all_are_in_the_candidate_set():
    task = _task([])

    result = task.parse(
        {"codes": [_extracted_code("15801")], "notes": None}, _prepared(frozenset({"15801", "15802"}))
    )

    assert [c.code for c in result.codes] == ["15801"]
    assert result.notes is None


# -- resolve_fees -------------------------------------------------------------------------


def _row(number: str, *fees: CodeRowFee) -> CodeRow:
    return CodeRow(number=number, libelle="", description="", header_path="", fees=list(fees))


async def test_resolve_fees_attaches_every_fee_for_each_code_in_order():
    repository = _FakeCodeRepository(
        [
            _row(
                "15801",
                CodeRowFee(amount=33.15, context="Jour", lieu="Cabinet"),
                CodeRowFee(amount=40.0, context="Soir", lieu="Domicile", majoration="20%"),
            )
        ]
    )
    task = _task([], code_repository=repository)
    result = task.parse({"codes": [_extracted_code("15801")], "notes": None}, _prepared(frozenset({"15801"})))

    await task.resolve_fees(result)

    [code] = result.codes
    assert [f.amount for f in code.fees] == [33.15, 40.0]
    assert code.fees[1].lieu == "Domicile"
    assert code.fees[1].majoration == "20%"


async def test_resolve_fees_leaves_a_code_with_no_matching_row_with_an_empty_list():
    task = _task([], code_repository=_FakeCodeRepository([]))
    result = task.parse({"codes": [_extracted_code("15801")], "notes": None}, _prepared(frozenset({"15801"})))

    await task.resolve_fees(result)

    assert result.codes[0].fees == []


async def test_resolve_fees_does_not_query_the_repository_for_an_empty_codes_list():
    repository = _FakeCodeRepository([])
    task = _task([], code_repository=repository)
    result = task.parse({"codes": [], "notes": None}, _prepared(frozenset()))

    await task.resolve_fees(result)

    assert repository.list_by_numbers_calls == []
