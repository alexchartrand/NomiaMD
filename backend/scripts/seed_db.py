"""Seed a freshly wiped database with a demo admin user and all 25 simulated consultation-
note patients, for local development. From backend/, with the venv active:

    python scripts/seed_db.py

Prompts for the new user's password interactively (same reasoning as create_user.py: never
accepted as a CLI argument, to avoid it ending up in shell history/`ps` output). Fails
loudly (rather than upserting) if the admin email already exists — that means the DB wasn't
actually wiped, so re-run against a clean DB instead of layering seed data on top of itself.
"""

import asyncio
import re
import sys
from datetime import date
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.auth.security import PasswordHasher  # noqa: E402
from app.patients import format_full_name, nam  # noqa: E402
from app.postgresdb import (  # noqa: E402
    PatientRepository,
    PhysicianPatientRepository,
    PhysicianProfileRepository,
    PhysicianType,
    RemunerationType,
    UserRepository,
    UserRole,
    init_db,
)
from app.sample_patients import get_sample_patients, parse_age_hint_years, parse_header_fields  # noqa: E402

ADMIN_EMAIL = "invite@nomiamd.com"
ADMIN_FULL_NAME = "Alex Chartrand"
ADMIN_PHYSICIAN_TYPE = PhysicianType.MED_FAM.value
ADMIN_NUMBER_OF_PATIENTS = 800
ADMIN_REMUNERATION_TYPE = RemunerationType.MIXTE.value

# A single fabricated placeholder, not a real RAMQ practice number — reused both as the
# seeded admin's own practice_number and as every seeded patient's
# family_doctor_practice_number, so all 25 automatically resolve as "registered" with the
# admin once loaded: registration is derived from this exact-match comparison (see
# app/patients/registration.py), there's no separate flag left to set.
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


def prompt_for_password() -> str:
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

    await init_db()  # a fresh DB (e.g. right after a wipe) has no tables yet
    hashed_password = PasswordHasher().hash(password)
    try:
        admin = await UserRepository().create(
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
    await PhysicianProfileRepository().upsert_current(
        admin.id,
        physician_type=ADMIN_PHYSICIAN_TYPE,
        number_of_patients=ADMIN_NUMBER_OF_PATIENTS,
        remuneration_type=ADMIN_REMUNERATION_TYPE,
    )

    print(f"Created admin user {admin.email!r} (id={admin.id}, practice_number={SEED_PRACTICE_NUMBER!r})")

    patient_repository = PatientRepository()
    roster_repository = PhysicianPatientRepository()
    today = date.today()

    for sample in get_sample_patients():
        fields = parse_header_fields(sample.transcript)
        patient_field = fields.get("Patient", "")

        normalized_nam = nam.normalize(fields.get("NAM"))
        if normalized_nam is None:
            print(f"  ! skipping {sample.id!r}: no valid NAM in header", file=sys.stderr)
            continue

        decoded = nam.decode(normalized_nam, on_date=today, age_hint=parse_age_hint_years(patient_field))
        if decoded is None:
            print(f"  ! skipping {sample.id!r}: could not decode NAM {normalized_nam!r}", file=sys.stderr)
            continue

        full_name = format_full_name(_name_as_stated(patient_field)) or patient_field
        is_vulnerable = bool(_VULNERABLE_RE.search(sample.transcript))

        patient = await patient_repository.get_or_create_by_ramq_number(
            ramq_number=normalized_nam,
            full_name=full_name,
            date_of_birth=decoded.date_of_birth,
            gender=decoded.gender,
            is_vulnerable=is_vulnerable,
            family_doctor_name=_family_doctor_name(fields),
            family_doctor_practice_number=SEED_PRACTICE_NUMBER,
        )
        await roster_repository.add(admin.id, patient.id)
        print(f"  + patient {patient.full_name!r} (id={patient.id}, vulnerable={is_vulnerable})")


if __name__ == "__main__":
    asyncio.run(main())
