from fastapi import APIRouter, Depends, Request

from app.auth import get_current_user
from app.llm.usage import usage_scope
from app.postgresdb import LLMCallOwner, LLMCallRepository, User, session_scope
from app.ramq_chatbot.factory import get_ramq_query_engine
from app.ramq_chatbot.models import RAMQQueryRequest, RAMQQueryResult
from app.rate_limit import limiter

router = APIRouter()


@router.post("/query", response_model=RAMQQueryResult)
@limiter.limit("20/minute")
# Free-form, multi-turn billing question answered from the RAMQ manual, not tied to a specific
# transcript. POST a query + optional history; history is stateless (client resends prior turns).
async def query_ramq_manual(
    request: Request, body: RAMQQueryRequest, current_user: User = Depends(get_current_user)
) -> RAMQQueryResult:
    engine = get_ramq_query_engine()
    with usage_scope() as usage:
        try:
            answer = await engine.aquery(body.query, chat_history=body.history)
        finally:
            # Its own short session after the LLM calls, like /extract's (no pooled connection
            # held across them).
            async with session_scope() as session:
                await LLMCallRepository(session).add_many(usage.records, LLMCallOwner(user_id=current_user.id))
    return RAMQQueryResult(answer=answer)
