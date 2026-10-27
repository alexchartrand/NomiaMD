"""Work site and shift request/response models."""

from datetime import date, time
from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

from app.care_setting import CareSetting
from app.shifts.day_type import DayType
from app.shifts.periods import ShiftPeriod

# The settings a work site can be, for now: the ER, the ward, a CHSLD and a GMF. Cabinet and
# domicile stay pickable at paste/upload but aren't places a physician schedules shifts at yet.
SITE_CARE_SETTINGS = (CareSetting.URGENCE, CareSetting.HOSPITALISATION, CareSetting.CHSLD, CareSetting.GMF)

SiteName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
EtablissementNumber = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16)]


class WorkSiteIn(BaseModel):
    name: SiteName
    care_setting: CareSetting
    etablissement_number: EtablissementNumber | None = None

    @field_validator("care_setting")
    @classmethod
    def _schedulable(cls, value: CareSetting) -> CareSetting:
        if value not in SITE_CARE_SETTINGS:
            raise ValueError(f"care_setting must be one of {', '.join(SITE_CARE_SETTINGS)}")
        return value


class WorkSiteOut(BaseModel):
    id: int
    name: str
    care_setting: CareSetting
    etablissement_number: str | None
    is_active: bool


class ShiftIn(BaseModel):
    work_site_id: int
    period: ShiftPeriod
    service_date: date
    start_time: time
    end_time: time


class ShiftOut(BaseModel):
    id: int
    work_site_id: int
    work_site_name: str
    care_setting: CareSetting
    period: ShiftPeriod
    service_date: date
    start_time: time
    end_time: time
    ends_next_day: bool
    day_type: DayType


class PeriodDefaultOut(BaseModel):
    period: ShiftPeriod
    label: str
    start_time: time
    end_time: time
