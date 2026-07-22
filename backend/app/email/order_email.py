"""Order email content + background scheduling.

Content builders return (subject, body); orchestrators attach the card-free
order PDF and delegate transport to app.email.mailer. schedule_order_emails is
the single entry point the orders router calls after commit.
"""
from app.config import settings
from app.email import mailer


def _summary(ctx: dict) -> str:
    return (
        f"Order: {ctx['short_id']}\n"
        f"Season: {ctx['season_label']} ({ctx['season_code']})\n"
        f"Buyer: {ctx['buyer_name']}\n"
        f"Total pieces: {ctx['total_qty']}\n"
        f"Total: ${ctx['total_amount']:,.2f}\n"
    )


def admin_email(ctx: dict) -> tuple[str, str]:
    subject = (
        f"New wholesale order — {ctx['buyer_name']} "
        f"({ctx['season_code']}) — {ctx['total_qty']} pcs"
    )
    body = "A new wholesale order was submitted.\n\n" + _summary(ctx) + "\nThe order form PDF is attached."
    return subject, body


def buyer_email(ctx: dict) -> tuple[str, str]:
    subject = f"Your Wooden Ships wholesale order — {ctx['season_label']}"
    body = (
        f"Thank you for your Wooden Ships wholesale order, {ctx['buyer_name']}.\n\n"
        + _summary(ctx)
        + "\nYour order copy is attached as a PDF.\n\n— Wooden Ships"
    )
    return subject, body


def send_admin_copy(ctx: dict, pdf_bytes: bytes, filename: str) -> bool:
    subject, body = admin_email(ctx)
    return mailer.send_email(settings.admin_email, subject, body, [(filename, pdf_bytes, "pdf")])


def send_buyer_copy(to: str, ctx: dict, pdf_bytes: bytes, filename: str) -> bool:
    subject, body = buyer_email(ctx)
    return mailer.send_email(to, subject, body, [(filename, pdf_bytes, "pdf")])


def schedule_order_emails(
    background,
    *,
    order_copy: bool,
    order_copy_email: str | None,
    ctx: dict,
    pdf_bytes: bytes,
    filename: str,
) -> None:
    """Queue the admin notice (always) and the buyer copy (only when opted in).

    Runs via FastAPI BackgroundTasks after the response — a slow/failed Gmail
    never blocks or fails the order.
    """
    background.add_task(send_admin_copy, ctx, pdf_bytes, filename)
    if order_copy and order_copy_email:
        background.add_task(send_buyer_copy, order_copy_email, ctx, pdf_bytes, filename)
