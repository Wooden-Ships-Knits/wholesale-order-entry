"""Order email content + background scheduling.

Content builders return (subject, body); orchestrators attach the card-free
order PDF and delegate transport to app.email.mailer.

Who gets the order PDF:
  send_admin_copy  — at submit: always to ADMIN_EMAIL, CC the territory's rep
  send_signed_copy — same recipients, when the buyer signs via the emailed link
  send_buyer_copy  — only when the buyer ticked "send me a copy"

The rep is CC'd rather than sent a separate mail so there is one thread per
order carrying one attachment, and a reply reaches everyone who has it. A
rep-filled order therefore reaches the rep twice: once at submit (what they
sent out) and once on signing (what the buyer actually agreed to) — which is
the point, because the buyer may have changed the quantities in between.

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


def signed_email(ctx: dict) -> tuple[str, str]:
    """Notice for an order the BUYER has just signed through the emailed link.

    Distinct from admin_email because "A new wholesale order was submitted" is
    wrong here — it was submitted days ago by the rep, and what just happened
    is the signature. The quantities may also have changed in between, so the
    totals below are the ones that count.
    """
    subject = (
        f"Order signed — {_store(ctx)} "
        f"({ctx['season_code']}) — {ctx['total_qty']} pcs"
    )
    body = (
        f"{ctx['buyer_name']} signed this order.\n\n"
        + _summary(ctx)
        + "\nThe signed order form PDF is attached."
    )
    return subject, body


def send_admin_copy(ctx: dict, pdf_bytes: bytes, filename: str, cc: str | None = None) -> bool:
    """Always to ADMIN_EMAIL, CC the territory's rep so they get the PDF too."""
    subject, body = admin_email(ctx)
    return mailer.send_email(
        settings.admin_email, subject, body, [(filename, pdf_bytes, "pdf")], cc=cc
    )


def send_signed_copy(ctx: dict, pdf_bytes: bytes, filename: str, cc: str | None = None) -> bool:
    """Same recipients as send_admin_copy, worded for a signature rather than
    a new submission."""
    subject, body = signed_email(ctx)
    return mailer.send_email(
        settings.admin_email, subject, body, [(filename, pdf_bytes, "pdf")], cc=cc
    )


def send_buyer_copy(to: str, ctx: dict, pdf_bytes: bytes, filename: str) -> bool:
    subject, body = buyer_email(ctx)
    return mailer.send_email(to, subject, body, [(filename, pdf_bytes, "pdf")])


# schedule_order_emails() lived here: it queued the admin notice AND the buyer
# copy together at submit. Nothing called it — the buyer copy is sent on Accept
# instead (app/routers/admin.py), because the buyer is told they'll hear back
# "once your order has been reviewed", and at submit there is nothing to
# confirm yet. Removed rather than left dead so there is one obvious path.
