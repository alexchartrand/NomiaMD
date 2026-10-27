from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.claims.status import ClaimStatus
from app.postgresdb import User
from app.shift_claims.errors import (
    EmptyShiftClaimError,
    HoursExceedShiftError,
    ShiftClaimConflictError,
    ShiftClaimNotFoundError,
    ShiftClaimOnBillError,
    ShiftNotFoundError,
    UnknownShiftCodeError,
    WholeQuartsOnlyError,
)
from app.shift_claims.catalog import GardeOption
from app.shift_claims.factory import get_shift_claim_service
from app.shift_claims.models import ShiftBillingOut, ShiftClaimIn, ShiftClaimOut
from app.shift_claims.service import ShiftClaimService

shift_billing_router = APIRouter(prefix="/shifts", tags=["shift-claims"])
shift_claims_router = APIRouter(prefix="/shift-claims", tags=["shift-claims"])

_SHIFT_NOT_FOUND = "Quart introuvable"
_ON_BILL = "Cette réclamation de quart est sur une facture : annulez d'abord la facture."


@shift_billing_router.get("/{shift_id}/billing", response_model=ShiftBillingOut)
async def get_shift_billing(
    shift_id: int,
    garde_option: GardeOption | None = None,
    current_user: User = Depends(get_current_user),
    service: ShiftClaimService = Depends(get_shift_claim_service),
) -> ShiftBillingOut:
    """The shift, the codes its rules suggest under `garde_option` (default: its claim's, else
    à l'acte), the others its care setting and that option allow, its claim."""
    try:
        return await service.billing(current_user.id, shift_id, garde_option)
    except ShiftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_SHIFT_NOT_FOUND) from exc


@shift_billing_router.put("/{shift_id}/claim", response_model=ShiftClaimOut)
async def save_shift_claim(
    shift_id: int,
    body: ShiftClaimIn,
    current_user: User = Depends(get_current_user),
    service: ShiftClaimService = Depends(get_shift_claim_service),
) -> ShiftClaimOut:
    """Creates the shift's claim, or replaces its draft."""
    try:
        return await service.save(current_user.id, shift_id, body)
    except ShiftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_SHIFT_NOT_FOUND) from exc
    except ShiftClaimOnBillError as exc:
        raise HTTPException(status_code=409, detail=_ON_BILL) from exc
    except ShiftClaimConflictError as exc:
        raise HTTPException(status_code=409, detail="Ce quart a été réclamé entre-temps.") from exc
    except EmptyShiftClaimError as exc:
        raise HTTPException(status_code=422, detail="Au moins un code doit être sélectionné") from exc
    except UnknownShiftCodeError as exc:
        raise HTTPException(status_code=422, detail=f"Code {exc.code} non applicable à ce quart") from exc
    except WholeQuartsOnlyError as exc:
        raise HTTPException(
            status_code=422, detail=f"Code {exc.code} : par période complète de {exc.quart_hours} h seulement"
        ) from exc
    except HoursExceedShiftError as exc:
        raise HTTPException(
            status_code=422, detail=f"Code {exc.code} : {exc.hours} h dépasse la durée du quart ({exc.shift_hours} h)"
        ) from exc


@shift_claims_router.get("", response_model=list[ShiftClaimOut])
async def list_shift_claims(
    date_from: date | None = None,
    date_to: date | None = None,
    status: ClaimStatus | None = None,
    current_user: User = Depends(get_current_user),
    service: ShiftClaimService = Depends(get_shift_claim_service),
) -> list[ShiftClaimOut]:
    return await service.list_for_physician(current_user.id, date_from=date_from, date_to=date_to, status=status)


@shift_claims_router.delete("/{claim_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shift_claim(
    claim_id: int,
    current_user: User = Depends(get_current_user),
    service: ShiftClaimService = Depends(get_shift_claim_service),
) -> None:
    try:
        await service.void(current_user.id, claim_id)
    except ShiftClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Réclamation de quart introuvable") from exc
    except ShiftClaimOnBillError as exc:
        raise HTTPException(status_code=409, detail=_ON_BILL) from exc
