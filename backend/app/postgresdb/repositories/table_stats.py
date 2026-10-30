"""Row counts per table, for the admin console's system page. Read-only, across aggregates."""

from sqlalchemy import func, select

from app.postgresdb.models import (
    AuditEvent,
    Bill,
    Claim,
    ContactRequest,
    Encounter,
    ExtractionRun,
    LLMCall,
    LLMUsageDay,
    Patient,
    User,
)
from app.postgresdb.repositories.base import SessionRepository

_COUNTED = {
    "users": User,
    "patients": Patient,
    "encounters": Encounter,
    "extraction_runs": ExtractionRun,
    "claims": Claim,
    "bills": Bill,
    "contact_requests": ContactRequest,
    "llm_calls": LLMCall,
    "llm_usage_daily": LLMUsageDay,
    "audit_events": AuditEvent,
}


class TableStatsRepository(SessionRepository):
    async def row_counts(self) -> dict[str, int]:
        return {
            name: (await self._session.execute(select(func.count()).select_from(model))).scalar_one()
            for name, model in _COUNTED.items()
        }

    async def ping(self) -> str:
        """Round-trips the database and returns its dialect name ("sqlite", "postgresql")."""
        await self._session.execute(select(1))
        return self._session.bind.dialect.name
