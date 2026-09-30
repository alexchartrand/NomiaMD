from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.dependencies import COOKIE_NAME, get_current_user
from app.auth.factory import get_auth_service, get_profile_service
from app.auth.profile import PracticeFacts, ProfileService
from app.auth.service import AuthService
from app.auth.models import LoginRequest, PasswordChangeRequest, ProfileUpdateRequest, UserOut
from app.config import settings
from app.postgresdb import User
from app.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
    profiles: ProfileService = Depends(get_profile_service),
) -> UserOut:
    result = await auth.login(body.email, body.password, body.remember_me)
    if result is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token, user, max_age = result
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return UserOut.from_account(await profiles.current(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME)


@router.get("/me", response_model=UserOut)
async def me(
    current_user: User = Depends(get_current_user),
    profiles: ProfileService = Depends(get_profile_service),
) -> UserOut:
    # get_current_user deliberately doesn't load the profile — every authenticated
    # request pays for that dependency, and only this screen needs the practice facts.
    return UserOut.from_account(await profiles.current(current_user))


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    profiles: ProfileService = Depends(get_profile_service),
) -> UserOut:
    # One transaction for both halves (users + physician_profiles): a failure in either
    # rolls back the other, see app/postgresdb/dependencies.py.
    account = await profiles.update(
        current_user,
        full_name=body.full_name,
        practice_number=body.practice_number,
        facts=PracticeFacts(
            physician_type=body.physician_type.value if body.physician_type else None,
            number_of_patients=body.number_of_patients,
            remuneration_type=body.remuneration_type.value if body.remuneration_type else None,
        ),
    )
    return UserOut.from_account(account)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def change_password(
    request: Request,
    body: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> None:
    changed = await auth.change_password(
        current_user, current_password=body.current_password, new_password=body.new_password
    )
    if not changed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mot de passe actuel invalide")
