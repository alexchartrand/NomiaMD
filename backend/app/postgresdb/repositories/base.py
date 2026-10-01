"""Shared base for every repository in this package — see __init__.py for the session contract."""

from sqlalchemy.ext.asyncio import AsyncSession


class SessionRepository:
    """Holds the session a repository works in. The session's owner (session.py's
    session_scope, or the per-request DbSession) commits or rolls back — never the
    repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
