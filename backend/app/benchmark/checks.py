"""Deterministic checks of a consultation summary against what the note states for certain.
There is no gold summary to grade against, so these only cover facts the note header makes
unambiguous (date, start time), plus structural stats that make two models' summaries
comparable at a glance. The summary's real job — feeding retrieval — is measured by the
retrieval stage's recall, not here."""

import re

from app.benchmark.dataset import BenchmarkCase
from app.benchmark.records import SummaryCheck
from app.extraction.encounter_date import parse_encounter_date
from app.sample_patients import parse_header_fields
from app.summary import ConsultationSummaryResult

_HEADER_TIME_RE = re.compile(r"\b(\d{1,2})\s*h\s*(\d{2})\b")
_SUMMARY_TIME_RE = re.compile(r"^\s*(\d{1,2})\s*[:h]\s*(\d{2})")


def _hhmm(match: re.Match | None) -> str | None:
    return f"{int(match.group(1)):02d}:{match.group(2)}" if match else None


class SummaryChecks:
    def check(self, case: BenchmarkCase, summary: ConsultationSummaryResult) -> list[SummaryCheck]:
        header = parse_header_fields(case.transcript).get("Date/heure", "")
        return [self._date(header, summary), self._time_start(header, summary)]

    def stats(self, summary: ConsultationSummaryResult) -> dict[str, int | bool]:
        return {
            "procedures": len(summary.procedures_performed),
            "add_ons": len(summary.possible_billable_add_ons),
            "uncertain_items": len(summary.notes_uncertain_items),
            "systems": len(summary.clinical_summary.systems_or_body_regions_involved),
            "pregnancy": summary.pregnancy_context.present,
            "referral": summary.referral_information.present,
            "duration_stated": summary.encounter_setting.duration_explicitly_stated,
        }

    @staticmethod
    def _date(header: str, summary: ConsultationSummaryResult) -> SummaryCheck:
        expected = parse_encounter_date(header)
        actual = parse_encounter_date(summary.encounter_setting.date)
        return SummaryCheck(
            name="date",
            passed=None if expected is None else actual == expected,
            expected=expected.isoformat() if expected else None,
            actual=summary.encounter_setting.date,
        )

    @staticmethod
    def _time_start(header: str, summary: ConsultationSummaryResult) -> SummaryCheck:
        expected = _hhmm(_HEADER_TIME_RE.search(header))
        actual_raw = summary.encounter_setting.time_start
        actual = _hhmm(_SUMMARY_TIME_RE.match(actual_raw)) if actual_raw else None
        return SummaryCheck(
            name="time_start",
            passed=None if expected is None else actual == expected,
            expected=expected,
            actual=actual_raw,
        )
