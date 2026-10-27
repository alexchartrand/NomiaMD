from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_user
from app.postgresdb import User
from app.shifts.factory import get_shift_service, get_work_site_service
from app.shifts.models import (
    PeriodDefaultOut,
    ShiftIn,
    ShiftOut,
    ShiftSeriesIn,
    ShiftSeriesUpdateIn,
    WorkSiteIn,
    WorkSiteOut,
)
from app.shifts.periods import DEFAULT_PERIOD_HOURS, SHIFT_PERIOD_LABELS_FR
from app.shifts.service import (
    EmptySeriesError,
    RangeTooLongError,
    ShiftService,
    SiteUnavailableError,
    WorkSiteService,
)

work_sites_router = APIRouter(prefix="/work-sites", tags=["shifts"])
shifts_router = APIRouter(prefix="/shifts", tags=["shifts"])

_SITE_NOT_FOUND = "Lieu de travail introuvable"
_SHIFT_NOT_FOUND = "Quart introuvable"
_SERIES_NOT_FOUND = "Série de quarts introuvable"


@work_sites_router.get("", response_model=list[WorkSiteOut])
async def list_work_sites(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    service: WorkSiteService = Depends(get_work_site_service),
) -> list[WorkSiteOut]:
    return await service.list(current_user.id, include_inactive=include_inactive)


@work_sites_router.post("", response_model=WorkSiteOut, status_code=status.HTTP_201_CREATED)
async def create_work_site(
    body: WorkSiteIn,
    current_user: User = Depends(get_current_user),
    service: WorkSiteService = Depends(get_work_site_service),
) -> WorkSiteOut:
    return await service.create(current_user.id, body)


@work_sites_router.put("/{site_id}", response_model=WorkSiteOut)
async def update_work_site(
    site_id: int,
    body: WorkSiteIn,
    current_user: User = Depends(get_current_user),
    service: WorkSiteService = Depends(get_work_site_service),
) -> WorkSiteOut:
    site = await service.update(current_user.id, site_id, body)
    if site is None:
        raise HTTPException(status_code=404, detail=_SITE_NOT_FOUND)
    return site


@work_sites_router.post("/{site_id}/deactivate", response_model=WorkSiteOut)
async def deactivate_work_site(
    site_id: int,
    current_user: User = Depends(get_current_user),
    service: WorkSiteService = Depends(get_work_site_service),
) -> WorkSiteOut:
    site = await service.set_active(current_user.id, site_id, False)
    if site is None:
        raise HTTPException(status_code=404, detail=_SITE_NOT_FOUND)
    return site


@work_sites_router.post("/{site_id}/reactivate", response_model=WorkSiteOut)
async def reactivate_work_site(
    site_id: int,
    current_user: User = Depends(get_current_user),
    service: WorkSiteService = Depends(get_work_site_service),
) -> WorkSiteOut:
    site = await service.set_active(current_user.id, site_id, True)
    if site is None:
        raise HTTPException(status_code=404, detail=_SITE_NOT_FOUND)
    return site


@shifts_router.get("/periods", response_model=list[PeriodDefaultOut])
async def list_period_defaults(current_user: User = Depends(get_current_user)) -> list[PeriodDefaultOut]:
    """The hours the calendar prefills for each period."""
    return [
        PeriodDefaultOut(period=period, label=SHIFT_PERIOD_LABELS_FR[period], start_time=h.start_time, end_time=h.end_time)
        for period, h in DEFAULT_PERIOD_HOURS.items()
    ]


@shifts_router.get("", response_model=list[ShiftOut])
async def list_shifts(
    start: date = Query(),
    end: date = Query(),
    current_user: User = Depends(get_current_user),
    service: ShiftService = Depends(get_shift_service),
) -> list[ShiftOut]:
    try:
        return await service.list_between(current_user.id, start, end)
    except RangeTooLongError as exc:
        raise HTTPException(status_code=422, detail="Période invalide (62 jours au plus)") from exc


@shifts_router.post("", response_model=ShiftOut, status_code=status.HTTP_201_CREATED)
async def create_shift(
    body: ShiftIn,
    current_user: User = Depends(get_current_user),
    service: ShiftService = Depends(get_shift_service),
) -> ShiftOut:
    try:
        return await service.create(current_user.id, body)
    except SiteUnavailableError as exc:
        raise HTTPException(status_code=422, detail=_SITE_NOT_FOUND) from exc


@shifts_router.post("/series", response_model=list[ShiftOut], status_code=status.HTTP_201_CREATED)
async def create_shift_series(
    body: ShiftSeriesIn,
    current_user: User = Depends(get_current_user),
    service: ShiftService = Depends(get_shift_service),
) -> list[ShiftOut]:
    try:
        return await service.create_series(current_user.id, body)
    except SiteUnavailableError as exc:
        raise HTTPException(status_code=422, detail=_SITE_NOT_FOUND) from exc
    except RangeTooLongError as exc:
        raise HTTPException(status_code=422, detail="Période invalide (62 jours au plus)") from exc
    except EmptySeriesError as exc:
        raise HTTPException(status_code=422, detail="Aucun jour à l'horaire dans cette période") from exc


@shifts_router.put("/series/{series_id}", response_model=list[ShiftOut])
async def update_shift_series(
    series_id: int,
    body: ShiftSeriesUpdateIn,
    current_user: User = Depends(get_current_user),
    service: ShiftService = Depends(get_shift_service),
) -> list[ShiftOut]:
    try:
        shifts = await service.update_series(current_user.id, series_id, body)
    except SiteUnavailableError as exc:
        raise HTTPException(status_code=422, detail=_SITE_NOT_FOUND) from exc
    if shifts is None:
        raise HTTPException(status_code=404, detail=_SERIES_NOT_FOUND)
    return shifts


@shifts_router.delete("/series/{series_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shift_series(
    series_id: int,
    from_date: date | None = None,
    current_user: User = Depends(get_current_user),
    service: ShiftService = Depends(get_shift_service),
) -> None:
    """Every shift of the series, or those from `from_date` on."""
    if not await service.void_series(current_user.id, series_id, from_date):
        raise HTTPException(status_code=404, detail=_SERIES_NOT_FOUND)


@shifts_router.put("/{shift_id}", response_model=ShiftOut)
async def update_shift(
    shift_id: int,
    body: ShiftIn,
    current_user: User = Depends(get_current_user),
    service: ShiftService = Depends(get_shift_service),
) -> ShiftOut:
    try:
        shift = await service.update(current_user.id, shift_id, body)
    except SiteUnavailableError as exc:
        raise HTTPException(status_code=422, detail=_SITE_NOT_FOUND) from exc
    if shift is None:
        raise HTTPException(status_code=404, detail=_SHIFT_NOT_FOUND)
    return shift


@shifts_router.delete("/{shift_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shift(
    shift_id: int,
    current_user: User = Depends(get_current_user),
    service: ShiftService = Depends(get_shift_service),
) -> None:
    if not await service.void(current_user.id, shift_id):
        raise HTTPException(status_code=404, detail=_SHIFT_NOT_FOUND)
