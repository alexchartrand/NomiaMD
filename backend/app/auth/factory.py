"""Composition root for AuthService and ProfileService. Both are built per session, since
their repositories work inside the caller's transaction (see app/postgresdb/session.py):
`build_*` for a session the caller already holds, `get_*` as the per-request FastAPI
dependency."""

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.profile import ProfileService
from app.auth.security import PasswordHasher, TokenService
from app.auth.service import AuthService
from app.config import settings
from app.postgresdb import DbSession, PhysicianProfileRepository, UserRepository


@lru_cache(maxsize=1)
def _password_hasher() -> PasswordHasher:
    return PasswordHasher()


@lru_cache(maxsize=1)
def _token_service() -> TokenService:
    return TokenService(settings.secret_key, settings.jwt_expiry_seconds, settings.jwt_remember_me_expiry_seconds)


def build_auth_service(session: AsyncSession) -> AuthService:
    return AuthService(
        user_repository=UserRepository(session),
        password_hasher=_password_hasher(),
        token_service=_token_service(),
    )


def build_profile_service(session: AsyncSession) -> ProfileService:
    return ProfileService(
        user_repository=UserRepository(session),
        profile_repository=PhysicianProfileRepository(session),
    )


def get_auth_service(session: DbSession) -> AuthService:
    return build_auth_service(session)


def get_profile_service(session: DbSession) -> ProfileService:
    return build_profile_service(session)
