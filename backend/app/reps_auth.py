"""Rep sign-in: the roster, and one password hash per rep.

One password per rep, not one shared by all (revised 2026-08-10). The shared
password it replaced gave no identity at all: the login is a name dropdown, so
any rep could pick a colleague's name, type the one password everybody had, and
read that colleague's whole book. Per-rep hashes make the name meaningful — a
right password against the wrong name is simply a failed login.

Hashes live in REPS_PASSWORD_HASHES as a JSON object keyed by the rep's
normalized name:

    REPS_PASSWORD_HASHES={"avivalandin":"<hash>","denisearnett":"<hash>"}

Normalized keys keep spaces out of the .env value and make the lookup immune to
spacing and case differences between the roster and whatever the browser sends.
The hashes themselves are the same pbkdf2-sha256-in-base64 as the admin one
(app.admin.security) — base64 so their internal '$' cannot be eaten by Docker
Compose's variable interpolation.

Generate the value (note the leading space, which keeps the plaintext out of
your shell history if HISTCONTROL includes ignorespace):

     docker compose exec backend python -m app.reps_auth "Aviva Landin=harbor-42" ...
"""
import json
import logging
import re
import sys

from app.admin.security import hash_password, verify_password

logger = logging.getLogger(__name__)

# Who may sign in. A constant rather than the region/rep sheet because this is a
# security boundary — only these names get a session — and the sheet's Email tab
# also carries rows that are not reps. Adding a rep means a line here AND an
# entry in REPS_PASSWORD_HASHES; a name in one but not the other cannot sign in.
# The name must also match the sheet's Name column (column C) or their orders
# won't resolve (test_reps_portal asserts every name maps to an address).
REP_NAMES = (
    "Aviva Landin",
    "Denise Arnett",
    "Jason Hilsenrad",
    "Kitty Tally",
    "Michael Young",
    "Rande Cohen",
    "Vickie Wilde",
)


def normalize_name(value: str | None) -> str:
    """Lookup key for a rep name: spacing and case need not agree."""
    return re.sub(r"\s+", "", value or "").lower()


def load_hashes(raw: str) -> dict[str, str]:
    """Parse REPS_PASSWORD_HASHES. {} on anything malformed.

    Deliberately never raises: a typo in this one value would otherwise take the
    whole app down — order form included — over a setting only /reps reads.
    Failing to an empty map disables rep sign-in and nothing else.
    """
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        logger.error("REPS_PASSWORD_HASHES is not valid JSON — rep sign-in is disabled")
        return {}
    if not isinstance(parsed, dict):
        logger.error("REPS_PASSWORD_HASHES must be a JSON object — rep sign-in is disabled")
        return {}
    return {normalize_name(k): v for k, v in parsed.items() if isinstance(v, str)}


def verify_rep(name: str, password: str, raw_hashes: str) -> bool:
    """Is this the password for THIS rep? False for an unknown name.

    The name must be on the roster as well as in the hash map: a stale entry
    left in the env value must not outlive its removal from REP_NAMES.
    """
    if name not in REP_NAMES:
        return False
    stored = load_hashes(raw_hashes).get(normalize_name(name))
    if not stored:
        return False
    return verify_password(password, stored)


if __name__ == "__main__":  # pragma: no cover - operator helper
    # Usage: python -m app.reps_auth "Aviva Landin=harbor-42" "Denise Arnett=copper-73"
    # Prints the REPS_PASSWORD_HASHES line. Passwords are never stored anywhere
    # but the hash — they cannot be recovered from it, only reset.
    pairs: dict[str, str] = {}
    for arg in sys.argv[1:]:
        if "=" not in arg:
            print(f'bad argument {arg!r} — expected "Rep Name=password"')
            raise SystemExit(2)
        name, password = arg.split("=", 1)
        name = name.strip()
        if name not in REP_NAMES:
            print(f"{name!r} is not in REP_NAMES — add it there first")
            raise SystemExit(2)
        pairs[normalize_name(name)] = hash_password(password)

    if not pairs:
        print('usage: python -m app.reps_auth "Rep Name=password" ...')
        raise SystemExit(2)

    missing = [n for n in REP_NAMES if normalize_name(n) not in pairs]
    if missing:
        # Not fatal: rotating one rep is a legitimate single-pair run. But the
        # output is the WHOLE value, so a partial run would lock the others out.
        print(f"# WARNING — no password given for: {', '.join(missing)}")
        print("# This line replaces the whole value; those reps will not be able to sign in.")
    print("REPS_PASSWORD_HASHES=" + json.dumps(pairs, separators=(",", ":")))
