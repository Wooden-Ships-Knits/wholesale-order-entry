"""SQLAlchemy models. NO CVV column — ever, in any form (CLAUDE.md rule 1).

card_name, card_last4 and card_exp persist in the clear. The full card number
is never stored as a column: it exists only inside card_pdf_enc, the encrypted
admin-copy PDF, which is purged once the monitoring team has keyed the card
into Salesforce. CVV is read by nothing and stored nowhere.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    season_code: Mapped[str] = mapped_column(Text)
    order_date: Mapped[date | None] = mapped_column(Date)
    part_ship_ok: Mapped[bool | None] = mapped_column(Boolean)
    ship_window_note: Mapped[str | None] = mapped_column(Text)
    ship_window: Mapped[str | None] = mapped_column(Text)  # buyer-selected window
    filled_by: Mapped[str | None] = mapped_column(Text)  # rep | customer
    notes: Mapped[str | None] = mapped_column(Text)

    # bill to
    buyer_name: Mapped[str | None] = mapped_column(Text)
    bill_street: Mapped[str | None] = mapped_column(Text)
    bill_city_state: Mapped[str | None] = mapped_column(Text)
    bill_zip: Mapped[str | None] = mapped_column(Text)
    tel: Mapped[str | None] = mapped_column(Text)
    fax: Mapped[str | None] = mapped_column(Text)
    bill_lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    bill_lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    # ship to
    ship_email: Mapped[str] = mapped_column(Text)
    ship_street: Mapped[str | None] = mapped_column(Text)
    ship_city_state: Mapped[str | None] = mapped_column(Text)
    ship_zip: Mapped[str | None] = mapped_column(Text)
    resale_tax_id: Mapped[str | None] = mapped_column(Text)
    ship_lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    ship_lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    # payment (NO card number / CVV columns)
    payment_method: Mapped[str | None] = mapped_column(Text)  # link | card
    approval_before_charge: Mapped[bool | None] = mapped_column(Boolean)
    card_name: Mapped[str | None] = mapped_column(Text)
    card_last4: Mapped[str | None] = mapped_column(Text)
    # Expiry is cardholder data, not sensitive authentication data — safe to
    # keep in the clear (unlike the number, and unlike CVV which is never kept).
    card_exp: Mapped[str | None] = mapped_column(Text)
    # The admin-copy PDF showing the full card number, AES-256-GCM encrypted
    # (app/crypto.py). Held only until the monitoring team keys the card into
    # Salesforce: purged on Accept/Decline and by the retention sweep. NEVER
    # written to disk, emailed, or logged. null = no card kept / already purged.
    card_pdf_enc: Mapped[bytes | None] = mapped_column(LargeBinary)

    # tax exemption acknowledgements + uploaded certificate
    cert_required_ack: Mapped[bool | None] = mapped_column(Boolean)
    cert_sending_ack: Mapped[bool | None] = mapped_column(Boolean)
    cert_on_file: Mapped[bool | None] = mapped_column(Boolean)
    cert_filename: Mapped[str | None] = mapped_column(Text)

    # signature / terms
    signature_name: Mapped[str | None] = mapped_column(Text)
    signature_date: Mapped[date | None] = mapped_column(Date)
    terms_accepted: Mapped[bool | None] = mapped_column(Boolean)
    # buyer opted to receive a copy of the order form at this address; null = no
    order_copy_email: Mapped[str | None] = mapped_column(Text)

    # ---- signature by emailed link (admin sends it from the order table) ----
    # Where the link was sent, and when. null requested_at = never asked.
    signature_email: Mapped[str | None] = mapped_column(Text)
    signature_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A bearer credential: whoever holds the URL can edit and sign this order.
    # Random — NEVER the order id, which appears in admin URLs, log lines and
    # PDF filenames. Nulled on signing, so a link works exactly once.
    signature_token: Mapped[str | None] = mapped_column(Text, unique=True, index=True)
    signature_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Set only when the buyer signs through the link — signature_name alone
    # can't distinguish that from a rep who typed it on the form.
    signature_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # How many automatic chasers have gone out (0, 1, 2 …). Indexes into
    # settings.signature_reminder_hours, so it is the sweep's cursor as well as
    # a count: never a timestamp, because "which reminder is next" has to
    # survive the schedule being changed.
    signature_reminders_sent: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    signature_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The order as the rep wrote it, snapshotted when the link is first sent.
    # Lets /admin show "edited at signing: 40 → 22 pcs" instead of the buyer's
    # change silently replacing what the rep and buyer discussed.
    orig_total_qty: Mapped[int | None] = mapped_column(Integer)
    orig_total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    # internal use
    new_or_reorder: Mapped[str | None] = mapped_column(Text)
    account_status: Mapped[str | None] = mapped_column(Text)
    campaign: Mapped[str | None] = mapped_column(Text)
    po_number: Mapped[str | None] = mapped_column(Text)
    rep: Mapped[str | None] = mapped_column(Text)
    order_written_by: Mapped[str | None] = mapped_column(Text)
    split_with: Mapped[str | None] = mapped_column(Text)

    # salesforce link
    sf_account_id: Mapped[str | None] = mapped_column(Text)
    # Set when the SF Business Account for this new account was created from
    # /admin (sf_account_id holds the created id). null = not yet created.
    sf_account_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The Kugamon sales order pushed to SF on Accept: record id + auto-number
    # Name. null = not yet pushed; presence makes the push idempotent.
    sf_order_id: Mapped[str | None] = mapped_column(Text)
    sf_order_number: Mapped[str | None] = mapped_column(Text)
    # Account.SalesTerritory__c at order time; null for new/unmatched accounts.
    sales_territory: Mapped[str | None] = mapped_column(Text)
    # The store / account name (distinct from buyer_name, the Bill To person).
    account_name: Mapped[str | None] = mapped_column(Text)
    # Account.Special_Instructions__c at order time; null for new/unmatched.
    special_instructions: Mapped[str | None] = mapped_column(Text)
    # Account.Rank__c at order time; null for new/unmatched (shown as Rank C).
    rank: Mapped[str | None] = mapped_column(Text)

    # is this a new account? set from the rep's Internal Use radio
    is_new_account: Mapped[bool | None] = mapped_column(Boolean)

    # nearby-stockist conflict verdict — populated by the conflict-check API
    # (feat/nearby-conflict-api); null means "not yet checked", NOT "no conflict".
    has_conflict: Mapped[bool | None] = mapped_column(Boolean)

    # when the admin sent the conflict / tax-cert email for this order from
    # /admin. null = not sent. Drives the persistent "Sent ✓" button state.
    conflict_email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tax_cert_email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Admin's recorded outcome of a conflict inquiry, set from /admin once the
    # rep responds. null = still waiting. "cleared" = ok to proceed;
    # "real_conflict" = a genuine territory conflict. The note is free text.
    conflict_resolution: Mapped[str | None] = mapped_column(Text)
    conflict_resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conflict_resolution_note: Mapped[str | None] = mapped_column(Text)

    # AI-suggested outcome from a captured rep reply (see app/ai/conflict_reply).
    # A suggestion only — surfaced in /admin for a human to confirm; confirming
    # sets conflict_resolution above. outcome: cleared | real_conflict | unclear.
    conflict_ai_outcome: Mapped[str | None] = mapped_column(Text)
    conflict_ai_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    conflict_ai_reason: Mapped[str | None] = mapped_column(Text)
    conflict_ai_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # totals / status
    total_qty: Mapped[int] = mapped_column(Integer)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # submitted | accepted | declined
    status: Mapped[str] = mapped_column(Text, server_default="submitted")
    status_reason: Mapped[str | None] = mapped_column(Text)
    status_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class InboundReply(Base):
    """A reply captured from the wholesale@ mailbox and correlated to an order
    via the plus-address token. Currently only conflict replies. The classifier
    (next slice) reads unprocessed rows to suggest a resolution."""

    __tablename__ = "inbound_replies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(Text)  # "conflict"
    from_address: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    # Truncated plain-text body — enough for classification / display, not the
    # whole thread (keep stored PII minimal).
    snippet: Mapped[str | None] = mapped_column(Text)
    # RFC822 Message-ID: dedupes re-fetches of the same message. Unique.
    message_id: Mapped[str | None] = mapped_column(Text, unique=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Set once the classifier has read this reply, so a re-poll doesn't re-run
    # the model on it. null = not yet classified.
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )

    # one Product2 per SKU (style×color×size) → one id per size cell
    sf_product_id_xs: Mapped[str | None] = mapped_column(Text)
    sf_product_id_sm: Mapped[str | None] = mapped_column(Text)
    sf_product_id_ml: Mapped[str | None] = mapped_column(Text)

    code: Mapped[str | None] = mapped_column(Text)
    style_name: Mapped[str] = mapped_column(Text)
    color: Mapped[str] = mapped_column(Text)
    qty_xs: Mapped[int] = mapped_column(Integer, default=0)
    qty_sm: Mapped[int] = mapped_column(Integer, default=0)
    qty_ml: Mapped[int] = mapped_column(Integer, default=0)
    line_qty: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    order: Mapped[Order] = relationship(back_populates="items")
