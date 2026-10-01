"""Loads synthetic sample patients for the frontend's patient picker.

This is test/demo fixture data only, not representative of real Quebec RAMQ encounters.
It exists so the extraction pipeline can be exercised end-to-end without any real (or even
realistic) patient data.

SAMPLE_PATIENTS_DIR defaults to consultations/ at the repo root — one freeform,
French-language clinical note per file (`README.md` and `all_notes.md` in that directory
are skipped). Override with the SAMPLE_PATIENTS_DIR env var to point at a different
directory of files in the same format — needed under Docker, where the backend image's
build context is backend/ only, so consultations/ (a repo-root directory) isn't in the
image and has to be bind-mounted instead (see docker-compose.yml).
"""

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.patients import nam as nam_module

SAMPLE_PATIENTS_DIR = (
    Path(os.environ["SAMPLE_PATIENTS_DIR"])
    if os.environ.get("SAMPLE_PATIENTS_DIR")
    else Path(__file__).parent.parent.parent.parent / "consultations"
)

_SKIP_STEMS = {"README", "all_notes"}

@dataclass(frozen=True)
class SamplePatient:
    id: str
    label: str
    transcript: str
    # Normalized NAM from the note's `**NAM :**` header, or None if missing/malformed —
    # lets the frontend auto-match this sample to the real Patient row seed_db.py creates
    # for it (same normalization, see scripts/seed_db.py).
    nam: str | None


_FIELD_RE = re.compile(r"^\*\*(.+?)\s*:\*\*\s*(.*)$", re.MULTILINE)
_AGE_SEX_YEARS_RE = re.compile(r"(\d+)\s*ans\s*\((\w)\)")
_AGE_SEX_MONTHS_RE = re.compile(r"(\d+)\s*mois\s*\((\w)\)")
_MOTIF_RE = re.compile(r"### Motif de consultation\s*\n(.+?)(?=\n#{2,3}|\Z)", re.DOTALL)


def parse_header_fields(note: str) -> dict[str, str]:
    """Every `**Label :** value` header line in a consultation note, as a dict — shared by
    the sample-patient loader below and scripts/seed_db.py, which needs the same fields
    (Patient/NAM/Médecin) to seed a Patient row per note."""
    return dict(_FIELD_RE.findall(note))


def parse_age_hint_years(patient_field: str) -> float | None:
    """The age hint embedded in a `**Patient :**` line, e.g. "45 ans (H)" or, for an
    infant, "18 mois (F)" — as whole or fractional years, for app.patients.nam.decode's
    age_hint (it needs this to disambiguate a NAM's century when both the 19xx and 20xx
    candidate birth years pass its own sanity checks, which happens for any very recent
    NAM)."""
    years_match = _AGE_SEX_YEARS_RE.search(patient_field)
    if years_match:
        return float(years_match.group(1))
    months_match = _AGE_SEX_MONTHS_RE.search(patient_field)
    if months_match:
        return float(months_match.group(1)) / 12
    return None


def _build_label(note: str, fields: dict[str, str]) -> str:
    age_sex = _AGE_SEX_YEARS_RE.search(fields.get("Patient", ""))
    demographic = f"{age_sex.group(1)}{age_sex.group(2)}" if age_sex else ""

    motif_match = _MOTIF_RE.search(note)
    motif = motif_match.group(1).strip() if motif_match else "no chief complaint recorded"

    return f"{demographic} — {motif}" if demographic else motif


def _load_note(path: Path, index: int) -> SamplePatient:
    note = path.read_text().strip()
    fields = parse_header_fields(note)
    dossier = fields.get("Dossier", "").strip().lstrip("#").strip()

    return SamplePatient(
        id=dossier or f"note-{index}",
        label=_build_label(note, fields),
        transcript=note,
        nam=nam_module.normalize(fields.get("NAM")),
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
