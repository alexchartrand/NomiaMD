"""Seed a freshly wiped database with a demo admin user and two sample patients, for local
development. From backend/, with the venv active:

    python scripts/seed_db.py

Prompts for the new user's password interactively (same reasoning as create_user.py: never
accepted as a CLI argument, to avoid it ending up in shell history/`ps` output). Fails
loudly (rather than upserting) if the admin email already exists — that means the DB wasn't
actually wiped, so re-run against a clean DB instead of layering seed data on top of itself.
"""

import asyncio
import sys
from datetime import date
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.auth.security import PasswordHasher  # noqa: E402
from app.postgresdb import Gender, PatientRepository, PhysicianType, UserRepository, UserRole, init_db  # noqa: E402

ADMIN_EMAIL = "invite@nomiamd.com"
ADMIN_FULL_NAME = "Alex Chartrand"
ADMIN_PHYSICIAN_TYPE = PhysicianType.MED_FAM.value
ADMIN_NUMBER_OF_PATIENTS = 800

# From consultations/01_hta_prise_en_charge.md and consultations/04_grossesse_suivi_t3.md.
SEED_PATIENTS = [
    {
        "full_name": "Roch Desjardins",
        "ramq_number": "DESR81021001",
        "date_of_birth": date(1981, 2, 10),
        "gender": Gender.MALE,
        "is_registered_with_physician": True,
        "is_vulnerable": False,
    },
    {
        "full_name": "Sabrina Nadeau",
        "ramq_number": "NADS94052201",
        "date_of_birth": date(1994, 5, 22),
        "gender": Gender.FEMALE,
        "is_registered_with_physician": True,
        "is_vulnerable": False,
    },
]


def prompt_for_password() -> str:
    while True:
        password = getpass("Password for the new admin user: ")
        confirmation = getpass("Confirm password: ")
        if password == confirmation:
            return password
        print("Passwords didn't match, try again.")


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
            physician_type=ADMIN_PHYSICIAN_TYPE,
            number_of_patients=ADMIN_NUMBER_OF_PATIENTS,
        )
    except IntegrityError:
        print(f"A user with email {ADMIN_EMAIL!r} already exists — DB wasn't wiped?", file=sys.stderr)
        raise SystemExit(1)

    print(f"Created admin user {admin.email!r} (id={admin.id})")

    patient_repository = PatientRepository()
    for seed in SEED_PATIENTS:
        patient = await patient_repository.create(physician_id=admin.id, **seed)
        print(f"  + patient {patient.full_name!r} (id={patient.id})")


if __name__ == "__main__":
    asyncio.run(main())
