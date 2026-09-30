from fastapi import HTTPException, Request, status

from app.auth.factory import build_auth_service
from app.postgresdb import User, session_scope

COOKIE_NAME = "nomiamd_session"


async def get_current_user(request: Request) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    # Its own short session, not the request's DbSession: every route depends on this, and
    # a lookup on the request session would keep a pooled connection checked out for the
    # whole handler — including /extract's multi-second LLM calls. The returned User is
    # detached but fully loaded (expire_on_commit=False, app/postgresdb/database.py).
    async with session_scope() as session:
        user = await build_auth_service(session).get_user_from_token(token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    return user
