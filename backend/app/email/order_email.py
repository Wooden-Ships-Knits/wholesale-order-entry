"""Order email content + background scheduling.

Content builders return (subject, body); orchestrators attach the card-free
order PDF and delegate transport to app.email.mailer.

Who gets the order PDF:
  send_admin_copy  — at submit, to ADMIN_EMAIL: the team's internal notice
  send_signed_copy — same, when the buyer signs via the emailed link
  send_order_copy  — the customer-facing copy, to the buyer AND their rep

The first two are OFF by default since 2026-08-06 — see settings.
send_internal_notices. They are still built and still sent when it is on, so
this module deliberately keeps all three.

The order copy goes out unconditionally (2026-08-05 — it used to depend on an
"email me a copy" checkbox, which is gone from both the form and the signing
page). It is sent once per order, at the point the quantities become final:
at submit for a customer-filled order, at signing for a rep-filled one, since
the buyer may change quantities on the signing page.

The rep is a To on that copy rather than being sent a separate mail, so there
is one thread per order carrying one attachment and a reply reaches everyone
who has it. They are not copied on the internal notices above — that would be
the same PDF twice. On a rep-filled order they still hear from us at submit:
the signature request CCs them (routers/orders.py::_send_signature_request).

None of these is a confirmation: the order is reviewed in /admin afterwards
and can be declined. Accept/Decline sends the buyer nothing automatically.
"""
from app.config import settings
from app.email import mailer


def _store(ctx: dict) -> str:
    """The store this order is for, which is how the team identifies it.

    Falls back to the buyer only when there is no account name — older orders
    predate the field, and a person's name is better than an empty subject.
    """
    return (ctx.get("account_name") or "").strip() or ctx.get("buyer_name") or "—"


def _tag(ctx: dict) -> str:
    """The order's short id, appended to every subject line.

    One order can generate four mails across two flows; the id at the end is
    what ties them together in a mailbox and back to the /admin row, since
    store + season alone repeat across a season's re-orders.
    """
    return f" - {ctx['short_id']}"


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
        f"({ctx['season_code']}) — {ctx['total_qty']} pcs" + _tag(ctx)
    )
    body = "A new wholesale order was submitted.\n\n" + _summary(ctx) + "\nThe order form PDF is attached."
    return subject, body


def order_copy_email(ctx: dict) -> tuple[str, str]:
    """The customer-facing copy, sent to the buyer and CC'd to their rep.

    Sent once the quantities are final — at submit for a customer-filled
    order, after signing for a rep-filled one — so the totals below are the
    ones that count. Deliberately NOT a confirmation: that is the Sales Order
    Confirmation the body promises, which the team sends separately.
    """
    subject = f"An Order has been Submitted! {ctx['season_label']} - {_store(ctx)}" + _tag(ctx)
    body = (
        f"Hi there,\n\n"
        f"Thank you for your order! Your signed PDF is attached.\n\n"
        f"Total pieces: {ctx['total_qty']}\n"
        f"Total: ${ctx['total_amount']:,.0f}\n\n"  # whole dollars, by request
        "You will receive a Sales Order Confirmation within 2 business days.\n\n"
        "As a reminder, you can change your order up to 10 days from receipt of the Sales Order Confirmation.\n\n"
        "Thanks again for your order! We are excited to knit this for you!\n\n"
        "Wooden Ships"
    )
    return subject, body


def rep_notice_email(ctx: dict) -> tuple[str, str]:
    """The rep's own copy of an order they wrote, sent at submit.

    Replaces the CC they used to get on the buyer's signature request. That CC
    was dropped because the request's body IS the signing link, and a link is a
    bearer credential — a rep holding one could sign on the buyer's behalf. So
    this carries the same PDF and says the same thing about status, and
    deliberately carries NO link.

    Sent whether or not the signing link went out, including while an order is
    held for a conflict: the rep wrote it, so they should know it landed. NOTE
    that the body below states the link was sent instantly, which is not true
    of a held order — see routers/orders.py.

    Wording supplied by Wooden Ships 2026-08-06; keep it as written. The
    **bold** run renders in the HTML part and has its markers stripped from the
    plain-text one — see email/mailer.py::html_from_text.
    """
    subject = (
        f"Draft order/Need Signature - {ctx['season_label']} - {_store(ctx)}" + _tag(ctx)
    )
    body = """Hi there,

We have received an unsigned Draft Order for this account! We appreciate it!

Upon receipt, our system instantly sent a link to the customer. They can sign digitally and immediately submit. They can also edit any part of the order if they want.

Attached is a PDF copy of the order for your reference and so you can follow up with your account if they don't sign the order soon.

**As much as possible, we encourage you to have the customer immediately open their email as soon as you click on the "send to Customer" so they can sign on the spot and complete the process.** This will save you from following up and having orders sit unsubmitted.

You will receive a Notification email once the customer has actually signed the order.

Until we receive the signed copy, reviewed it and accepted the order, the order is in Draft status. This means the order is not in our system. It will not appear in any report and the yarn is not held, the capacity is not booked and the ship window is not locked.

If you have any questions, please feel free to reply to this email.

Thank you!
Wooden Ships
"""
    return subject, body


