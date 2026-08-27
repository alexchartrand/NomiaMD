from functools import lru_cache

from app.auth.profile import ProfileService
from app.auth.security import PasswordHasher, TokenService
from app.auth.service import AuthService
from app.config import settings
from app.postgresdb import PhysicianProfileRepository, UserRepository


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    return AuthService(
        user_repository=UserRepository(),
        password_hasher=PasswordHasher(),
        token_service=TokenService(
            settings.secret_key, settings.jwt_expiry_seconds, settings.jwt_remember_me_expiry_seconds
        ),
    )


@lru_cache(maxsize=1)
def get_profile_service() -> ProfileService:
    return ProfileService(
        user_repository=UserRepository(),
        profile_repository=PhysicianProfileRepository(),
    )
