"""Order PDF rendering (WeasyPrint) and saving.

The rendered PDF is the ONLY artifact that contains the full card number/CVV
(for manual processing). It is written to PDF_OUTPUT_DIR — a bind-mounted
directory outside the web root, never served by nginx.
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
    return HTML(string=html).write_pdf()


def order_pdf_filename(season: str, buyer_name: str, created, order_id) -> str:
    """WS-order-{season}-{buyerName}-{YYYYMMDD}-{shortId}.pdf"""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", buyer_name or "unknown").strip("-")[:40] or "unknown"
    return f"WS-order-{season}-{slug}-{created:%Y%m%d}-{str(order_id)[:8]}.pdf"


def save_order_pdf(pdf_bytes: bytes, filename: str) -> str:
    out_dir = Path(settings.pdf_output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_bytes(pdf_bytes)
    logger.info("Order PDF written: %s (%d bytes)", filename, len(pdf_bytes))
    return str(path)
