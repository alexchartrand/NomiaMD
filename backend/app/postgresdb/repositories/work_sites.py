"""`work_sites` — the places a physician works."""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from app.postgresdb.models import WorkSite
from app.postgresdb.repositories.base import SessionRepository


@dataclass
class WorkSiteInput:
    name: str
    care_setting: str
    etablissement_number: str | None


class WorkSiteRepository(SessionRepository):
    """Stores a physician's work sites. Every read is scoped to its owner; deactivated
    sites are listed only when asked for."""

    async def create(self, user_id: int, data: WorkSiteInput) -> WorkSite:
        site = WorkSite(
            user_id=user_id,
            name=data.name,
            care_setting=data.care_setting,
            etablissement_number=data.etablissement_number,
        )
        self._session.add(site)
        await self._session.flush()
        return site

    async def update(self, site: WorkSite, data: WorkSiteInput) -> WorkSite:
        site.name = data.name
        site.care_setting = data.care_setting
        site.etablissement_number = data.etablissement_number
        await self._session.flush()
        return site

    async def list_for_user(self, user_id: int, *, include_inactive: bool = False) -> list[WorkSite]:
        query = select(WorkSite).where(WorkSite.user_id == user_id)
        if not include_inactive:
            query = query.where(WorkSite.is_active.is_(True))
        result = await self._session.execute(query.order_by(WorkSite.name, WorkSite.id))
        return list(result.scalars().all())

    async def get_for_user(self, site_id: int, user_id: int) -> WorkSite | None:
        site = await self._session.get(WorkSite, site_id)
        if site is None or site.user_id != user_id:
            return None
        return site

    async def deactivate(self, site: WorkSite) -> None:
        site.is_active = False
        site.deactivated_at = datetime.now(timezone.utc)
        await self._session.flush()

    async def reactivate(self, site: WorkSite) -> None:
        site.is_active = True
        site.deactivated_at = None
        await self._session.flush()
