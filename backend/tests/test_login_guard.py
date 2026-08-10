"""Failed-sign-in throttle (app/login_guard.py)."""
import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers

from app.login_guard import LoginGuard, client_ip


class _Clock:
    """Manual clock — the window is 15 minutes and no test should sleep."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _guard(clock, **over):
    kwargs = dict(max_per_ip=3, max_per_identity=5, window_seconds=60, clock=clock)
    kwargs.update(over)
    return LoginGuard("test", **kwargs)


def _fail(guard, n, ip="1.1.1.1", identity="rep"):
    for _ in range(n):
        guard.record_failure(ip, identity)


def test_under_the_limit_passes():
    guard = _guard(_Clock())
    _fail(guard, 2)
    guard.check("1.1.1.1", "rep")  # does not raise


def test_too_many_from_one_ip_is_locked_out():
    guard = _guard(_Clock())
    _fail(guard, 3)
    with pytest.raises(HTTPException) as e:
        guard.check("1.1.1.1", "rep")
    assert e.value.status_code == 429
    assert "Retry-After" in e.value.headers


def test_the_ip_limit_does_not_lock_out_a_different_caller():
    guard = _guard(_Clock())
    _fail(guard, 3, ip="1.1.1.1")
    guard.check("2.2.2.2", "someone-else")  # does not raise


def test_one_account_attacked_from_many_addresses_is_still_locked_out():
    """The reason the per-identity counter exists: X-Forwarded-For is
    caller-supplied, so the IP counter alone is evadable."""
    guard = _guard(_Clock())
    for i in range(5):
        guard.record_failure(f"10.0.0.{i}", "Aviva Landin")
    with pytest.raises(HTTPException) as e:
        guard.check("10.0.0.99", "Aviva Landin")
    assert e.value.status_code == 429


def test_the_window_expires():
    clock = _Clock()
    guard = _guard(clock)
    _fail(guard, 3)
    clock.advance(61)
    guard.check("1.1.1.1", "rep")  # does not raise


def test_failures_older_than_the_window_do_not_count():
    clock = _Clock()
    guard = _guard(clock)
    _fail(guard, 2)
    clock.advance(61)
    _fail(guard, 2)
    guard.check("1.1.1.1", "rep")  # the first two have aged out


def test_a_successful_sign_in_clears_the_counters():
    """Someone who mistypes twice and then gets it right is not then locked out
    by their own earlier attempts."""
    guard = _guard(_Clock())
    _fail(guard, 2)
    guard.record_success("1.1.1.1", "rep")
    _fail(guard, 2)
    guard.check("1.1.1.1", "rep")  # does not raise


def test_retry_after_is_positive_and_bounded_by_the_window():
    clock = _Clock()
    guard = _guard(clock)
    _fail(guard, 3)
    clock.advance(30)
    with pytest.raises(HTTPException) as e:
        guard.check("1.1.1.1", "rep")
    retry = int(e.value.headers["Retry-After"])
    assert 0 < retry <= 60


# ------------------------------------------------------------------ client_ip

class _Request:
    def __init__(self, headers=None, host="127.0.0.1"):
        self.headers = Headers(headers or {})
        self.client = type("C", (), {"host": host})() if host else None


def test_client_ip_prefers_the_forwarded_client():
    """Behind nginx every request's peer is the proxy, so without this each
    caller would share one counter and the first few failures would lock out
    everyone."""
    req = _Request({"x-forwarded-for": "203.0.113.7, 172.18.0.4"}, host="172.18.0.4")
    assert client_ip(req) == "203.0.113.7"


def test_client_ip_falls_back_to_the_peer():
    assert client_ip(_Request(host="198.51.100.2")) == "198.51.100.2"


def test_client_ip_survives_a_missing_client():
    assert client_ip(_Request(host=None)) == "unknown"
