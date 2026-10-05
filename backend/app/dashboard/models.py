"""Response shapes for /dashboard. Mirrored by hand in frontend/src/api/dashboard.ts."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.claims.models import Money
from app.encounters.models import EncounterRowOut


class TaskCountsOut(BaseModel):
    """What the physician still has to act on, by kind — the same statuses the inbox's
    "à traiter" filter covers (reçu, prêt, à associer, échec)."""

    to_do: int
    to_review: int
    # Of `to_review`, those approvable from the inbox without opening them (all_clean).
    approvable: int
    to_associate: int
    failed: int
    extracting: int
    possible_duplicates: int


class KpisOut(BaseModel):
    encounters_this_week: int
    draft_count: int
    draft_total: Money
    billed_this_month: Money


class DeadlineItemOut(BaseModel):
    """Unbilled work close to (or past) RAMQ's billing deadline: an encounter not reviewed
    yet, or a draft claim not on a bill yet."""

    kind: Literal["encounter", "claim"]
    id: int
    patient_display: str | None
    service_date: date
    # Negative once the deadline has passed.
    days_left: int


class WeekActivityOut(BaseModel):
    week_start: date
    received: int
    reviewed: int


class DashboardOut(BaseModel):
    today: date
    tasks: TaskCountsOut
    kpis: KpisOut
    deadlines: list[DeadlineItemOut]
    weekly_activity: list[WeekActivityOut]
    recent_encounters: list[EncounterRowOut]
