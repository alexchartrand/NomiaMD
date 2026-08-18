from functools import lru_cache

from app.auth.security import PasswordHasher, TokenService
from app.auth.service import AuthService
from app.config import settings
from app.postgresdb import UserRepository


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    return AuthService(
        user_repository=UserRepository(),
        password_hasher=PasswordHasher(),
        token_service=TokenService(settings.secret_key, settings.jwt_expiry_seconds),
    )
