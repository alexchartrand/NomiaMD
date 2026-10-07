"""Seed a freshly wiped database with a demo admin user and every simulated consultation-
note patients, each with an encounter holding its note, for local development — plus the
Epic sandbox demo's patients (no encounters: those come from its import). The
encounters go through IntakeService (the sample connector), the same path a real note
takes. From backend/, with the venv active:

    python scripts/seed_db.py

Prompts for the new user's password interactively (same reasoning as create_user.py: never
accepted as a CLI argument, to avoid it ending up in shell history/`ps` output). The E2E suite
(frontend/e2e/) has no terminal to prompt on, so it passes a throwaway one in SEED_ADMIN_PASSWORD. Fails
loudly (rather than upserting) if the admin email already exists — that means the DB wasn't
actually wiped, so re-run against a clean DB instead of layering seed data on top of itself.
"""

import asyncio
import os
import re
import sys
from datetime import date
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Loads the repo-root .env — must run before the app imports below read their settings.
import app.config  # noqa: E402,F401

from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.auth.factory import build_profile_service  # noqa: E402
from app.auth.profile import PracticeFacts  # noqa: E402
from app.auth.security import PasswordHasher  # noqa: E402
from app.bootstrap import postgres_database  # noqa: E402
from app.intake import IntakeService, SampleConnector  # noqa: E402
from app.intake.connectors.epic_fhir import SandboxRoster  # noqa: E402
from app.patients import format_full_name, nam  # noqa: E402
from app.postgresdb import (  # noqa: E402
    PatientRepository,
    PhysicianPatientRepository,
    PhysicianType,
    RemunerationType,
    UserRepository,
    UserRole,
    session_scope,
)
from app.sample_patients import get_sample_patients, parse_age_hint_years, parse_header_fields  # noqa: E402

ADMIN_EMAIL = "invite@nomiamd.com"
ADMIN_FULL_NAME = "Alex Chartrand"
ADMIN_PHYSICIAN_TYPE = PhysicianType.MED_FAM.value
ADMIN_PANEL_SIZE = 800
ADMIN_REMUNERATION_TYPE = RemunerationType.MIXTE.value

# A single fabricated placeholder, not a real RAMQ practice number — reused both as the
# seeded admin's own practice_number and as every seeded patient's
# family_doctor_practice_number, so every seeded patient resolves as "registered" with the
# admin once loaded — except those whose **Patient :** line says "non inscrit(e)" (walk-in,
# ER, shared-care notes), seeded with no family doctor: registration is derived from this
# exact-match comparison (see app/patients/registration.py), there's no separate flag to set.
SEED_PRACTICE_NUMBER = "123456"

# The em dash separates the name from the "NN ans (H/F)"/"NN mois (H/F)" demographic
# suffix on every **Patient :** header line — strips that suffix so format_full_name only
# ever sees the "Surname, Given" part.
_NAME_PREFIX_RE = re.compile(r"^(.*?)\s*[—-]\s*\d")

# Not preceded by "non " so "non vulnérable" (a code-eligibility phrase, never a positive
# patient fact) is never mistaken for one. Best-effort heuristic for dev-seed data only —
# consultations/README.md already flags vulnerability-status judgment calls as an open
# ambiguity in these fixtures, not something a regex can fully resolve.
_VULNERABLE_RE = re.compile(r"(?<!non )vuln[ée]rable", re.IGNORECASE)

# Matched against the **Patient :** header line only — the note body may well mention
# "patient non inscrit" while describing a billing rule or someone else.
_NOT_REGISTERED_RE = re.compile(r"\bnon[- ]inscrite?\b", re.IGNORECASE)


class _NoExtractionQueue:
    """Seeded encounters wait "reçu": extracting every note up front would spend one LLM run each."""

    async def enqueue(self, encounter_id: int) -> None:
        pass


def prompt_for_password() -> str:
    preset = os.environ.get("SEED_ADMIN_PASSWORD")
    if preset:
        return preset
    while True:
        password = getpass("Password for the new admin user: ")
        confirmation = getpass("Confirm password: ")
        if password == confirmation:
            return password
        print("Passwords didn't match, try again.")


def _name_as_stated(patient_field: str) -> str:
    match = _NAME_PREFIX_RE.match(patient_field)
    return match.group(1) if match else patient_field


