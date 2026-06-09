"""Password hashing — PBKDF2-HMAC-SHA256 with a PHC-style encoded string.

Stdlib only (hashlib + hmac), so no native build dependency on Windows.
Format: `pbkdf2_sha256$<iterations>$<b64 salt>$<b64 hash>` — self-describing,
so `verify_password` reads the iteration count and salt out of the stored
value and never needs the current setting to match what was used at hash
time.

Production upgrade path: swap to argon2id / bcrypt by changing the algo
tag and dispatching on it in verify_password. The PHC format makes that a
non-breaking migration — old pbkdf2 hashes keep verifying."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

from ..config import settings


_ALGO = "pbkdf2_sha256"


def hash_password(password: str, *, iterations: int | None = None) -> str:
    if not password:
        raise ValueError("password must not be empty")
    iters = iterations or settings.password_iterations
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
    return (
        f"{_ALGO}${iters}$"
        f"{base64.b64encode(salt).decode()}$"
        f"{base64.b64encode(dk).decode()}"
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not password or not encoded:
        return False
    try:
        algo, iters_s, b64salt, b64hash = encoded.split("$")
        if algo != _ALGO:
            return False
        salt = base64.b64decode(b64salt)
        expected = base64.b64decode(b64hash)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters_s))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False
