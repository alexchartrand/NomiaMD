"""GET /.well-known/jwks.json: the public half of every key we sign client assertions with
(Epic's backend services today), which an EHR's app registration points its JWK Set URL at.
The keys are the PEM files committed in public_keys/, loaded once at startup.

Public interface — everything else that needs this imports it from here rather than
reaching into .keys/.router directly."""

from app.jwks.keys import DEFAULT_PUBLIC_KEYS_DIR, InvalidPublicKeyError, JwkSet, PublicJwk
from app.jwks.router import get_jwk_set
from app.jwks.router import router as jwks_router

__all__ = ["DEFAULT_PUBLIC_KEYS_DIR", "InvalidPublicKeyError", "JwkSet", "PublicJwk", "get_jwk_set", "jwks_router"]
