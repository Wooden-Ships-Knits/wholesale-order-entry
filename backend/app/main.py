from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import accounts, health, orders, products, seasons

app = FastAPI(title="Wooden Ships Wholesale Order Form")

# Same-origin in production (nginx proxies /api); CORS matters for local dev
# and stays locked to the configured origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(health.router, prefix="/api")
app.include_router(seasons.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
