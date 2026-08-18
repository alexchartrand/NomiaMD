from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.dependencies import COOKIE_NAME, get_current_user
from app.auth.factory import get_auth_service
from app.auth.models import LoginRequest, UserOut
from app.config import settings
from app.postgresdb import User
from app.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, response: Response) -> User:
    result = await get_auth_service().login(body.email, body.password)
    if result is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token, user = result
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.jwt_expiry_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
