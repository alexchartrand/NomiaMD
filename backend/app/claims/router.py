from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_user
from app.claims.factory import get_claim_service, get_manual_claim_service
from app.claims.manual import ManualClaimService
from app.claims.models import ClaimCreate, ClaimOut, ManualClaimCreate
from app.claims.errors import (
    ClaimEncounterMismatchError,
    ClaimNotFoundError,
    ClaimOnBillError,
    DuplicateClaimError,
    DuplicateEncounterClaimError,
    EmptySelectionError,
    ExtractionRunNotFoundError,
    IneligibleOrUnknownCodesError,
    InvalidFeeSelectionError,
    InvalidLieuSelectionError,
    PatientNotFoundError,
)
from app.claims.service import ClaimService
from app.claims.status import ClaimStatus
from app.postgresdb import User

router = APIRouter(prefix="/claims", tags=["claims"])


@router.post("", response_model=ClaimOut, status_code=status.HTTP_201_CREATED)
async def create_claim(
    body: ClaimCreate,
    confirm_duplicate: bool = False,
    current_user: User = Depends(get_current_user),
    service: ClaimService = Depends(get_claim_service),
) -> ClaimOut:
    with _claim_errors():
        return await service.create(
            physician=current_user,
            extraction_run_id=body.extraction_run_id,
            service_date=body.service_date,
            selected_codes=body.selected_codes,
            confirm_duplicate=confirm_duplicate,
        )


@router.put("/{claim_id}", response_model=ClaimOut)
async def replace_claim(
    claim_id: int,
    body: ClaimCreate,
    confirm_duplicate: bool = False,
    current_user: User = Depends(get_current_user),
    service: ClaimService = Depends(get_claim_service),
) -> ClaimOut:
    """A changed review of a draft: voids it and returns the claim saved in its place."""
    with _claim_errors(), _replace_errors("Cette extraction ne provient pas de la même rencontre"):
        return await service.replace(
            claim_id=claim_id,
            physician=current_user,
            extraction_run_id=body.extraction_run_id,
            service_date=body.service_date,
            selected_codes=body.selected_codes,
            confirm_duplicate=confirm_duplicate,
        )


@router.post("/manual", response_model=ClaimOut, status_code=status.HTTP_201_CREATED)
async def create_manual_claim(
    body: ManualClaimCreate,
    current_user: User = Depends(get_current_user),
    service: ManualClaimService = Depends(get_manual_claim_service),
) -> ClaimOut:
    """A claim billed without an encounter (no note): patient, date and codes picked by hand."""
    with _claim_errors():
        return await service.create(
            physician=current_user,
            patient_id=body.patient_id,
            service_date=body.service_date,
            selected_codes=body.selected_codes,
        )


@router.put("/manual/{claim_id}", response_model=ClaimOut)
async def replace_manual_claim(
    claim_id: int,
    body: ManualClaimCreate,
    current_user: User = Depends(get_current_user),
    service: ManualClaimService = Depends(get_manual_claim_service),
) -> ClaimOut:
    """A changed draft billed without an encounter: voids it and returns the claim saved in
    its place."""
    with _claim_errors(), _replace_errors("Cette facturation provient d'une rencontre"):
        return await service.replace(
            claim_id=claim_id,
            physician=current_user,
            patient_id=body.patient_id,
            service_date=body.service_date,
            selected_codes=body.selected_codes,
        )


@contextmanager
def _replace_errors(mismatch_detail: str) -> Iterator[None]:
    """What replacing a draft can be refused for, on top of _claim_errors."""
    try:
        yield
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Facturation introuvable") from exc
    except ClaimOnBillError as exc:
        raise HTTPException(
            status_code=409,
            detail="Cette facturation fait partie d'une facture générée. Supprimez d'abord la facture.",
        ) from exc
    except ClaimEncounterMismatchError as exc:
        raise HTTPException(status_code=422, detail=mismatch_detail) from exc


@contextmanager
def _claim_errors() -> Iterator[None]:
    """What saving a claim can be refused for, shared by create and replace."""
    try:
        yield
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Patient introuvable") from exc
    except ExtractionRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Extraction introuvable") from exc
    except EmptySelectionError as exc:
        raise HTTPException(status_code=422, detail="Au moins un code doit être sélectionné") from exc
    except IneligibleOrUnknownCodesError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Code(s) inexistant(s) ou non admissible(s) pour ce patient : {', '.join(exc.codes)}",
        ) from exc
    except InvalidFeeSelectionError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Choix de tarif invalide pour le code {exc.code} "
                f"(indice {exc.fee_index}, {exc.available} tarif(s) disponible(s))"
            ),
        ) from exc
    except InvalidLieuSelectionError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Lieu invalide pour le code {exc.code} : {exc.lieu}",
        ) from exc
    except DuplicateClaimError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "duplicate_claim", "message": exc.message},
        ) from exc
    except DuplicateEncounterClaimError as exc:
        raise HTTPException(
            status_code=409, detail="Cette rencontre a été marquée comme doublon d'une autre visite"
        ) from exc


@router.get("", response_model=list[ClaimOut])
async def list_claims(
    patient_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status_filter: ClaimStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    service: ClaimService = Depends(get_claim_service),
) -> list[ClaimOut]:
    return await service.list_for_physician(
        current_user.id,
        patient_id=patient_id,
        date_from=date_from,
        date_to=date_to,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/{claim_id}", response_model=ClaimOut)
async def get_claim(
    claim_id: int,
    current_user: User = Depends(get_current_user),
    service: ClaimService = Depends(get_claim_service),
) -> ClaimOut:
    claim = await service.get(claim_id, current_user.id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Facturation introuvable")
    return claim


@router.delete("/{claim_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_claim(
    claim_id: int,
    current_user: User = Depends(get_current_user),
    service: ClaimService = Depends(get_claim_service),
) -> None:
    try:
        # A void, not a hard delete — see the Claim model.
        deleted = await service.void(claim_id, current_user.id)
    except ClaimOnBillError as exc:
        raise HTTPException(
            status_code=409,
            detail="Cette facturation fait partie d'une facture générée. Supprimez d'abord la facture.",
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Facturation introuvable")
