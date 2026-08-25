from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_user
from app.billing.factory import get_billing_service
from app.billing.models import BillingRecordCreate, BillingRecordOut, BillingStatus
from app.billing.service import (
    BillingService,
    DuplicateBillingRecordError,
    EmptySelectionError,
    ExtractionRecordNotFoundError,
    PatientNotFoundError,
    RecordOnBillError,
    UnknownCodesError,
)
from app.postgresdb import User

router = APIRouter(prefix="/billing-records", tags=["billing"])


@router.post("", response_model=BillingRecordOut, status_code=status.HTTP_201_CREATED)
async def create_billing_record(
    body: BillingRecordCreate,
    confirm_duplicate: bool = False,
    current_user: User = Depends(get_current_user),
    service: BillingService = Depends(get_billing_service),
) -> BillingRecordOut:
    try:
        return await service.create(
            physician_id=current_user.id,
            patient_id=body.patient_id,
            service_date=body.service_date,
            billing_extraction_record_id=body.billing_extraction_record_id,
            summary_extraction_record_id=body.summary_extraction_record_id,
            selected_codes=body.selected_codes,
            source_system=body.source_system,
            confirm_duplicate=confirm_duplicate,
        )
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Patient introuvable") from exc
    except ExtractionRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Extraction introuvable") from exc
    except EmptySelectionError as exc:
        raise HTTPException(status_code=422, detail="Au moins un code doit être sélectionné") from exc
    except UnknownCodesError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Code(s) absent(s) de cette extraction : {', '.join(exc.codes)}",
        ) from exc
    except DuplicateBillingRecordError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "duplicate_billing_record", "message": exc.message},
        ) from exc


@router.get("", response_model=list[BillingRecordOut])
async def list_billing_records(
    patient_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status_filter: BillingStatus | None = Query(default=None, alias="status"),
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    service: BillingService = Depends(get_billing_service),
) -> list[BillingRecordOut]:
    return await service.list_for_physician(
        current_user.id,
        patient_id=patient_id,
        date_from=date_from,
        date_to=date_to,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_billing_record(
    record_id: int,
    current_user: User = Depends(get_current_user),
    service: BillingService = Depends(get_billing_service),
) -> None:
    try:
        deleted = await service.delete(record_id, current_user.id)
    except RecordOnBillError as exc:
        raise HTTPException(
            status_code=409,
            detail="Cette facturation fait partie d'une facture générée. Supprimez d'abord la facture.",
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Facture introuvable")
