"""Inventory the Epic sandbox (fhir.epic.com) for the step 11b demo: which test patients have
signed clinical notes worth importing. From backend/, with EPIC_SANDBOX_CLIENT_ID and
EPIC_SANDBOX_PRIVATE_KEY_PATH set (see .env.example):

    uv run python scripts/epic_sandbox_inventory.py                 # print the table
    uv run python scripts/epic_sandbox_inventory.py --write         # + rewrite the roster
    uv run python scripts/epic_sandbox_inventory.py --record ID     # + save ID's resources

The sandbox is shared and writable: besides Epic's own seeded notes, other developers' apps
post test notes into the same patients through the API (authored by "User Interconnect" or
"User Epic"). DemoNoteSelector keeps only Epic's seeded notes by a family-medicine or
emergency physician with some substance, longest first.

--write rewrites app/intake/connectors/epic_fhir/sandbox_patients.json with every patient
that has a selected note: a fake NAM built from its sandbox name, birth date and sex, and the
selected note ids (edit the file by hand to prune). Re-run scripts/seed_db.py afterwards so
those patients exist. --record saves one patient's raw resources under
tests/fixtures/epic/recorded/ (synthetic data, safe to commit). Extra positional arguments
are more patient FHIR ids to check."""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import httpx  # noqa: E402

from app.config import settings  # noqa: E402
from app.intake import default_normalizers  # noqa: E402
from app.intake.connectors.epic_fhir import (  # noqa: E402
    EPIC_SANDBOX_SOURCE_SYSTEM,
    EpicFhirClient,
    EpicFhirError,
    EpicNoteMapper,
    Resource,
)
from app.intake.connectors.epic_fhir.factory import sandbox_client  # noqa: E402
from app.intake.connectors.epic_fhir.mapper import NOTE_CONTENT_TYPE  # noqa: E402
from app.intake.connectors.epic_fhir.sandbox_roster import (  # noqa: E402
    DEFAULT_ROSTER_PATH,
    SandboxPatient,
    demo_nam,
    to_json,
)
from app.postgresdb import Gender  # noqa: E402

# Epic's documented R4 sandbox test patients (fhir.epic.com → Documentation → Test Data).
# Unknown or retired ids just show as unreadable in the table.
KNOWN_SANDBOX_PATIENTS = [
    "erXuFYUfucBZaryVksYEcMg3",  # Camila Lopez
    "eq081-VQEgP8drUUqCWzHfw3",  # Derrick Lin
    "egqBHVfQlt4Bw3XGXoxVxHg3",  # Elijah Davis
    "eIXesllypH3M9tAA5WdJftQ3",  # Linda Ross
    "eh2xYHuzl9nkSFVvV3osUHg3",  # Olivia Roberts
    "e0w0LEDCYtfckT6N.CkJKCw3",  # Warren McGinnis
    "e63wRTbPfr1p8UW81d8Seiw3",  # Theodore Mychart
    "eAB3mDIBBcyUKviyzrxsnAw3",  # Desiree Powell
]

RECORD_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "epic" / "recorded"

_GENDERS = {"male": Gender.MALE, "female": Gender.FEMALE}


@dataclass(frozen=True)
class Candidate:
    document: Resource
    text: str


class DemoNoteSelector:
    """Which signed notes the demo imports. NomiaMD serves omnipraticiens, in clinic and in
    the ER, so: Epic's seeded notes by a family-medicine or emergency physician, long enough
    to bill from, at most `per_patient` of them, longest first."""

    _SPECIALTIES = ("Family Medicine", "Emergency")

    def __init__(self, min_chars: int, per_patient: int) -> None:
        self._min_chars = min_chars
        self._per_patient = per_patient

    def is_candidate(self, document: Resource) -> bool:
        """Checked before any body is fetched: signed, HTML, and by a seeded physician."""
        if not (EpicNoteMapper.is_signed(document) and EpicNoteMapper.note_attachment(document)):
            return False
        author = _author_display(document)
        return "Physician" in author and any(specialty in author for specialty in self._SPECIALTIES)

    def select(self, candidates: list[Candidate]) -> list[Candidate]:
        substantial = [candidate for candidate in candidates if len(candidate.text) >= self._min_chars]
        return sorted(substantial, key=lambda candidate: len(candidate.text), reverse=True)[: self._per_patient]


def _author_display(document: Resource) -> str:
    authors = document.get("author", [])
    return (authors[0].get("display") or "") if authors else ""


def _names(patient: Resource) -> tuple[str, str]:
    names = patient.get("name", [])
    official = next((name for name in names if name.get("use") == "official"), names[0] if names else {})
    given = official.get("given", [""])
    return official.get("family", ""), given[0] if given else ""


def _sandbox_patient(fhir_id: str, patient: Resource, note_ids: list[str]) -> SandboxPatient:
    family, given = _names(patient)
    birth_date = date.fromisoformat(patient["birthDate"])
    gender = _GENDERS.get(patient.get("gender", ""), Gender.OTHER)
    nam = demo_nam(family, given, birth_date, gender)
    return SandboxPatient(fhir_id, family, given, birth_date, gender, nam, frozenset(note_ids))


