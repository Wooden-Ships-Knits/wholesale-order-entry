"""Order email content + background scheduling.

Content builders return (subject, body); orchestrators attach the card-free
order PDF and delegate transport to app.email.mailer.

Both are sent at submit from app/routers/orders.py:
  send_admin_copy  — always, to ADMIN_EMAIL
  send_buyer_copy  — only when the buyer ticked "send me a copy"

Neither is a confirmation: the order is reviewed in /admin afterwards and can
be declined. Accept/Decline sends the buyer nothing automatically today.
"""
from app.config import settings
from app.email import mailer


def _store(ctx: dict) -> str:
    """The store this order is for, which is how the team identifies it.

    Falls back to the buyer only when there is no account name — older orders
    predate the field, and a person's name is better than an empty subject.
    """
    return (ctx.get("account_name") or "").strip() or ctx.get("buyer_name") or "—"


def _summary(ctx: dict) -> str:
    return (
        f"Order: {ctx['short_id']}\n"
        f"Store: {_store(ctx)}\n"
        f"Season: {ctx['season_label']} ({ctx['season_code']})\n"
        f"Buyer: {ctx['buyer_name']}\n"
        f"Total pieces: {ctx['total_qty']}\n"
        f"Total: ${ctx['total_amount']:,.2f}\n"
    )


def admin_email(ctx: dict) -> tuple[str, str]:
    # Store first: Gmail truncates the subject, and buyer first names repeat
    # across stores ("Deborah" four times over is unscannable).
    subject = (
        f"New wholesale order — {_store(ctx)} "
        f"({ctx['season_code']}) — {ctx['total_qty']} pcs"
    )
    body = "A new wholesale order was submitted.\n\n" + _summary(ctx) + "\nThe order form PDF is attached."
    return subject, body


def buyer_email(ctx: dict) -> tuple[str, str]:
    # Sent at submit, to buyers who ticked "send me a copy". Deliberately NOT a
    # confirmation — the order still has to be reviewed and can be declined.
    # Wording mirrors the note under that checkbox on the form
    # (frontend/src/components/TermsSignature.jsx); keep the two in step.
    subject = f"Your Wooden Ships order copy — {ctx['season_label']}"
    body = (
        f"Thank you for your Wooden Ships wholesale order, {ctx['buyer_name']}.\n\n"
        "This is a copy for your records — not an order confirmation. "
        "We'll email you once your order has been reviewed.\n\n"
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


# schedule_order_emails() lived here: it queued the admin notice AND the buyer
# copy together at submit. Nothing called it — the buyer copy is sent on Accept
# instead (app/routers/admin.py), because the buyer is told they'll hear back
# "once your order has been reviewed", and at submit there is nothing to
# confirm yet. Removed rather than left dead so there is one obvious path.
