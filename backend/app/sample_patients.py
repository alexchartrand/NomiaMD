"""Loads synthetic sample patients for the frontend's patient picker.

This is test/demo fixture data only, not representative of real Quebec RAMQ encounters.
It exists so the extraction pipeline can be exercised end-to-end without any real (or even
realistic) patient data.

SAMPLE_PATIENTS_DIR defaults to consultations/ at the repo root — one freeform,
French-language clinical note per file (`README.md` and `all_notes.md` in that directory
are skipped). Override it to point at a different directory of files in the same format.
"""

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_DIR = Path(__file__).parent.parent.parent / "consultations"
SAMPLE_PATIENTS_DIR = Path(os.environ.get("SAMPLE_PATIENTS_DIR") or DEFAULT_DIR)

_SKIP_STEMS = {"README", "all_notes"}


@dataclass(frozen=True)
class SamplePatient:
    id: str
    label: str
    transcript: str


_FIELD_RE = re.compile(r"^\*\*(.+?)\s*:\*\*\s*(.*)$", re.MULTILINE)
_AGE_SEX_RE = re.compile(r"(\d+)\s*ans\s*\((\w)\)")
_MOTIF_RE = re.compile(r"### Motif de consultation\s*\n(.+?)(?=\n#{2,3}|\Z)", re.DOTALL)


def _build_label(note: str, fields: dict[str, str]) -> str:
    age_sex = _AGE_SEX_RE.search(fields.get("Patient", ""))
    demographic = f"{age_sex.group(1)}{age_sex.group(2)}" if age_sex else ""

    motif_match = _MOTIF_RE.search(note)
    motif = motif_match.group(1).strip() if motif_match else "no chief complaint recorded"

    return f"{demographic} — {motif}" if demographic else motif


def _load_note(path: Path, index: int) -> SamplePatient:
    note = path.read_text().strip()
    fields = dict(_FIELD_RE.findall(note))
    dossier = fields.get("Dossier", "").strip().lstrip("#").strip()

    return SamplePatient(
        id=dossier or f"note-{index}",
        label=_build_label(note, fields),
        transcript=note,
    )


def _load_all() -> list[SamplePatient]:
    if not SAMPLE_PATIENTS_DIR.is_dir():
        return []
    paths = sorted(p for p in SAMPLE_PATIENTS_DIR.glob("*.md") if p.stem not in _SKIP_STEMS)
    return [_load_note(p, i) for i, p in enumerate(paths)]


@lru_cache(maxsize=1)
def get_sample_patients() -> list[SamplePatient]:
    return _load_all()


def get_sample_patient(patient_id: str) -> SamplePatient | None:
    return next((p for p in get_sample_patients() if p.id == patient_id), None)