class Inventory:
    def __init__(self, client: EpicFhirClient, selector: DemoNoteSelector) -> None:
        self._client = client
        self._selector = selector
        self._normalizer = default_normalizers().for_source(EPIC_SANDBOX_SOURCE_SYSTEM)

    async def patient(self, fhir_id: str, record: bool) -> SandboxPatient | None:
        try:
            patient = await self._client.read("Patient", fhir_id)
        except EpicFhirError as error:
            print(f"{fhir_id:<28} unreadable ({error.status_code})")
            return None
        documents = await self._client.search("DocumentReference", {"patient": fhir_id, "category": "clinical-note"})
        signed = [doc for doc in documents if EpicNoteMapper.is_signed(doc)]
        candidates = [await self._candidate(doc) for doc in documents if self._selector.is_candidate(doc)]
        selected = self._selector.select(candidates)

        family, given = _names(patient)
        print(
            f"{fhir_id:<28} {given} {family:<16} born {patient.get('birthDate')} "
            f"notes={len(documents)} signed={len(signed)} physician={len(candidates)} selected={len(selected)}"
        )
        for candidate in selected:
            doc = candidate.document
            print(
                f"    {doc['id']:<28} {(doc.get('date') or '')[:10]} {doc.get('type', {}).get('text', ''):<20} "
                f"{len(candidate.text):>5} chars  {_author_display(doc)}"
            )
        if record:
            await self._record(fhir_id, patient, documents, selected)
        if not selected:
            return None
        return _sandbox_patient(fhir_id, patient, [candidate.document["id"] for candidate in selected])

    async def _candidate(self, document: Resource) -> Candidate:
        attachment = EpicNoteMapper.note_attachment(document)
        assert attachment is not None
        html = await self._client.binary_text(attachment["url"], NOTE_CONTENT_TYPE)
        return Candidate(document, self._normalizer.normalize(html))

    async def _record(
        self, fhir_id: str, patient: Resource, documents: list[Resource], selected: list[Candidate]
    ) -> None:
        folder = RECORD_DIR / fhir_id
        folder.mkdir(parents=True, exist_ok=True)
        _dump(folder / "Patient.json", patient)
        # The selected notes and a couple of drafts — not the other apps' junk, which is most
        # of the search and changes daily.
        drafts = [doc for doc in documents if doc.get("docStatus") == "preliminary"][:2]
        _dump(folder / "DocumentReference.json", [candidate.document for candidate in selected] + drafts)
        for candidate in selected[:3]:
            doc = candidate.document
            attachment = EpicNoteMapper.note_attachment(doc)
            assert attachment is not None
            (folder / f"Binary-{doc['id']}.html").write_text(
                await self._client.binary_text(attachment["url"], NOTE_CONTENT_TYPE), encoding="utf-8"
            )
            reference = EpicNoteMapper.encounter_reference(doc)
            if reference:
                try:
                    _dump(folder / f"{reference.replace('/', '-')}.json", await self._client.read_reference(reference))
                except EpicFhirError as error:
                    print(f"  ({reference} unreadable: {error.status_code})")
        print(f"  recorded under {folder}")


def _dump(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("patient_ids", nargs="*", help="more sandbox patient FHIR ids to check")
    parser.add_argument("--write", action="store_true", help="rewrite the roster with the selected notes")
    parser.add_argument("--record", metavar="ID", action="append", default=[], help="save this patient's resources")
    parser.add_argument("--min-chars", type=int, default=250, help="shortest note kept, once normalized")
    parser.add_argument("--per-patient", type=int, default=6, help="most notes kept per patient")
    args = parser.parse_args()
    if not (os.environ.get("EPIC_SANDBOX_CLIENT_ID") and os.environ.get("EPIC_SANDBOX_PRIVATE_KEY_PATH")):
        raise SystemExit("Set EPIC_SANDBOX_CLIENT_ID and EPIC_SANDBOX_PRIVATE_KEY_PATH (backend/.env) first.")

    ids = list(dict.fromkeys(KNOWN_SANDBOX_PATIENTS + args.patient_ids + args.record))
    async with httpx.AsyncClient(timeout=60) as http:
        client = sandbox_client(http, settings)
        try:
            await client.token()
        except EpicFhirError as error:
            raise SystemExit(
                f"Epic refused the token request: {error}\n"
                "invalid_client usually means the app (or its JWK Set URL) isn't synced to the "
                "sandbox yet, the client id isn't the non-production one, or the key's public half "
                "isn't in the JWK Set the app's URL serves (app/jwks/public_keys/)."
            ) from error
        inventory = Inventory(client, DemoNoteSelector(args.min_chars, args.per_patient))
        roster = [patient for fhir_id in ids if (patient := await inventory.patient(fhir_id, fhir_id in args.record))]

    print(f"\n{len(roster)} patient(s), {sum(len(p.note_ids) for p in roster)} note(s) selected.")
    if args.write:
        _dump(DEFAULT_ROSTER_PATH, [to_json(patient) for patient in roster])
        print(f"Wrote {DEFAULT_ROSTER_PATH} — re-run scripts/seed_db.py to create these patients.")


if __name__ == "__main__":
    asyncio.run(main())
