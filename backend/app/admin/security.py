"""Admin authentication: password hashing and the route guard.

One shared admin password, stored hashed in ADMIN_PASSWORD_HASH (never in
code). Hashing is stdlib pbkdf2-hmac-sha256 so no crypto dependency is added.

The hash is emitted base64-encoded: its internal '$' separators would
otherwise be swallowed by Docker Compose's variable interpolation in .env,
silently corrupting the salt.

Generate a hash:
    docker compose exec backend python -m app.admin.security "your-password"
"""
import base64
import binascii
import hashlib
import hmac
import logging
import secrets
import sys

from fastapi import Depends, HTTPException, Request, status

from app.config import settings

logger = logging.getLogger(__name__)

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 480_000
SESSION_KEY = "admin"


def hash_password(password: str, *, salt: str | None = None) -> str:
    """-> base64 of 'pbkdf2_sha256$iterations$salt$hexdigest'.

    Base64 keeps '$' out of the env value (see module docstring).
    """
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _ITERATIONS
    ).hex()
    raw = f"{_ALGO}${_ITERATIONS}${salt}${digest}"
    return base64.b64encode(raw.encode()).decode()


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check against a stored hash. False on any malformed input."""
    try:
        raw = base64.b64decode(stored, validate=True).decode()
        algo, iterations, salt, digest = raw.split("$")
        if algo != _ALGO:
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), int(iterations)
        ).hex()
    except (ValueError, AttributeError, binascii.Error, UnicodeDecodeError):
        return False
    return hmac.compare_digest(expected, digest)


def require_admin(request: Request) -> None:
    """Dependency guarding every /api/admin route. 401 when not signed in."""
    if not request.session.get(SESSION_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin sign-in required"
        )


AdminRequired = Depends(require_admin)


if __name__ == "__main__":  # pragma: no cover - operator helper
    if len(sys.argv) != 2:
        print('usage: python -m app.admin.security "password"')
        raise SystemExit(2)
    print(hash_password(sys.argv[1]))
