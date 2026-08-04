"""Order PDF rendering (WeasyPrint) and saving.

The PDF shows only the card name and last 4 — the full number and CVV are
never rendered and never leave the submit request. Output is written to
PDF_OUTPUT_DIR, a bind-mounted directory outside the web root.
"""
import logging
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings

logger = logging.getLogger(__name__)

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    autoescape=select_autoescape(["html"]),
)


def _longdate(value: Any) -> str:
    """'July 28, 2026' — never a numeric date.

    Bali reads 07/28 as day 7 of month 28-ish and the US reads it as July 28;
    spelling the month out removes the ambiguity entirely. Accepts a date,
    datetime, ISO string or None so a missing value renders as an em dash
    instead of blowing up the render (the PDF is built before the DB commit,
    so an exception here fails the buyer's whole submission).
    """
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value).date()
        except ValueError:
            return value  # already formatted, or something we can't parse
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        # %-d avoids a zero-padded day ("July 08"); portable on Linux/macOS.
        return f"{value:%B} {value.day}, {value.year}"
    return str(value)


def _money(value: Any) -> str:
    """'1,675.00' — thousands separated, always two decimals."""
    if value is None:
        return "0.00"
    return f"{Decimal(str(value)):,.2f}"


_env.filters["longdate"] = _longdate
_env.filters["money"] = _money


def render_order_pdf(context: dict) -> bytes:
    """Render the order template to PDF bytes. Card data stays in memory only."""
    # Imported lazily: WeasyPrint takes ~1s to import and is only needed here.
    from weasyprint import HTML

    html = _env.get_template("template.html").render(**context)
    # base_url lets the template reference local assets (the logo) by relative
    # path; without it WeasyPrint cannot resolve them and silently omits them.
    return HTML(string=html, base_url=str(Path(__file__).parent)).write_pdf()


def _buyer_slug(buyer_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", buyer_name or "unknown").strip("-")[:40] or "unknown"


def order_pdf_filename(season: str, buyer_name: str, created, order_id) -> str:
    """WS-order-{season}-{buyerName}-{YYYYMMDD}-{shortId}.pdf"""
    return f"WS-order-{season}-{_buyer_slug(buyer_name)}-{created:%Y%m%d}-{str(order_id)[:8]}.pdf"


def cert_filename(season: str, buyer_name: str, created, order_id, original_name: str) -> str:
    """WS-cert-{season}-{buyerName}-{YYYYMMDD}-{shortId}{ext}

    The extension comes from the uploaded name, already whitelist-validated
    by the CertFile schema; everything else in the name is discarded.
    """
    ext = Path(original_name).suffix.lower()
    return f"WS-cert-{season}-{_buyer_slug(buyer_name)}-{created:%Y%m%d}-{str(order_id)[:8]}{ext}"


def save_output_file(data: bytes, filename: str) -> str:
    out_dir = Path(settings.pdf_output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_bytes(data)
    logger.info("Output file written: %s (%d bytes)", filename, len(data))
    return str(path)


def save_order_pdf(pdf_bytes: bytes, filename: str) -> str:
    return save_output_file(pdf_bytes, filename)


def delete_output_file(filename: str) -> bool:
    """Remove a file from PDF_OUTPUT_DIR. True if it was there.

    Used when an order's PDF is re-saved under a different name — the filename
    carries the buyer name, and the buyer can correct that while signing, so
    the pre-signature copy would otherwise be left behind as an orphan holding
    a stale, unsigned version of the same order.

    Resolved and re-checked against the output directory, like the admin
    download route: `filename` is derived from stored data, but nothing here
    should be able to delete outside that folder.
    """
    base = Path(settings.pdf_output_dir).resolve()
    path = (base / filename).resolve()
    if not str(path).startswith(str(base) + "/") or not path.is_file():
        return False
    path.unlink()
    logger.info("Superseded output file removed: %s", filename)
    return True
