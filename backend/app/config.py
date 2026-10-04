"""Central place for environment-derived runtime configuration. Loads `.env` on import
(mirrors the previous per-entrypoint `load_dotenv()` calls) and exposes a `settings`
singleton — every other module should read config through it instead of touching
`os.environ` directly.

`mistral_api_key`/`mistral_embedding_model` and the `llm_*`/`embedding_*` provider
settings are read lazily via property, not cached at
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
        self.secret_key = os.environ["JWT_SECRET_KEY"]
        self.jwt_expiry_seconds = int(os.environ.get("JWT_EXPIRY_SECONDS", 12 * 3600))
        self.jwt_remember_me_expiry_seconds = int(
            os.environ.get("JWT_REMEMBER_ME_EXPIRY_SECONDS", 30 * 24 * 3600)
        )
        self.cookie_secure = _as_bool(os.environ.get("COOKIE_SECURE"), default=True)
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")

    @property
    def mistral_api_key(self) -> str:
        return os.environ["MISTRAL_API_KEY"]

    @property
    def mistral_embedding_model(self) -> str:
        return os.environ["MISTRAL_EMBEDDING_MODEL"]

    @property
    def llm_provider(self) -> str:
        """Which chat backend app/llm/chat.py builds: `mistral` (default) or
        `openai_compatible`."""
        return os.environ.get("LLM_PROVIDER", "mistral").strip().lower()

    @property
    def llm_endpoint(self) -> str | None:
        return os.environ.get("LLM_ENDPOINT") or None

    @property
    def llm_api_key(self) -> str:
        """Only read by the openai_compatible provider; the mistral one uses
        mistral_api_key (shared with embeddings)."""
        return os.environ["LLM_API_KEY"]

    @property
    def embedding_provider(self) -> str:
        """Which embedding backend app/llm/embeddings.py builds: `mistral` (default, model
        from MISTRAL_EMBEDDING_MODEL) or `openai_compatible`."""
        return os.environ.get("EMBEDDING_PROVIDER", "mistral").strip().lower()

    @property
    def embedding_endpoint(self) -> str | None:
        return os.environ.get("EMBEDDING_ENDPOINT") or None

    @property
    def embedding_model(self) -> str | None:
        """Only read by the openai_compatible provider."""
        return os.environ.get("EMBEDDING_MODEL") or None

    @property
    def embedding_api_key(self) -> str:
        """Only read by the openai_compatible provider. Optional: TEI and vLLM run without
        auth by default, and the OpenAI client needs some non-empty value."""
        return os.environ.get("EMBEDDING_API_KEY") or "unused"

    @property
    def smtp_host(self) -> str | None:
        """Outgoing mail for contact-form notifications (app/contact/notifier.py). Unset =
        notifications are only logged."""
        return os.environ.get("SMTP_HOST") or None

    @property
    def smtp_port(self) -> int:
        return int(os.environ.get("SMTP_PORT", 587))

    @property
    def smtp_username(self) -> str | None:
        return os.environ.get("SMTP_USERNAME") or None

    @property
    def smtp_password(self) -> str | None:
        return os.environ.get("SMTP_PASSWORD") or None

    @property
    def smtp_from(self) -> str | None:
        return os.environ.get("SMTP_FROM") or self.smtp_username

    @property
    def contact_notify_email(self) -> str | None:
        """Where a new contact-form request is announced."""
        return os.environ.get("CONTACT_NOTIFY_EMAIL") or None

    @property
    def app_env(self) -> str:
        """`development` (default) or `production` — what demo-only features check before
        they may turn on."""
        return os.environ.get("APP_ENV", "development").strip().lower()

    @property
    def epic_sandbox_enabled(self) -> bool:
        """The Epic sandbox demo import (app/intake/connectors/epic_fhir/). Refused at
        startup when app_env is production."""
        return _as_bool(os.environ.get("EPIC_SANDBOX_ENABLED"), default=False)

    @property
    def epic_sandbox_client_id(self) -> str:
        """The fhir.epic.com app's non-production client id."""
        return os.environ["EPIC_SANDBOX_CLIENT_ID"]

    @property
    def epic_sandbox_private_key_path(self) -> Path:
        """The PEM private key whose public half the fhir.epic.com app's JWK Set URL serves
        (scripts/epic_sandbox_jwks.py). Kept outside the repo."""
        return Path(os.environ["EPIC_SANDBOX_PRIVATE_KEY_PATH"]).expanduser()

    @property
    def epic_sandbox_key_id(self) -> str | None:
        """The JWT `kid`: which key of the JWK Set signed the assertion."""
        return os.environ.get("EPIC_SANDBOX_KEY_ID") or None

    @property
    def epic_sandbox_fhir_base_url(self) -> str:
        return os.environ.get(
            "EPIC_SANDBOX_FHIR_BASE_URL", "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4/"
        )

    @property
    def epic_sandbox_token_url(self) -> str:
        return os.environ.get(
            "EPIC_SANDBOX_TOKEN_URL", "https://fhir.epic.com/interconnect-fhir-oauth/oauth2/token"
        )


settings = Settings()
