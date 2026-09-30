"""Shared test-DB seeding. SQLite enforces foreign keys now (app/postgresdb/database.py), so
a fixed-id in-memory User handed to a route or repository must also exist as a real `users`
row before anything referencing it (claims, extraction records, roster entries) is written."""

from app.postgresdb import User, UserRole, session_scope


async def ensure_user_row(user: User) -> None:
    """Inserts a `users` row mirroring `user` unless one with its id already exists —
    idempotent, since the test DB is shared across the whole session (see conftest.py) and
    tests/test_auth.py also creates autoincremented users in it."""
    async with session_scope() as session:
        if await session.get(User, user.id) is not None:
            return
        session.add(
            User(
                id=user.id,
                email=user.email,
                hashed_password=user.hashed_password or "!",
                full_name=user.full_name,
                role=user.role,
                is_active=user.is_active,
                practice_number=user.practice_number,
            )
        )


def physician(user_id: int) -> User:
    """A minimal in-memory physician for repository tests that only need a valid
    physician_id — pass it through ensure_user_row before writing rows against it."""
    return User(
        id=user_id,
        email=f"physician-{user_id}@example.test",
        full_name=f"Dr. {user_id}",
        role=UserRole.PHYSICIAN,
        is_active=True,
    )
