"""Loads synthetic sample patients for the frontend's patient picker.

This is test/demo fixture data only, not representative of real Quebec RAMQ encounters.
It exists so the extraction pipeline can be exercised end-to-end without any real (or even
realistic) patient data.

SAMPLE_PATIENTS_PATH's file extension picks the parser:
- `.md` (default: notes_consultation_simulees.md at the repo root) — freeform clinical
  notes, one per "## NOTE <n> — ..." section.
- `.jsonl` (e.g. train.jsonl at the repo root) — synthetic South African English
  consultations from a third-party generator (see synthetic_data/), one JSON record per
  line with a "conversation" turn list.
"""

import json
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


def _build_label_jsonl(record: dict) -> str:
    scenario = record.get("scenario", {})
    persona = scenario.get("patient_persona", {})
    clinical = scenario.get("clinical_context", {})

    age = persona.get("age")
    sex = (persona.get("sex") or "")[:1].upper()
    demographic = f"{age}{sex}" if age is not None else sex

    complaint = clinical.get("chief_complaint") or "no chief complaint recorded"
    return f"{demographic} — {complaint}" if demographic else complaint


def _build_transcript_jsonl(record: dict) -> str:
    turns = record.get("conversation", [])
    return "\n".join(
        f"{turn.get('speaker', '?')}: {turn.get('utterance', '')}" for turn in turns
    )


def _load_jsonl() -> list[SamplePatient]:
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
                    label=_build_label_jsonl(record),
                    transcript=_build_transcript_jsonl(record),
                )
            )
    return patients


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
    if SAMPLE_PATIENTS_PATH.suffix == ".jsonl":
        return _load_jsonl()
    return _load_markdown()


@lru_cache(maxsize=1)
def get_sample_patients() -> list[SamplePatient]:
    return _load_all()


def get_sample_patient(patient_id: str) -> SamplePatient | None:
    return next((p for p in get_sample_patients() if p.id == patient_id), None)
