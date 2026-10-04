"""Print the JWK Set for the Epic sandbox key — what the fhir.epic.com app's "Non-Production
JWK Set URL" must serve. From backend/, with EPIC_SANDBOX_PRIVATE_KEY_PATH set:

    uv run python scripts/epic_sandbox_jwks.py > jwks.json

Only the public half is printed; publishing it is safe. The key's `kid` (its RFC 7638
thumbprint) goes into EPIC_SANDBOX_KEY_ID, so every client assertion names the key Epic
should check it against."""

import base64
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from cryptography.hazmat.primitives import serialization  # noqa: E402
from jwt.algorithms import RSAAlgorithm  # noqa: E402

from app.config import settings  # noqa: E402


def thumbprint(jwk: dict) -> str:
    """RFC 7638: SHA-256 of the required members, sorted, no whitespace, base64url."""
    canonical = json.dumps({name: jwk[name] for name in ("e", "kty", "n")}, separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(hashlib.sha256(canonical.encode()).digest()).rstrip(b"=").decode()


def main() -> None:
    private_key = serialization.load_pem_private_key(
        settings.epic_sandbox_private_key_path.read_bytes(), password=None
    )
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    # PyJWT adds key_ops, which RFC 7517 says not to combine with `use`.
    jwk.pop("key_ops", None)
    jwk |= {"kid": thumbprint(jwk), "alg": "RS384", "use": "sig"}
    print(json.dumps({"keys": [jwk]}, indent=2))
    print(f"EPIC_SANDBOX_KEY_ID={jwk['kid']}", file=sys.stderr)


if __name__ == "__main__":
    main()
