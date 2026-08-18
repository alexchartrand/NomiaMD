from fastapi import APIRouter, Depends, Request

from app.auth import get_current_user
from app.ramq_chatbot.factory import get_ramq_query_engine
from app.ramq_chatbot.models import RAMQQueryRequest, RAMQQueryResult
from app.rate_limit import limiter

router = APIRouter()


@router.post("/query", response_model=RAMQQueryResult, dependencies=[Depends(get_current_user)])
@limiter.limit("20/minute")
# Free-form, multi-turn billing question answered from the RAMQ manual, not tied to a specific
# transcript. POST a query + optional history; history is stateless (client resends prior turns).
async def query_ramq_manual(request: Request, body: RAMQQueryRequest) -> RAMQQueryResult:
    engine = get_ramq_query_engine()
    answer = await engine.acustom_query(body.query, chat_history=body.history)
    return RAMQQueryResult(answer=answer)
