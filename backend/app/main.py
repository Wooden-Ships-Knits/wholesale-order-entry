import asyncio
import contextlib
import logging
import secrets

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.db.session import SessionLocal
from app.services import signature_reminders
from app.tasks import poll_replies
from app.routers import (
    accounts,
    admin,
    catalog,
    conflict_email,
    health,
    notices,
    orders,
    products,
    reports,
    reps,
    reps_portal,
    seasons,
    send_email,
    ship_windows,
    sign,
    signature_email,
)

logger = logging.getLogger(__name__)

# How often the unsigned-order sweep wakes up. The thresholds it enforces are
# 48h and 96h, so an hour of slack costs nothing and keeps the loop cheap.
REMINDER_TICK_SECONDS = 60 * 60


async def _reminder_loop() -> None:
    """Chase unsigned orders forever, one pass an hour.

    An in-process loop rather than a scheduler container, to keep the
    deployment at the same three containers. It follows that a SECOND backend
    replica would double every reminder — if this is ever scaled out, move the
    sweep behind an advisory lock or into a single worker.

    The body runs in a threadpool: the session and the SMTP call are both
    blocking, and awaiting them on the event loop would stall every request
    for the duration of a send.
    """
    while True:
        await asyncio.sleep(REMINDER_TICK_SECONDS)
        try:
            await run_in_threadpool(_reminder_pass)
        except Exception:
            # Never let one bad pass kill the loop — an unhandled error here
            # would silently stop all chasing until the next deploy.
            logger.exception("Signature reminder sweep failed")


def _reminder_pass() -> None:
    db = SessionLocal()
    try:
        signature_reminders.send_due_reminders(db)
        # Same pass, same session: both walk the unsigned orders, and running
        # them together keeps "what happens on the hour" in one place.
        signature_reminders.send_due_rep_followups(db)
    finally:
        db.close()


def _mailbox_polling_enabled() -> tuple[bool, str]:
    """Should this instance poll the shared mailbox on a timer? (yes/no, why).

    Two refusals, both about not stealing someone else's mail:

      * IMAP unconfigured — nothing to poll.
      * dev_mail_rewrite on — this is a development instance, and dev and
        production read the SAME wholesale@ mailbox. Fetching marks messages
        \\Seen, so an automatic dev poll would silently consume the bounces and
        rep replies production is waiting for. The "Check replies" button still
        works there, so a developer can poll deliberately; it just never
        happens behind their back.
    """
    if not settings.imap_configured:
        return False, "IMAP is not configured"
    if settings.dev_mail_rewrite:
        return False, "development instance — it shares production's mailbox"
    if settings.poll_replies_minutes <= 0:
        return False, "POLL_REPLIES_MINUTES is 0"
    return True, ""


async def _poll_replies_loop() -> None:
    """Capture inbound replies and delivery failures on a timer.

    Until now this only ran when someone pressed "Check replies", so a bounced
    signature request sat unnoticed — the order kept showing "Email Sent ✓"
    while the buyer had never received anything.
    """
    enabled, why = _mailbox_polling_enabled()
    if not enabled:
        logger.info("Automatic reply polling is off: %s", why)
        return
    interval = settings.poll_replies_minutes * 60
    logger.info("Automatic reply polling every %d minutes", settings.poll_replies_minutes)
    while True:
        await asyncio.sleep(interval)
        try:
            await run_in_threadpool(poll_replies.run_once)
        except Exception:
            logger.exception("Reply poll failed")


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    tasks = [
        asyncio.create_task(_reminder_loop()),
        asyncio.create_task(_poll_replies_loop()),
    ]
    yield
    for t in tasks:
        t.cancel()
    for t in tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await t


app = FastAPI(title="Wooden Ships Wholesale Order Form", lifespan=lifespan)

# Signs the admin session cookie. A generated fallback keeps dev working but
# invalidates sessions on restart — set SESSION_SECRET in production.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret or secrets.token_urlsafe(32),
    session_cookie="ws_admin",
    https_only=settings.session_cookie_secure,
    same_site="strict",
    max_age=8 * 60 * 60,
)

# Same-origin in production (nginx proxies /api); CORS matters for local dev
# and stays locked to the configured origin. Credentials are allowed so the
# admin session cookie survives the dev-server proxy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(health.router, prefix="/api")
app.include_router(seasons.router, prefix="/api")
app.include_router(ship_windows.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(reps.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(reps_portal.router, prefix="/api")
app.include_router(conflict_email.router, prefix="/api")
app.include_router(send_email.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(notices.router, prefix="/api")
app.include_router(signature_email.router, prefix="/api")
# Public — token-authenticated, not session-authenticated. See routers/sign.py
# for what that means and what the GET response is allowed to contain.
app.include_router(sign.router, prefix="/api")