def _family_doctor_name(fields: dict[str, str]) -> str | None:
    # "Dr. Louis-Philippe Gagné, MD, médecine familiale" -> "Dr. Louis-Philippe Gagné":
    # drop the trailing credential/specialty suffix, keep just the name.
    medecin = fields.get("Médecin", "").strip()
    return medecin.split(",", 1)[0].strip() or None


async def main() -> None:
    password = prompt_for_password()

    async with postgres_database():
        hashed_password = PasswordHasher().hash(password)
        # One transaction for the user and patients: a failure part-way leaves the DB as it
        # was. It commits before the encounters, which IntakeService receives in its own
        # sessions and resolves against these patients.
        async with session_scope() as session:
            try:
                admin = await UserRepository(session).create(
                    email=ADMIN_EMAIL,
                    hashed_password=hashed_password,
                    full_name=ADMIN_FULL_NAME,
                    role=UserRole.ADMIN,
                    practice_number=SEED_PRACTICE_NUMBER,
                )
            except IntegrityError:
                print(f"A user with email {ADMIN_EMAIL!r} already exists — DB wasn't wiped?", file=sys.stderr)
                raise SystemExit(1)

            # The practice facts live in their own dated table, so provisioning writes the
            # account's first profile version rather than more columns on `users`.
            await build_profile_service(session).record_practice_facts(
                admin.id,
                PracticeFacts(
                    physician_type=ADMIN_PHYSICIAN_TYPE,
                    panel_size=ADMIN_PANEL_SIZE,
                    remuneration_type=ADMIN_REMUNERATION_TYPE,
                ),
            )

            print(f"Created admin user {admin.email!r} (id={admin.id}, practice_number={SEED_PRACTICE_NUMBER!r})")

            patient_repository = PatientRepository(session)
            roster_repository = PhysicianPatientRepository(session)
            today = date.today()

            for sample in get_sample_patients():
                fields = parse_header_fields(sample.transcript)
                patient_field = fields.get("Patient", "")

                normalized_nam = nam.normalize(fields.get("NAM"))
                if normalized_nam is None:
                    print(f"  ! no patient for {sample.id!r}: no valid NAM in header", file=sys.stderr)
                    continue

                decoded = nam.decode(normalized_nam, on_date=today, age_hint=parse_age_hint_years(patient_field))
                if decoded is None:
                    print(f"  ! no patient for {sample.id!r}: could not decode NAM {normalized_nam!r}", file=sys.stderr)
                    continue

                full_name = format_full_name(_name_as_stated(patient_field)) or patient_field
                is_vulnerable = bool(_VULNERABLE_RE.search(sample.transcript))
                is_registered = not _NOT_REGISTERED_RE.search(patient_field)

                patient = await patient_repository.get_or_create_by_ramq_number(
                    ramq_number=normalized_nam,
                    full_name=full_name,
                    date_of_birth=decoded.date_of_birth,
                    gender=decoded.gender,
                    is_vulnerable=is_vulnerable,
                    family_doctor_name=_family_doctor_name(fields) if is_registered else None,
                    family_doctor_practice_number=SEED_PRACTICE_NUMBER if is_registered else None,
                )
                await roster_repository.add(admin.id, patient.id)
                print(
                    f"  + patient {patient.full_name!r} "
                    f"(id={patient.id}, vulnerable={is_vulnerable}, registered={is_registered})"
                )

            # The Epic sandbox demo's patients, under the fake NAMs its import resolves them
            # by (app/intake/connectors/epic_fhir/sandbox_patients.json). Synthetic too.
            for demo in SandboxRoster.load().patients():
                patient = await patient_repository.get_or_create_by_ramq_number(
                    ramq_number=demo.nam,
                    full_name=demo.full_name,
                    date_of_birth=demo.birth_date,
                    gender=demo.gender,
                    is_vulnerable=False,
                    family_doctor_name=None,
                    family_doctor_practice_number=SEED_PRACTICE_NUMBER,
                )
                await roster_repository.add(admin.id, patient.id)
                print(f"  + Epic sandbox patient {patient.full_name!r} (id={patient.id}, NAM {demo.nam})")

        # A sample whose patient wasn't created above still gets its encounter, "à associer".
        outcomes = await IntakeService(_NoExtractionQueue()).receive_all(SampleConnector().notes(), admin)
        for outcome in outcomes:
            print(f"  + encounter id={outcome.encounter_id} ({outcome.outcome}, patient_id={outcome.patient_id})")


if __name__ == "__main__":
    asyncio.run(main())
