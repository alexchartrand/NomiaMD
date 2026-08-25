"""Reset an existing user's password — for when a manually-provisioned login (there is no
signup/forgot-password page, see create_user.py) is locked out. From backend/, with the
venv active:

    python scripts/reset_password.py --email doc@example.com

The new password is never accepted as a CLI argument (it would end up in shell
history/`ps` output) — it's prompted for interactively instead, same as create_user.py.
"""

import argparse
import asyncio
import sys
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.auth.security import PasswordHasher  # noqa: E402
from app.postgresdb import UserRepository, init_db  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    return parser.parse_args()


def prompt_for_password() -> str:
    while True:
        password = getpass("New password: ")
        confirmation = getpass("Confirm password: ")
        if password == confirmation:
            return password
        print("Passwords didn't match, try again.")


async def main() -> None:
    args = parse_args()

    await init_db()
    users = UserRepository()
    user = await users.get_by_email(args.email)
    if user is None:
        print(f"No user with email {args.email!r}.", file=sys.stderr)
        raise SystemExit(1)

    password = prompt_for_password()
    await users.update_password_hash(user.id, PasswordHasher().hash(password))

    print(f"Password reset for {user.email!r} (id={user.id}).")


if __name__ == "__main__":
    asyncio.run(main())
