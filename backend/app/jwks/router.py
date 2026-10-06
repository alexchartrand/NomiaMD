from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.jwks.keys import JwkSet

router = APIRouter(tags=["jwks"])

# Verifiers cache the set anyway; an hour keeps a rotation's new key visible the same day.
_CACHE_CONTROL = "public, max-age=3600"


def get_jwk_set(request: Request) -> JwkSet:
    return request.app.state.jwk_set


@router.get("/.well-known/jwks.json")
def jwks(jwk_set: JwkSet = Depends(get_jwk_set)) -> JSONResponse:
    """No login: public keys only, fetched by the EHRs we authenticate to."""
    return JSONResponse(jwk_set.as_dict(), headers={"Cache-Control": _CACHE_CONTROL})
