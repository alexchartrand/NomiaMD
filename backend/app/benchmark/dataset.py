"""The labeled eval set as benchmark cases: each fixture entry (expected codes, billing
context, label status, difficulty) joined to its `consultations/` note.

The billing context comes straight from the fixture rather than BillingContextBuilder: the
benchmark is deterministic and needs no physician login or patient row. So does the care
setting (`encounter_context`), which in the app comes from the note's source or the
physician, never the note text."""

import hashlib
import json
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.care_setting import CareSetting
from app.ramq_codes import BillingContext, PatientContext, PhysicianContext
from app.sample_patients import SamplePatient, get_sample_patient

DEFAULT_EVAL_PATH = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "eval_billing_codes.jsonl"

Difficulty = Literal["original", "easy", "medium", "hard", "negative"]


@dataclass(frozen=True)
class BenchmarkCase:
    patient_id: str
    transcript: str
    context: BillingContext
    expected_codes: frozenset[str]
    label_status: str
    difficulty: Difficulty
    label_notes: str = ""

    @property
    def is_labeled_negative(self) -> bool:
        """The right answer is no code (a no-show, an insurer form...) — unless the entry
        simply isn't labeled yet."""
        return not self.expected_codes and self.label_status != "needs_physician_label"


class UnknownCaseError(LookupError):
    pass


class EvalSetLoader:
    def __init__(
        self,
        path: Path = DEFAULT_EVAL_PATH,
        notes: Callable[[str], SamplePatient | None] = get_sample_patient,
    ):
        self.path = path
        self._notes = notes

    def load(
        self,
        *,
        patient_ids: Collection[str] | None = None,
        label_statuses: Collection[str] | None = None,
        difficulties: Collection[str] | None = None,
    ) -> list[BenchmarkCase]:
        """Fixture order. Each filter, when given, keeps only the entries matching it."""
        entries = self._entries()
        if patient_ids:
            unknown = sorted(set(patient_ids) - {entry["patient_id"] for entry in entries})
            if unknown:
                raise UnknownCaseError(f"Not in {self.path.name}: {', '.join(unknown)}")

        cases = []
        for entry in entries:
            if patient_ids and entry["patient_id"] not in patient_ids:
                continue
            if label_statuses and entry.get("label_status") not in label_statuses:
                continue
            if difficulties and entry.get("difficulty") not in difficulties:
                continue
            cases.append(self._case(entry))
        return cases

    def sha256(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def _entries(self) -> list[dict]:
        with self.path.open() as f:
            return [json.loads(line) for line in f if line.strip()]

    def _case(self, entry: dict) -> BenchmarkCase:
        note = self._notes(entry["patient_id"])
        if note is None:
            raise UnknownCaseError(f"No consultations/ note for {entry['patient_id']!r}")
        return BenchmarkCase(
            patient_id=entry["patient_id"],
            transcript=note.transcript,
            context=self._context(entry),
            expected_codes=frozenset(entry.get("expected_codes") or []),
            label_status=entry.get("label_status", "unknown"),
            difficulty=entry["difficulty"],
            label_notes=entry.get("label_notes", ""),
        )

    @staticmethod
    def _context(entry: dict) -> BillingContext:
        physician = entry.get("physician_context") or {}
        patient = entry.get("patient_context") or {}
        # A misspelled setting fails loudly (ValueError) rather than silently searching
        # without it.
        care_setting = (entry.get("encounter_context") or {}).get("care_setting")
        return BillingContext(
            physician=PhysicianContext(
                panel_size=physician.get("panel_size"),
                physician_type=physician.get("physician_type"),
                remuneration_type=physician.get("remuneration_type"),
            ),
            patient=PatientContext(
                age_years=patient.get("age_years"),
                is_registered=patient.get("is_registered"),
                is_vulnerable=patient.get("is_vulnerable"),
            ),
            care_setting=CareSetting(care_setting) if care_setting is not None else None,
        )
