"""AES-256-GCM for the transient admin-copy order PDF (CLAUDE.md rule 1).

The admin copy is the only artefact that shows a full card number, and it exists
only until the monitoring team has keyed the card into Salesforce. It is held
encrypted in the database, never written to disk and never emailed.

The key comes from CARD_ENCRYPTION_KEY and must NOT live in the database —
ciphertext stored beside its own key protects nothing. GCM is authenticated, so
a tampered blob raises rather than decrypting to garbage.
"""
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

# 96-bit nonce is the GCM standard; generated fresh per encryption and stored
# in front of the ciphertext (it is not secret, only unique).
_NONCE_BYTES = 12
_KEY_BYTES = 32  # AES-256


class CardCryptoUnavailable(RuntimeError):
    """No usable CARD_ENCRYPTION_KEY — callers skip keeping the admin copy."""


def _key() -> bytes:
    raw = (settings.card_encryption_key or "").strip()
    if not raw:
        raise CardCryptoUnavailable("CARD_ENCRYPTION_KEY is not set")
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise CardCryptoUnavailable("CARD_ENCRYPTION_KEY is not valid base64") from exc
    if len(key) != _KEY_BYTES:
        raise CardCryptoUnavailable(
            f"CARD_ENCRYPTION_KEY must decode to {_KEY_BYTES} bytes, got {len(key)}"
        )
    return key


def configured() -> bool:
    """True when a usable key is present. Checked before rendering an admin copy
    so a missing key degrades to 'no card kept' instead of failing the order."""
    try:
        _key()
    except CardCryptoUnavailable:
        return False
    return True


def encrypt(data: bytes) -> bytes:
    nonce = os.urandom(_NONCE_BYTES)
    return nonce + AESGCM(_key()).encrypt(nonce, data, None)


def decrypt(blob: bytes) -> bytes:
    return AESGCM(_key()).decrypt(blob[:_NONCE_BYTES], blob[_NONCE_BYTES:], None)
