from fastapi import HTTPException, Request, status

from app.auth.factory import get_auth_service
from app.postgresdb import User

COOKIE_NAME = "nomiamd_session"


async def get_current_user(request: Request) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = await get_auth_service().get_user_from_token(token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    return user
