"""PKCE parameters for an authorization-code flow.

The public clients used here ship no secret -- their ids are the ones the
vendors' own CLIs use and are readable by anyone -- so proof of key exchange is
what stops an intercepted authorization code from being redeemed by someone
else. It is not optional hardening for this design; it is the only thing
binding the code to the process that asked for it.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass

#: 96 bytes, matching the reference client. RFC 7636 allows 32 to 96 octets
#: before encoding; the top of that range costs nothing here.
VERIFIER_BYTES = 96


def _b64url(raw: bytes) -> str:
    """base64url without padding, as RFC 7636 requires."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


@dataclass(frozen=True)
class Pkce:
    verifier: str
    challenge: str
    method: str = "S256"


def generate_pkce() -> Pkce:
    verifier = _b64url(secrets.token_bytes(VERIFIER_BYTES))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return Pkce(verifier=verifier, challenge=challenge)


def generate_state() -> str:
    """An unguessable value tying a callback back to the request that began it."""
    return _b64url(secrets.token_bytes(32))
