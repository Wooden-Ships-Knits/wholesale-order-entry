"""Order PDF rendering (WeasyPrint) and saving.

The PDF shows only the card name and last 4 — the full number and CVV are
never rendered and never leave the submit request. Output is written to
PDF_OUTPUT_DIR, a bind-mounted directory outside the web root.
"""
import logging
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings

logger = logging.getLogger(__name__)

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    autoescape=select_autoescape(["html"]),
)


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
