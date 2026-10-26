from fastapi import Depends, HTTPException, Request, status

from app.auth.factory import build_auth_service
from app.postgresdb import User, UserRole, session_scope

COOKIE_NAME = "nomiamd_session"

PASSWORD_CHANGE_REQUIRED = "password_change_required"


async def get_authenticated_user(request: Request) -> User:
    """The logged-in user, whether or not they still owe a password change — only the few
    routes that let them make it (`/auth/me`, `/auth/me/password`) depend on this directly.
    Everything else goes through get_current_user."""
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


async def get_current_user(user: User = Depends(get_authenticated_user)) -> User:
    """The logged-in user, refused while they're on an admin-issued temporary password."""
    if user.must_change_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PASSWORD_CHANGE_REQUIRED)
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Réservé aux administrateurs")
    return user
