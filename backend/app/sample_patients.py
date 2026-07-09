"""Loads synthetic test patients from train.jsonl for the frontend's patient picker.

This is test/demo fixture data only — synthetic South African English consultations from
a third-party generator (see synthetic_data/ at the repo root), not representative of real
Quebec RAMQ encounters. It exists so the extraction pipeline can be exercised end-to-end
without any real (or even realistic) patient data.
"""

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent.parent.parent / "train.jsonl"
SAMPLE_PATIENTS_PATH = Path(os.environ.get("SAMPLE_PATIENTS_PATH") or DEFAULT_PATH)


@dataclass(frozen=True)
class SamplePatient:
    id: str
    label: str
    transcript: str


def _build_label(record: dict) -> str:
    scenario = record.get("scenario", {})
    persona = scenario.get("patient_persona", {})
    clinical = scenario.get("clinical_context", {})

    age = persona.get("age")
    sex = (persona.get("sex") or "")[:1].upper()
    demographic = f"{age}{sex}" if age is not None else sex

    complaint = clinical.get("chief_complaint") or "no chief complaint recorded"
    return f"{demographic} — {complaint}" if demographic else complaint


def _build_transcript(record: dict) -> str:
    turns = record.get("conversation", [])
    return "\n".join(
        f"{turn.get('speaker', '?')}: {turn.get('utterance', '')}" for turn in turns
    )


def _load_all() -> list[SamplePatient]:
    if not SAMPLE_PATIENTS_PATH.exists():
        return []

    patients: list[SamplePatient] = []
    with SAMPLE_PATIENTS_PATH.open() as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            patients.append(
                SamplePatient(
                    id=record.get("conversation_id") or f"patient-{i}",
                    label=_build_label(record),
                    transcript=_build_transcript(record),
                )
            )
    return patients


@lru_cache(maxsize=1)
def get_sample_patients() -> list[SamplePatient]:
    return _load_all()


def get_sample_patient(patient_id: str) -> SamplePatient | None:
    return next((p for p in get_sample_patients() if p.id == patient_id), None)
