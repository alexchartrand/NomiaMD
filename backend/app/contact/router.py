from fastapi import APIRouter, BackgroundTasks, Depends, Request, status

from app.contact.factory import get_contact_notifier, get_contact_service
from app.contact.models import ContactRequestIn
from app.contact.notifier import ContactNotifier
from app.contact.service import ContactService
from app.rate_limit import limiter

router = APIRouter(prefix="/contact", tags=["contact"])


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/hour")
async def submit_contact_request(
    request: Request,
    body: ContactRequestIn,
    background_tasks: BackgroundTasks,
    service: ContactService = Depends(get_contact_service),
    notifier: ContactNotifier = Depends(get_contact_notifier),
) -> None:
    saved = await service.submit(body)
    if saved is not None:
        # Runs after the response — and so after DbSession committed the row.
        background_tasks.add_task(notifier.notify, saved.id, body)
