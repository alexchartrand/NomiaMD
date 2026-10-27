"""Shift claim request/response models. Mirrored by hand in frontend/src/api/shiftClaims.ts."""

from datetime import date, datetime, time

from pydantic import BaseModel, Field

from app.care_setting import CareSetting
from app.claims.models import Money
from app.claims.origin import CodeOrigin
from app.claims.status import ClaimStatus
from app.shifts import ShiftOut, ShiftPeriod


class ShiftCodeOut(BaseModel):
    """A catalog code the physician may add to the shift's claim, with its fee on the shift's date."""

    code: str
    description: str
    quart_hours: int
    divisible_in_hours: bool
    hourly_fee: Money | None
    # The RAMQ secteur de dispensation it's billed under, e.g. "07" — Service d'urgence.
    secteur_dispensation: str
    secteur_dispensation_label: str
    source: str


class SuggestedShiftCodeOut(BaseModel):
    """A code the shift's rules earned, for the hours they counted."""

    code: str
    description: str
    hours: int
    hourly_fee: Money | None
    fee_amount: Money | None
    secteur_dispensation: str
    secteur_dispensation_label: str
    source: str


class ShiftClaimLineIn(BaseModel):
    code: str
    hours: int = Field(gt=0, le=24)


class ShiftClaimIn(BaseModel):
    """The codes the physician confirms. Descriptions and fees come from the catalog, never
    from here."""

    codes: list[ShiftClaimLineIn]


class ShiftClaimCodeOut(BaseModel):
    code: str
    description: str
    origin: CodeOrigin
    hours: int
    hourly_fee: Money | None
    fee_amount: Money | None
    secteur_dispensation: str
    secteur_dispensation_label: str
    source: str

    model_config = {"from_attributes": True}


class ShiftClaimOut(BaseModel):
    id: int
    shift_id: int
    # The shift as claimed, snapshotted at save time.
    service_date: date
    start_time: time
    end_time: time
    ends_next_day: bool
    care_setting: CareSetting
    period: ShiftPeriod
    work_site_name: str
    status: ClaimStatus
    bill_id: int | None
    codes: list[ShiftClaimCodeOut]
    total_amount: Money | None
    created_at: datetime
    updated_at: datetime


class ShiftBillingOut(BaseModel):
    """Everything the schedule's shift drawer shows: the shift, what its rules suggest, the
    other codes its care setting allows, and its live claim if any."""

    shift: ShiftOut
    suggested: list[SuggestedShiftCodeOut]
    available_codes: list[ShiftCodeOut]
    claim: ShiftClaimOut | None
