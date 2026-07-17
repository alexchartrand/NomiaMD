"""Loads synthetic sample patients for the frontend's patient picker.

This is test/demo fixture data only, not representative of real Quebec RAMQ encounters.
It exists so the extraction pipeline can be exercised end-to-end without any real (or even
realistic) patient data.

SAMPLE_PATIENTS_PATH defaults to notes_consultation_simulees.md at the repo root —
freeform, French-language clinical notes, one per "## NOTE <n> — ..." section. Override it
to point at a different file in the same format.
"""

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent.parent.parent / "notes_consultation_simulees.md"
SAMPLE_PATIENTS_PATH = Path(os.environ.get("SAMPLE_PATIENTS_PATH") or DEFAULT_PATH)


@dataclass(frozen=True)
class SamplePatient:
    id: str
    label: str
    transcript: str


_NOTE_HEADER_RE = re.compile(r"^## NOTE \d+.*$", re.MULTILINE)
_FIELD_RE = re.compile(r"^\*\*(.+?)\s*:\*\*\s*(.*)$", re.MULTILINE)
_AGE_SEX_RE = re.compile(r"(\d+)\s*ans\s*\((\w)\)")
_MOTIF_RE = re.compile(r"### Motif de consultation\s*\n(.+?)(?=\n#{2,3}|\Z)", re.DOTALL)


def _build_label_markdown(section: str, fields: dict[str, str]) -> str:
    age_sex = _AGE_SEX_RE.search(fields.get("Patient", ""))
    demographic = f"{age_sex.group(1)}{age_sex.group(2)}" if age_sex else ""

    motif_match = _MOTIF_RE.search(section)
    motif = motif_match.group(1).strip() if motif_match else "no chief complaint recorded"

    return f"{demographic} — {motif}" if demographic else motif


def _load_markdown() -> list[SamplePatient]:
    text = SAMPLE_PATIENTS_PATH.read_text()
    headers = list(_NOTE_HEADER_RE.finditer(text))

    patients: list[SamplePatient] = []
    for i, header in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        # Each section is terminated by a "---" separator (or end of file for the last one).
        section = text[header.start():end].split("\n---", 1)[0].strip()

        fields = dict(_FIELD_RE.findall(section))
        dossier = fields.get("Dossier", "").strip().lstrip("#").strip()

        patients.append(
            SamplePatient(
                id=dossier or f"note-{i}",
                label=_build_label_markdown(section, fields),
                transcript=section,
            )
        )
    return patients


def _load_all() -> list[SamplePatient]:
    if not SAMPLE_PATIENTS_PATH.exists():
        return []
    return _load_markdown()


@lru_cache(maxsize=1)
def get_sample_patients() -> list[SamplePatient]:
    return _load_all()


def get_sample_patient(patient_id: str) -> SamplePatient | None:
    return next((p for p in get_sample_patients() if p.id == patient_id), None)
