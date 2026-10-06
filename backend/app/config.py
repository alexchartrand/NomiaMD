"""Central place for environment-derived runtime configuration. Loads the repo-root `.env`
on import (the one file docker compose also reads; scripts import this module to load it)
and exposes a `settings` singleton — every other module should read config through it
instead of touching `os.environ` directly.

The `llm_*`/`embedding_*` provider settings are named by role (chat, embeddings), not by
vendor: whichever provider LLM_PROVIDER/EMBEDDING_PROVIDER selects reads them. They're
read lazily via property, not cached at construction: tests' `no_real_api_keys` fixture
(tests/conftest.py) deletes the API keys from the environment per-test specifically to make any un-stubbed real-API
code path raise instead of silently succeeding — caching the key at import time would
defeat that safety net.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Explicit path: under a debugger, load_dotenv() searches os.getcwd() instead. A missing file
# is a no-op — in the containers, compose's env_file has already set the environment.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


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
        # Concurrent extractions per worker process; size to the LLM endpoint's throughput.
        self.worker_max_jobs = int(os.environ.get("WORKER_MAX_JOBS", 4))
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")

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
        """The chat provider's key, whichever LLM_PROVIDER selects. Separate from
        embedding_api_key: chat and embeddings can be different hosts (`make dev-fake`
        points chat at the fake server while embeddings stay on Mistral)."""
        return os.environ["LLM_API_KEY"]

    @property
    def embedding_provider(self) -> str:
        """Which embedding backend app/llm/embeddings.py builds: `mistral` (default) or
        `openai_compatible`."""
        return os.environ.get("EMBEDDING_PROVIDER", "mistral").strip().lower()

    @property
    def embedding_endpoint(self) -> str | None:
        return os.environ.get("EMBEDDING_ENDPOINT") or None

    @property
    def embedding_model(self) -> str | None:
        """Required by every provider: the model ramq-ingestion embedded the LanceDB tables
        with."""
        return os.environ.get("EMBEDDING_MODEL") or None

    @property
    def embedding_api_key(self) -> str | None:
        """The embedding provider's key, whichever EMBEDDING_PROVIDER selects. Required by
        mistral; optional for openai_compatible (TEI and vLLM run without auth by default)."""
        return os.environ.get("EMBEDDING_API_KEY") or None

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
        """The PEM private key whose public half GET /.well-known/jwks.json serves
        (app/jwks/public_keys/), the fhir.epic.com app's JWK Set URL. Kept outside the repo."""
        return Path(os.environ["EPIC_SANDBOX_PRIVATE_KEY_PATH"]).expanduser()

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
