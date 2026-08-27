"""Manually provision a login — there is no signup page/API, accounts are created by an
operator running this script. From backend/, with the venv active:

    python scripts/create_user.py --email doc@example.com --full-name "Dr. X" --role physician \\
        [--physician-type "GMF"] [--number-of-patients 850] [--remuneration-type "Mixte"]

The password is never accepted as a CLI argument (it would end up in shell history and
`ps` output) — it's prompted for interactively instead.
"""

import argparse
import asyncio
import sys
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Must run before app.postgresdb is imported below — app.config.settings reads DATABASE_URL
# at import time. Explicit path for the same reason as app/main.py: under a debugger,
# load_dotenv() searches os.getcwd() instead of walking up from this file.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.auth.security import PasswordHasher  # noqa: E402
from app.postgresdb import (  # noqa: E402
    PhysicianProfileRepository,
    UserRepository,
    UserRole,
    init_db,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--role", required=True, choices=[role.value for role in UserRole])
    parser.add_argument("--physician-type", default=None)
    parser.add_argument("--number-of-patients", type=int, default=None)
    parser.add_argument("--remuneration-type", default=None)
    return parser.parse_args()


def prompt_for_password() -> str:
    while True:
        password = getpass("Password: ")
        confirmation = getpass("Confirm password: ")
        if password == confirmation:
            return password
        print("Passwords didn't match, try again.")


async def main() -> None:
    args = parse_args()
    password = prompt_for_password()

    await init_db()  # a fresh DB (e.g. first run) has no `users` table yet
    hashed_password = PasswordHasher().hash(password)
    try:
        user = await UserRepository().create(
            email=args.email,
            hashed_password=hashed_password,
            full_name=args.full_name,
            role=UserRole(args.role),
        )
    except IntegrityError:
        print(f"A user with email {args.email!r} already exists.", file=sys.stderr)
        raise SystemExit(1)

    # The practice facts live in their own dated table, so provisioning writes the
    # account's first profile version rather than more columns on `users`.
    if any((args.physician_type, args.number_of_patients, args.remuneration_type)):
        await PhysicianProfileRepository().upsert_current(
            user.id,
            physician_type=args.physician_type,
            number_of_patients=args.number_of_patients,
            remuneration_type=args.remuneration_type,
        )

    print(f"Created user {user.email!r} (id={user.id}, role={user.role.value})")


if __name__ == "__main__":
    asyncio.run(main())