def rep_followup_email(ctx: dict) -> tuple[str, str]:
    """Day-6 nudge to the REP: their buyer still has not signed.

    The buyer is already chased on days 2, 5, 15, 22 and 29. This is the one
    that goes to the person who wrote the order, on the theory that by day six
    a phone call is worth more than a sixth email to the same inbox.

    Sent once per order, never repeated — see services/signature_reminders.py.

    Wording supplied by Wooden Ships 2026-08-10; keep it as written.
    """
    subject = (
        f"❗Pls CALL this account: {_store(ctx)} - {ctx['season_label']}" + _tag(ctx)
    )
    body = """Hi,

We have made 3 attempts to get a Signature on the order you submitted.

Email is not working. **Could you please call the account**, ask them to find the email, click and sign.

It's fast and easy to sign. But until they do, these orders are NOT in the system. They are not in your reports. No yarn, capacity, or ship window is held for them.

As much as possible, avoid entering orders "later" or in "batches." Pls enter while still with the buyer, have them open the email and sign on the spot as they would if you had a paper order.

If you have any questions or feedback, just reply to this email.

Thank you!
Wooden Ships
"""
    return subject, body


def send_rep_followup(to: str, ctx: dict, pdf_bytes: bytes, filename: str) -> bool:
    """The day-6 nudge, to the rep, with the PDF and no signing link."""
    subject, body = rep_followup_email(ctx)
    return mailer.send_email(
        to, subject, body, [(filename, pdf_bytes, "pdf")],
        html=mailer.html_from_text(body),
    )


def signed_email(ctx: dict) -> tuple[str, str]:
    """Notice for an order the BUYER has just signed through the emailed link.

    Distinct from admin_email because "A new wholesale order was submitted" is
    wrong here — it was submitted days ago by the rep, and what just happened
    is the signature. The quantities may also have changed in between, so the
    totals below are the ones that count.
    """
    subject = (
        f"Order signed — {_store(ctx)} "
        f"({ctx['season_code']}) — {ctx['total_qty']} pcs" + _tag(ctx)
    )
    body = (
        f"{ctx['buyer_name']} signed this order.\n\n"
        + _summary(ctx)
        + "\nThe signed order form PDF is attached."
    )
    return subject, body


# html_from_text returns None unless the body actually uses **bold**, so these
# three stay single-part plain text until a template marks something up.
def send_admin_copy(ctx: dict, pdf_bytes: bytes, filename: str) -> bool:
    """The team's internal notice. ADMIN_EMAIL only — the rep gets the PDF on
    the customer copy instead of the same attachment twice."""
    subject, body = admin_email(ctx)
    return mailer.send_email(
        settings.admin_email, subject, body, [(filename, pdf_bytes, "pdf")],
        html=mailer.html_from_text(body),
    )


def send_signed_copy(ctx: dict, pdf_bytes: bytes, filename: str) -> bool:
    """Same recipient as send_admin_copy, worded for a signature rather than
    a new submission."""
    subject, body = signed_email(ctx)
    return mailer.send_email(
        settings.admin_email, subject, body, [(filename, pdf_bytes, "pdf")],
        html=mailer.html_from_text(body),
    )


def send_rep_notice(to: str, ctx: dict, pdf_bytes: bytes, filename: str) -> bool:
    """The rep's copy at submit, with the PDF and no signing link."""
    subject, body = rep_notice_email(ctx)
    return mailer.send_email(
        to, subject, body, [(filename, pdf_bytes, "pdf")],
        html=mailer.html_from_text(body),
    )


def send_order_copy(to: str, ctx: dict, pdf_bytes: bytes, filename: str, rep: str | None = None) -> bool:
    """The order copy, addressed to the buyer AND the rep — no CC.

    Both are To rather than the rep being copied (2026-08-05): this is as much
    the rep's record of the order as the customer's, and a CC reads as being
    kept in the loop on someone else's mail. rep is None when the territory is
    unknown or has no rep row, and the buyer still gets their copy.
    """
    subject, body = order_copy_email(ctx)
    recipients = ", ".join(a for a in (to, rep) if a)
    return mailer.send_email(
        recipients, subject, body, [(filename, pdf_bytes, "pdf")],
        html=mailer.html_from_text(body),
    )


# schedule_order_emails() lived here: it queued the admin notice AND the buyer
# copy together at submit. Nothing called it — the buyer copy is sent on Accept
# instead (app/routers/admin.py), because the buyer is told they'll hear back
# "once your order has been reviewed", and at submit there is nothing to
# confirm yet. Removed rather than left dead so there is one obvious path.
