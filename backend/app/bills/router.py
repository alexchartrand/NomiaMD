from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth import get_current_user
from app.bills.factory import get_bill_service
from app.bills.models import BillCreate, BillDetailOut, BillOut
from app.bills.service import BillService, EmptySelectionError, StaleSelectionError
from app.postgresdb import User

router = APIRouter(prefix="/bills", tags=["bills"])


@router.post("", response_model=BillOut, status_code=status.HTTP_201_CREATED)
async def create_bill(
    body: BillCreate,
    current_user: User = Depends(get_current_user),
    service: BillService = Depends(get_bill_service),
) -> BillOut:
    try:
        return await service.create(
            physician_id=current_user.id,
            start_date=body.start_date,
            end_date=body.end_date,
            claim_ids=body.claim_ids,
        )
    except EmptySelectionError as exc:
        raise HTTPException(status_code=422, detail="Au moins une facturation doit être sélectionnée") from exc
    except StaleSelectionError as exc:
        raise HTTPException(
            status_code=409,
            detail="Certaines facturations ne sont plus disponibles pour cette facture.",
        ) from exc


@router.get("", response_model=list[BillOut])
async def list_bills(
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    service: BillService = Depends(get_bill_service),
) -> list[BillOut]:
    return await service.list_for_physician(current_user.id, limit=limit, offset=offset)


@router.get("/{bill_id}", response_model=BillDetailOut)
async def get_bill(
    bill_id: int,
    current_user: User = Depends(get_current_user),
    service: BillService = Depends(get_bill_service),
) -> BillDetailOut:
    bill = await service.get_for_physician(bill_id, current_user.id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    return bill


@router.get("/{bill_id}/pdf")
async def get_bill_pdf(
    bill_id: int,
    current_user: User = Depends(get_current_user),
    service: BillService = Depends(get_bill_service),
) -> Response:
    pdf_bytes = await service.render_pdf(bill_id, current_user.id)
    if pdf_bytes is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="facture-{bill_id:06d}.pdf"'},
    )


@router.delete("/{bill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bill(
    bill_id: int,
    current_user: User = Depends(get_current_user),
    service: BillService = Depends(get_bill_service),
) -> None:
    deleted = await service.delete(bill_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Facture introuvable")
