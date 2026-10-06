"""The public keys we sign client assertions with, as a JWK Set (RFC 7517). An EHR that
authenticates us by JWT (Epic's backend services, later its SMART launch) fetches this set
from the URL registered with its app and checks each assertion against the key its `kid`
names.

Only public PEM files are read: the server that publishes the set never needs the private
half. Each key's `kid` is its RFC 7638 thumbprint, so whoever signs with the private key
derives the same `kid` from it (`PublicJwk.from_private_pem`) without any shared config."""

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jwt.algorithms import RSAAlgorithm

# The committed public keys: `*.pem` here is what GET /.well-known/jwks.json publishes. To
# rotate, add the new key's file, deploy, register nothing (the URL stays the same), switch
# the signer to the new private key, then remove the old file.
DEFAULT_PUBLIC_KEYS_DIR = Path(__file__).with_name("public_keys")

# Epic accepts RS384 (and ES384); every key here signs RS384 assertions.
_ALGORITHM = "RS384"


class InvalidPublicKeyError(ValueError):
    pass


@dataclass(frozen=True)
class PublicJwk:
    """One RSA public key in JWK form, identified by its thumbprint."""

    n: str
    e: str

    @classmethod
    def from_public_pem(cls, pem: bytes) -> "PublicJwk":
        try:
            key = serialization.load_pem_public_key(pem)
        except ValueError as exc:
            raise InvalidPublicKeyError("not a PEM public key (a private key must never be published)") from exc
        return cls._from_key(key)

    @classmethod
    def from_private_pem(cls, pem: bytes) -> "PublicJwk":
        """The public half of a signing key — what the signer reads its `kid` from."""
        return cls._from_key(serialization.load_pem_private_key(pem, password=None).public_key())

    @classmethod
    def _from_key(cls, key: object) -> "PublicJwk":
        if not isinstance(key, RSAPublicKey):
            raise InvalidPublicKeyError(f"only RSA keys are supported, got {type(key).__name__}")
        jwk = RSAAlgorithm.to_jwk(key, as_dict=True)
        return cls(n=jwk["n"], e=jwk["e"])

    @property
    def kid(self) -> str:
        """RFC 7638: SHA-256 of the required members, sorted, no whitespace, base64url."""
        canonical = json.dumps({"e": self.e, "kty": "RSA", "n": self.n}, separators=(",", ":"), sort_keys=True)
        return base64.urlsafe_b64encode(hashlib.sha256(canonical.encode()).digest()).rstrip(b"=").decode()

    def as_dict(self) -> dict[str, str]:
        # No key_ops: RFC 7517 says not to combine it with `use`.
        return {"kty": "RSA", "n": self.n, "e": self.e, "kid": self.kid, "alg": _ALGORITHM, "use": "sig"}


class JwkSet:
    """Every key currently published. Two at once is how a key is rotated without downtime:
    the verifier accepts assertions signed by either while the signer switches over."""

    def __init__(self, keys: list[PublicJwk]) -> None:
        kids = [key.kid for key in keys]
        duplicates = sorted({kid for kid in kids if kids.count(kid) > 1})
        if duplicates:
            raise InvalidPublicKeyError(f"the same key is listed twice: {', '.join(duplicates)}")
        self._keys = sorted(keys, key=lambda key: key.kid)

    @classmethod
    def from_directory(cls, directory: Path = DEFAULT_PUBLIC_KEYS_DIR) -> "JwkSet":
        """Fails the boot on any unreadable or private key rather than serving a partial set."""
        keys = []
        for path in sorted(directory.glob("*.pem")):
            try:
                keys.append(PublicJwk.from_public_pem(path.read_bytes()))
            except InvalidPublicKeyError as exc:
                raise InvalidPublicKeyError(f"{path}: {exc}") from exc
        return cls(keys)

    @property
    def kids(self) -> list[str]:
        return [key.kid for key in self._keys]

    def as_dict(self) -> dict[str, list[dict[str, str]]]:
        return {"keys": [key.as_dict() for key in self._keys]}
