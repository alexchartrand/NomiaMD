"""The admin console's system page: is each dependency reachable, what is it configured to
use, and how much data is there. Configuration is reported by name only — never a key, an
endpoint's credentials or any patient data."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import settings
from app.lancedb import ICodeCatalogRepository
from app.llm.structured import resolve_model
from app.postgresdb import EncounterRepository, TableStatsRepository
from app.ramq_chatbot.factory import CHAT_MODEL
from app.ramq_codes import CodeSelector
from app.summary import ConsultationSummarizer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DependencyCheck:
    ok: bool
    detail: str


@dataclass(frozen=True)
class ModelConfiguration:
    chat_provider: str
    embedding_provider: str
    embedding_model: str | None
    # Chat model per pipeline step, as each call would resolve it now.
    step_models: dict[str, str]


@dataclass(frozen=True)
class SystemReport:
    checked_at: datetime
    app_env: str
    app_version: str | None
    database: DependencyCheck
    codes_table: DependencyCheck
    models: ModelConfiguration
    row_counts: dict[str, int]
    failed_extractions: int
    encounters_past_purge: int


class SystemStatus:
    def __init__(
        self,
        tables: TableStatsRepository,
        encounters: EncounterRepository,
        codes: ICodeCatalogRepository | None,
    ) -> None:
        """`codes`: None when the code catalog isn't initialized (reported as down)."""
        self._tables = tables
        self._encounters = encounters
        self._codes = codes

    async def report(self) -> SystemReport:
        now = datetime.now(timezone.utc)
        dialect = await self._tables.ping()
        return SystemReport(
            checked_at=now,
            app_env=settings.app_env,
            app_version=settings.app_version,
            database=DependencyCheck(ok=True, detail=dialect),
            codes_table=await self._codes_table(),
            models=_model_configuration(),
            row_counts=await self._tables.row_counts(),
            failed_extractions=len(await self._encounters.list_failed_extractions(limit=1000)),
            encounters_past_purge=await self._encounters.count_past_purge(now),
        )

    async def _codes_table(self) -> DependencyCheck:
        if self._codes is None:
            return DependencyCheck(ok=False, detail="non initialisée")
        try:
            return DependencyCheck(ok=True, detail=await self._codes.current_revision())
        except Exception as exc:
            logger.exception("Codes table check failed")
            return DependencyCheck(ok=False, detail=type(exc).__name__)


def _model_configuration() -> ModelConfiguration:
    return ModelConfiguration(
        chat_provider=settings.llm_provider,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        step_models={
            ConsultationSummarizer.NAME: resolve_model(ConsultationSummarizer.NAME, ConsultationSummarizer.DEFAULT_MODEL),
            CodeSelector.NAME: resolve_model(CodeSelector.NAME, CodeSelector.DEFAULT_MODEL),
            "ramq_chatbot": resolve_model("ramq_chatbot", CHAT_MODEL),
        },
    )
