"""/api/admin — order monitoring for the admin team.

Every route except login/session is behind require_admin. Order PDFs and tax
certificates live outside the web root and are streamed through here, never
served statically: they carry buyer contact details and tax IDs.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.security import SESSION_KEY, AdminRequired, verify_password
from app.config import settings
from app.db.models import Order
from app.db.session import get_db
from app.pdf import render as pdf_render
from fastapi import Depends

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")

VALID_STATUSES = {"accepted", "declined"}


class LoginRequest(BaseModel):
    password: str


class StatusRequest(BaseModel):
    status: str
    reason: str = Field("", max_length=1000)


# ------------------------------------------------------------------ session

@router.post("/login")
def login(payload: LoginRequest, request: Request) -> dict:
    if not settings.admin_password_hash:
        logger.error("Admin login attempted but ADMIN_PASSWORD_HASH is not set")
        raise HTTPException(status_code=503, detail="Admin access is not configured")
    if not verify_password(payload.password, settings.admin_password_hash):
        # Never log the attempted password.
        logger.warning("Failed admin login attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password"
        )
    request.session[SESSION_KEY] = True
    return {"ok": True}


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/session")
def session_state(request: Request) -> dict:
    """Lets the page decide between the login screen and the table."""
    return {"authenticated": bool(request.session.get(SESSION_KEY))}


# ------------------------------------------------------------------ orders

def _row(o: Order) -> dict:
    return {
        "id": str(o.id),
        "shortId": str(o.id)[:8],
        "createdAt": o.created_at.isoformat() if o.created_at else None,
        "seasonCode": o.season_code,
        "accountName": o.buyer_name,
        "orderCopyEmail": o.order_copy_email,
        "salesTerritory": o.sales_territory,
        "specialInstructions": o.special_instructions,
        "shipEmail": o.ship_email,
        "totalQty": o.total_qty,
        "totalAmount": float(o.total_amount) if o.total_amount is not None else None,
        # null = unanswered / not yet checked. The UI must not render these as "No".
        "isNewAccount": o.is_new_account,
        "hasConflict": o.has_conflict,
        "hasCertificate": bool(o.cert_filename),
        "notes": o.notes,
        "status": o.status,
        "statusReason": o.status_reason,
        "statusAt": o.status_at.isoformat() if o.status_at else None,
    }


@router.get("/orders", dependencies=[AdminRequired])
def list_orders(
    db: Session = Depends(get_db),
    status_filter: str | None = None,
    limit: int = 100,
) -> dict:
    stmt = select(Order).order_by(Order.created_at.desc()).limit(min(limit, 500))
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
    return {"orders": [_row(o) for o in db.execute(stmt).scalars()]}


@router.post("/orders/{order_id}/status", dependencies=[AdminRequired])
def set_status(order_id: str, payload: StatusRequest, db: Session = Depends(get_db)) -> dict:
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="status must be accepted or declined")
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    order.status = payload.status
    order.status_reason = payload.reason or None
    order.status_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("Order %s marked %s", str(order.id)[:8], payload.status)
    return _row(order)


# ------------------------------------------------------------------ files

def _safe_output_path(filename: str) -> Path:
    """Resolve a filename inside pdf_output_dir, refusing anything that escapes it."""
    base = Path(settings.pdf_output_dir).resolve()
    path = (base / filename).resolve()
    if not path.is_relative_to(base):
        logger.warning("Blocked path traversal attempt: %r", filename)
        raise HTTPException(status_code=400, detail="Invalid file")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return path


@router.get("/orders/{order_id}/pdf", dependencies=[AdminRequired])
def download_pdf(order_id: str, db: Session = Depends(get_db)) -> FileResponse:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    filename = pdf_render.order_pdf_filename(
        order.season_code, order.buyer_name or "", order.created_at, order.id
    )
    # inline → the browser renders it in the tab instead of downloading.
    return FileResponse(
        _safe_output_path(filename),
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="inline",
    )


@router.get("/orders/{order_id}/certificate", dependencies=[AdminRequired])
def download_certificate(order_id: str, db: Session = Depends(get_db)) -> FileResponse:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.cert_filename:
        raise HTTPException(status_code=404, detail="No certificate for this order")
    # PDFs and images render inline; browsers fall back to downloading anything
    # they can't display, so this is safe for every allowed cert type.
    return FileResponse(
        _safe_output_path(order.cert_filename),
        filename=order.cert_filename,
        content_disposition_type="inline",
    )
