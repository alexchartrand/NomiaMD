"""Sources we go and fetch notes from (a FHIR server, a partner API), as opposed to push
channels, which call IntakeService.receive themselves."""

from abc import ABC, abstractmethod
from datetime import date

from app.intake.models import SourceNote
from app.postgresdb import User


class PullConnector(ABC):
    @abstractmethod
    async def fetch_signed_notes(self, user: User, since: date | None = None) -> list[SourceNote]:
        """The physician's signed notes the source holds, from `since` on (every one when
        None). Unsigned drafts are never returned: only what the physician signed is billed."""
