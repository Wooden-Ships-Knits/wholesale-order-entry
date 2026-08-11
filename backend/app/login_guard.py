"""Throttle repeated failed sign-ins on the admin and rep logins.

Both logins are a password against a known account, and /reps asks only for a
rep's first name — cheap to guess. Without a limit, an attacker gets
unlimited guesses — the rep passwords are short enough that a script would work
through the space in hours. This makes that attack take years and, more useful,
makes it loud in the logs long before it succeeds.

Two counters, either of which trips:

  * per client IP    — stops one machine grinding through every rep in turn
  * per identity     — stops a distributed attempt on ONE account, which the
                       IP counter cannot see. The identity is the rep's name,
                       or "admin" for the admin login.

The per-identity counter means someone can deliberately lock a rep out for a
few minutes by failing on their name. That is a nuisance rather than a breach,
and it is the price of defending the credential itself; the window expires on
its own and a successful sign-in clears it.

In-process, so like the reminder sweep in main.py this assumes ONE backend
replica. A second one would double the allowance — still bounded, but if the
app is ever scaled out this belongs in Postgres or Redis.
"""
import logging
import threading
import time

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

# Generous enough that nobody fat-fingering their password ever notices, tight
# enough that guessing a word-NN password (~10^6 combinations) is hopeless: 10
# tries per quarter hour is under 1000 a day from one address.
MAX_PER_IP = 10
MAX_PER_IDENTITY = 20
WINDOW_SECONDS = 15 * 60


def client_ip(request: Request) -> str:
    """Best-effort caller address.

    nginx proxies every request, so request.client.host is the proxy and would
    make all callers look like one. X-Forwarded-For's first entry is the
    original client. A caller can forge that header and so evade the per-IP
    counter — which is exactly why the per-identity counter exists and is not
    optional.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class LoginGuard:
    """Rolling-window failure counters. One instance per login route."""

    def __init__(
        self,
        name: str,
        *,
        max_per_ip: int = MAX_PER_IP,
        max_per_identity: int = MAX_PER_IDENTITY,
        window_seconds: int = WINDOW_SECONDS,
        clock=time.monotonic,
    ) -> None:
        self._name = name
        self._max_per_ip = max_per_ip
        self._max_per_identity = max_per_identity
        self._window = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        # key -> list of failure timestamps, pruned on touch
        self._failures: dict[tuple[str, str], list[float]] = {}

    def _recent(self, key: tuple[str, str], now: float) -> list[float]:
        kept = [t for t in self._failures.get(key, []) if now - t < self._window]
        if kept:
            self._failures[key] = kept
        else:
            self._failures.pop(key, None)
        return kept

    def check(self, ip: str, identity: str) -> None:
        """Raise 429 when either counter is over its limit. Call BEFORE
        verifying the password, so a locked-out caller learns nothing about
        whether the guess was right."""
        with self._lock:
            now = self._clock()
            for key, limit in ((("ip", ip), self._max_per_ip),
                               (("id", identity), self._max_per_identity)):
                recent = self._recent(key, now)
                if len(recent) >= limit:
                    retry_after = int(self._window - (now - min(recent))) + 1
                    logger.warning(
                        "%s login locked out (%s=%s, %d failures)",
                        self._name, key[0], key[1], len(recent),
                    )
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Too many failed sign-in attempts. Try again later.",
                        headers={"Retry-After": str(retry_after)},
                    )

    def record_failure(self, ip: str, identity: str) -> None:
        with self._lock:
            now = self._clock()
            for key in (("ip", ip), ("id", identity)):
                self._failures.setdefault(key, []).append(now)

    def record_success(self, ip: str, identity: str) -> None:
        """A correct password clears both counters — an honest user who finally
        remembers their password is not then locked out by the earlier tries."""
        with self._lock:
            self._failures.pop(("ip", ip), None)
            self._failures.pop(("id", identity), None)

    def reset(self) -> None:  # pragma: no cover - test helper
        with self._lock:
            self._failures.clear()
