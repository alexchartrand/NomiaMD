"""Login-session authentication: manually-provisioned accounts (see
scripts/create_user.py — no signup path), a JWT stored in an httpOnly cookie, and a
FastAPI dependency other routes gate on.

Public interface — everything else that needs this imports it from here rather than
reaching into .service/.security/.factory/.dependencies directly."""

from app.auth.dependencies import get_authenticated_user, get_current_user, require_admin
from app.auth.models import LoginRequest, UserOut
from app.auth.router import router as auth_router

__all__ = ["get_authenticated_user", "get_current_user", "require_admin", "LoginRequest", "UserOut", "auth_router"]
