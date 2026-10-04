"""Access tokens for Epic's FHIR API. Backend services (SMART "Backend OAuth 2.0"): the
server signs a short JWT with its private key and trades it for an access token — no user
in the loop, which is what a server-side import needs. Step 19 adds a per-user SMART launch
provider behind the same AccessTokenProvider interface."""

import time
import uuid
from collections.abc import Callable
from typing import Protocol

import httpx
import jwt

from app.intake.connectors.epic_fhir.errors import EpicFhirError

_CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
# Epic rejects an assertion whose exp is more than 5 minutes after iat.
_ASSERTION_LIFETIME_SECONDS = 240
# A token this close to expiry is renewed rather than sent: a long import outlives it.
_RENEW_MARGIN_SECONDS = 60


class AccessTokenProvider(Protocol):
    async def token(self) -> str: ...


class BackendServicesTokenProvider:
    def __init__(
        self,
        http: httpx.AsyncClient,
        token_url: str,
        client_id: str,
        private_key_pem: str,
        key_id: str | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._http = http
        self._token_url = token_url
        self._client_id = client_id
        self._private_key_pem = private_key_pem
        self._key_id = key_id
        self._now = now
        self._token: str | None = None
        self._expires_at = 0.0

    async def token(self) -> str:
        if self._token is None or self._now() >= self._expires_at - _RENEW_MARGIN_SECONDS:
            await self._renew()
        assert self._token is not None
        return self._token

    async def _renew(self) -> None:
        issued_at = self._now()
        response = await self._http.post(
            self._token_url,
            data={
                "grant_type": "client_credentials",
                "client_assertion_type": _CLIENT_ASSERTION_TYPE,
                "client_assertion": self.client_assertion(issued_at),
            },
        )
        if response.status_code != 200:
            raise EpicFhirError(response.status_code, self._token_url, response.text)
        body = response.json()
        self._token = body["access_token"]
        self._expires_at = issued_at + int(body.get("expires_in", 300))

    def client_assertion(self, issued_at: float) -> str:
        """The signed JWT proving we hold the key registered with the client id."""
        claims = {
            "iss": self._client_id,
            "sub": self._client_id,
            "aud": self._token_url,
            "jti": uuid.uuid4().hex,
            "iat": int(issued_at),
            "nbf": int(issued_at),
            "exp": int(issued_at) + _ASSERTION_LIFETIME_SECONDS,
        }
        headers = {"kid": self._key_id} if self._key_id else None
        return jwt.encode(claims, self._private_key_pem, algorithm="RS384", headers=headers)
