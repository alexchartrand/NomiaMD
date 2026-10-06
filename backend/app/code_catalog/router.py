from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.code_catalog.factory import get_code_catalog_service
from app.code_catalog.models import CodeDetail, CodeHit
from app.code_catalog.service import CodeCatalogService, CodeNotFoundError
from app.postgresdb import User

router = APIRouter(prefix="/codes", tags=["codes"])


@router.get("/search", response_model=list[CodeHit])
async def search_codes(
    q: str | None = Query(default=None, max_length=200),
    # With a patient, only the codes that patient may be billed on service_date (today when
    # omitted) are returned.
    patient_id: int | None = None,
    service_date: date | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    service: CodeCatalogService = Depends(get_code_catalog_service),
) -> list[CodeHit]:
    return await service.search(
        physician=current_user, q=q, patient_id=patient_id, service_date=service_date, limit=limit
    )


@router.get("/{number}", response_model=CodeDetail)
async def get_code(
    number: str,
    current_user: User = Depends(get_current_user),
    service: CodeCatalogService = Depends(get_code_catalog_service),
) -> CodeDetail:
    try:
        return await service.get(number)
    except CodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Code {number} introuvable") from exc
