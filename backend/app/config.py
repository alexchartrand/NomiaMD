"""Central place for environment-derived runtime configuration. Loads `.env` on import
(mirrors the previous per-entrypoint `load_dotenv()` calls) and exposes a `settings`
singleton — every other module should read config through it instead of touching
`os.environ` directly.

`mistral_api_key`/`mistral_embedding_model` are read lazily via property, not cached at
construction: tests' `no_real_api_keys` fixture (tests/conftest.py) deletes
MISTRAL_API_KEY from the environment per-test specifically to make any un-stubbed real-API
code path raise instead of silently succeeding — caching the key at import time would
defeat that safety net.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes")


class Settings:
    def __init__(self) -> None:
        self.debug = _as_bool(os.environ.get("DEBUG"), default=False)
        self.database_url = os.environ.get("DATABASE_URL") or "sqlite+aiosqlite:///./nomiamd.db"
        self.redis_url = os.environ.get("REDIS_URL", "memory://")
        self.db_path = os.environ["DB_PATH"]
        self.ramq_chatbot_db_path = os.environ["RAMQ_CHATBOT_DB_PATH"]
        self.secret_key = os.environ["JWT_SECRET_KEY"]
        self.jwt_expiry_seconds = int(os.environ.get("JWT_EXPIRY_SECONDS", 12 * 3600))
        self.cookie_secure = _as_bool(os.environ.get("COOKIE_SECURE"), default=True)

    @property
    def mistral_api_key(self) -> str:
        return os.environ["MISTRAL_API_KEY"]

    @property
    def mistral_embedding_model(self) -> str:
        return os.environ["MISTRAL_EMBEDDING_MODEL"]


settings = Settings()
