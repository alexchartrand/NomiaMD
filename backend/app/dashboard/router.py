from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.dashboard.factory import get_dashboard_service
from app.dashboard.models import DashboardOut
from app.dashboard.service import DashboardService
from app.postgresdb import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardOut:
    return await service.for_physician(current_user.id)
