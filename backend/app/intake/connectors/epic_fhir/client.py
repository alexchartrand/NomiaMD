"""Reads FHIR R4 resources from an Epic instance. Knows HTTP and FHIR's wire shapes (Bundles,
Binary), nothing about notes or NomiaMD: the mapper and reader build on it. The base URL
and token provider are injected, so the sandbox (step 11b) and the DSN (step 19) share it."""

import base64
from typing import Any

import httpx

from app.intake.connectors.epic_fhir.auth import AccessTokenProvider
from app.intake.connectors.epic_fhir.errors import EpicFhirError

Resource = dict[str, Any]

_FHIR_JSON = "application/fhir+json"
# A runaway `next` link chain stops here instead of looping forever.
_MAX_PAGES = 50


class EpicFhirClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str, tokens: AccessTokenProvider) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/") + "/"
        self._tokens = tokens

    async def token(self) -> str:
        """An access token, fetched now if needed — lets a caller check the credentials
        before its first real request."""
        return await self._tokens.token()

    async def read(self, resource_type: str, resource_id: str) -> Resource:
        return await self.read_reference(f"{resource_type}/{resource_id}")

    async def read_reference(self, reference: str) -> Resource:
        """A relative ("Encounter/abc") or absolute reference, as resources carry them."""
        response = await self._get(reference, accept=_FHIR_JSON)
        return response.json()

    async def search(self, resource_type: str, params: dict[str, str]) -> list[Resource]:
        """Every matching resource, across pages. Epic adds OperationOutcome entries (search
        mode "outcome") for warnings; those aren't matches and are left out."""
        matches: list[Resource] = []
        url: str | None = resource_type
        query: dict[str, str] | None = params
        for _ in range(_MAX_PAGES):
            if url is None:
                break
            bundle = (await self._get(url, accept=_FHIR_JSON, params=query)).json()
            matches += [
                entry["resource"]
                for entry in bundle.get("entry", [])
                if "resource" in entry and entry.get("search", {}).get("mode", "match") == "match"
            ]
            # The next link already carries the query.
            url, query = _next_link(bundle), None
        return matches

    async def binary_text(self, reference: str, content_type: str) -> str:
        """A Binary's content as text. Epic returns the raw document when the Accept header
        matches its type, and a FHIR Binary (base64 `data`) otherwise — both are handled."""
        response = await self._get(reference, accept=content_type)
        if "json" in response.headers.get("content-type", ""):
            payload = response.json()
            if payload.get("resourceType") == "Binary":
                return base64.b64decode(payload.get("data", "")).decode("utf-8")
        return response.text

    async def _get(self, url: str, accept: str, params: dict[str, str] | None = None) -> httpx.Response:
        absolute = httpx.URL(self._base_url).join(url)
        headers = {"Authorization": f"Bearer {await self._tokens.token()}", "Accept": accept}
        try:
            response = await self._http.get(absolute, params=params, headers=headers)
        except httpx.HTTPError as error:
            raise EpicFhirError(None, str(absolute), str(error)) from error
        if response.status_code != 200:
            raise EpicFhirError(response.status_code, str(absolute), response.text)
        return response


def _next_link(bundle: Resource) -> str | None:
    return next((link["url"] for link in bundle.get("link", []) if link.get("relation") == "next"), None)
