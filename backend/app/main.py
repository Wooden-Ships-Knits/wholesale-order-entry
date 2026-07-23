import secrets

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.routers import (
    accounts,
    admin,
    conflict_email,
    health,
    orders,
    products,
    reps,
    seasons,
    send_email,
    ship_windows,
)

app = FastAPI(title="Wooden Ships Wholesale Order Form")

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
app.include_router(conflict_email.router, prefix="/api")
app.include_router(send_email.router, prefix="/api")
