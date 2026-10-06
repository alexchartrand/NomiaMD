"""GET /.well-known/jwks.json and the JWK Set behind it: what Epic checks our signed client
assertions against. Keys are generated per test; only the route test reads the committed
public_keys/ directory, so a bad committed file fails CI rather than the next deploy."""

from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient

from app.config import settings
from app.intake.connectors.epic_fhir.factory import sandbox_client
from app.jwks import DEFAULT_PUBLIC_KEYS_DIR, InvalidPublicKeyError, JwkSet, PublicJwk
from app.main import app

TOKEN_URL = "https://fhir.example.test/oauth2/token"


def _rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _private_pem(key) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )


def _public_pem(key) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def _write(directory: Path, name: str, content: bytes) -> None:
    (directory / name).write_bytes(content)


# --- PublicJwk --------------------------------------------------------------------------


def test_kid_is_the_rfc_7638_thumbprint():
    # RFC 7638 section 3.1's worked example.
    jwk = PublicJwk(
        n=(
            "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjB"
            "ZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8"
            "KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_x"
            "BniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw"
        ),
        e="AQAB",
    )

    assert jwk.kid == "NzbLsXh8uDCcd-6MNwXF4W_7noWXFZAfHkxZsRGC9Xs"


def test_the_signer_and_the_set_derive_the_same_kid():
    key = _rsa_key()

    assert PublicJwk.from_private_pem(_private_pem(key)).kid == PublicJwk.from_public_pem(_public_pem(key)).kid


def test_a_published_jwk_carries_only_public_members():
    jwk = PublicJwk.from_public_pem(_public_pem(_rsa_key())).as_dict()

    assert set(jwk) == {"kty", "n", "e", "kid", "alg", "use"}
    assert (jwk["kty"], jwk["alg"], jwk["use"]) == ("RSA", "RS384", "sig")


# --- JwkSet -----------------------------------------------------------------------------


def test_the_set_lists_every_key_in_the_directory_for_rotation(tmp_path):
    old, new = _rsa_key(), _rsa_key()
    _write(tmp_path, "old.pem", _public_pem(old))
    _write(tmp_path, "new.pem", _public_pem(new))
    _write(tmp_path, "README.md", b"not a key, not read")

    jwk_set = JwkSet.from_directory(tmp_path)

    expected = {PublicJwk.from_public_pem(_public_pem(key)).kid for key in (old, new)}
    assert set(jwk_set.kids) == expected
    assert [jwk["kid"] for jwk in jwk_set.as_dict()["keys"]] == jwk_set.kids


def test_an_empty_directory_publishes_an_empty_set(tmp_path):
    assert JwkSet.from_directory(tmp_path).as_dict() == {"keys": []}


def test_a_private_key_in_the_directory_is_refused(tmp_path):
    _write(tmp_path, "oops.pem", _private_pem(_rsa_key()))

    with pytest.raises(InvalidPublicKeyError, match="oops.pem"):
        JwkSet.from_directory(tmp_path)


def test_a_non_rsa_key_is_refused(tmp_path):
    _write(tmp_path, "ec.pem", _public_pem(ec.generate_private_key(ec.SECP384R1())))

    with pytest.raises(InvalidPublicKeyError, match="only RSA"):
        JwkSet.from_directory(tmp_path)


def test_the_same_key_twice_is_refused(tmp_path):
    key = _rsa_key()
    _write(tmp_path, "a.pem", _public_pem(key))
    _write(tmp_path, "b.pem", _public_pem(key))

    with pytest.raises(InvalidPublicKeyError, match="listed twice"):
        JwkSet.from_directory(tmp_path)


def test_the_committed_keys_load():
    assert JwkSet.from_directory(DEFAULT_PUBLIC_KEYS_DIR).kids


# --- The route --------------------------------------------------------------------------


def test_the_route_serves_the_committed_set_without_login():
    with TestClient(app) as client:
        response = client.get("/.well-known/jwks.json")

    assert response.status_code == 200
    assert response.json() == JwkSet.from_directory(DEFAULT_PUBLIC_KEYS_DIR).as_dict()
    assert response.headers["cache-control"] == "public, max-age=3600"


# --- The Epic sandbox signer ------------------------------------------------------------


async def test_the_sandbox_signs_with_the_kid_the_set_lists(monkeypatch, tmp_path):
    key = _rsa_key()
    _write(tmp_path, "privatekey.pem", _private_pem(key))
    published = tmp_path / "public_keys"
    published.mkdir()
    _write(published, "epic-sandbox.pem", _public_pem(key))
    monkeypatch.setenv("EPIC_SANDBOX_CLIENT_ID", "client-123")
    monkeypatch.setenv("EPIC_SANDBOX_PRIVATE_KEY_PATH", str(tmp_path / "privatekey.pem"))
    monkeypatch.setenv("EPIC_SANDBOX_TOKEN_URL", TOKEN_URL)
    assertions: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assertions.append(dict(httpx.QueryParams(request.content.decode()))["client_assertion"])
        return httpx.Response(200, json={"access_token": "token-1", "expires_in": 3600})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await sandbox_client(http, settings).token()

    assert jwt.get_unverified_header(assertions[0])["kid"] == JwkSet.from_directory(published).kids[0]
