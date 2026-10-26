"""app/benchmark/checks.py: the summary's date and start time against a real note header."""

from app.benchmark.checks import SummaryChecks
from app.sample_patients import get_sample_patient
from app.summary import ConsultationSummaryResult
from tests.benchmark_helpers import case
from tests.test_consultation_summary import MOCK_RESULT


def _summary(**setting) -> ConsultationSummaryResult:
    return ConsultationSummaryResult.model_validate(
        {**MOCK_RESULT, "encounter_setting": {**MOCK_RESULT["encounter_setting"], **setting}}
    )


def _note_case(patient_id: str = "CLI-2026-01220"):
    # 01_hta_prise_en_charge.md: **Date/heure :** 10 février 2026, 09h15
    return case(patient_id, transcript=get_sample_patient(patient_id).transcript)


def _checks(summary):
    return {c.name: c for c in SummaryChecks().check(_note_case(), summary)}


def test_matching_date_and_time_pass():
    checks = _checks(_summary(date="2026-02-10", time_start="09:15"))

    assert checks["date"].passed and checks["time_start"].passed
    assert checks["date"].expected == "2026-02-10" and checks["time_start"].expected == "09:15"


def test_a_french_date_or_an_h_time_still_counts_as_the_same_value():
    checks = _checks(_summary(date="10 février 2026", time_start="9h15"))

    assert checks["date"].passed and checks["time_start"].passed


def test_wrong_or_missing_values_fail():
    checks = _checks(_summary(date="2026-02-11", time_start=None))

    assert checks["date"].passed is False
    assert checks["time_start"].passed is False


def test_a_note_without_a_header_makes_the_checks_not_applicable():
    checks = {c.name: c for c in SummaryChecks().check(case(transcript="Suivi sans en-tête."), _summary(date="2026-07-13"))}

    assert checks["date"].passed is None and checks["time_start"].passed is None


def test_stats_count_what_the_summary_called_out():
    stats = SummaryChecks().stats(_summary())

    assert stats["procedures"] == 0
    assert stats["systems"] == 2
    assert stats["pregnancy"] is False
