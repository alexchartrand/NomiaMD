"""The Epic sandbox patients the demo imports, each with the fake NAM it's seeded under and
the notes it imports. `sandbox_patients.json` is written by scripts/epic_sandbox_inventory.py
from the live sandbox and read by the connector and by scripts/seed_db.py, which creates the
matching NomiaMD patients.

The notes are listed by id because the sandbox is shared and writable: other developers'
apps post test notes ("CONTRACT TEST", size probes, bot events) into the same patients
every day. Only the listed notes are imported, so the demo shows the same notes every time."""

import json
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.postgresdb import Gender

DEFAULT_ROSTER_PATH = Path(__file__).with_name("sandbox_patients.json")

# A NAM's last two digits are a sequence number; 99 marks the demo ones.
_DEMO_SEQUENCE = "99"


@dataclass(frozen=True)
class SandboxPatient:
    fhir_id: str
    family_name: str
    given_name: str
    birth_date: date
    gender: Gender
    nam: str
    # The DocumentReference ids the demo imports for this patient.
    note_ids: frozenset[str] = frozenset()

    @property
    def full_name(self) -> str:
        return f"{self.given_name} {self.family_name}"


class SandboxRoster:
    def __init__(self, patients: list[SandboxPatient]) -> None:
        self._by_fhir_id = {patient.fhir_id: patient for patient in patients}

    @classmethod
    def load(cls, path: Path = DEFAULT_ROSTER_PATH) -> "SandboxRoster":
        entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        return cls([_parse(entry) for entry in entries])

    def __len__(self) -> int:
        return len(self._by_fhir_id)

    def patients(self) -> list[SandboxPatient]:
        return list(self._by_fhir_id.values())

    def by_fhir_id(self, fhir_id: str) -> SandboxPatient | None:
        return self._by_fhir_id.get(fhir_id)


def demo_nam(family_name: str, given_name: str, birth_date: date, gender: Gender) -> str:
    """A well-formed NAM for a sandbox patient, built the way RAMQ builds one (3 letters of
    the surname, 1 of the given name, YYMMDD with +50 on the month for women), so the
    patient's age and sex decode from it like a real one's."""
    surname = (_letters(family_name) + "XXX")[:3]
    initial = (_letters(given_name) + "X")[:1]
    month = birth_date.month + (50 if gender == Gender.FEMALE else 0)
    return f"{surname}{initial}{birth_date:%y}{month:02d}{birth_date:%d}{_DEMO_SEQUENCE}"


def to_json(patient: SandboxPatient) -> dict:
    return {
        "fhir_id": patient.fhir_id,
        "family_name": patient.family_name,
        "given_name": patient.given_name,
        "birth_date": patient.birth_date.isoformat(),
        "gender": patient.gender.value,
        "nam": patient.nam,
        "note_ids": sorted(patient.note_ids),
    }


def _parse(entry: dict) -> SandboxPatient:
    return SandboxPatient(
        fhir_id=entry["fhir_id"],
        family_name=entry["family_name"],
        given_name=entry["given_name"],
        birth_date=date.fromisoformat(entry["birth_date"]),
        gender=Gender(entry["gender"]),
        nam=entry["nam"],
        note_ids=frozenset(entry.get("note_ids", [])),
    )


def _letters(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "".join(char for char in ascii_name.upper() if char.isalpha())
