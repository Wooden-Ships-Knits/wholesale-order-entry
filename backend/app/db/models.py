"""SQLAlchemy models. NO card number / CVV columns — ever (CLAUDE.md rule 1).

Only card_name and card_last4 may persist; the full card number and CVV live
transiently in the request payload for PDF rendering (Phase 4) and are dropped.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Text, func
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

    # tax exemption acknowledgements + uploaded certificate
    cert_required_ack: Mapped[bool | None] = mapped_column(Boolean)
    cert_sending_ack: Mapped[bool | None] = mapped_column(Boolean)
    cert_on_file: Mapped[bool | None] = mapped_column(Boolean)
    cert_filename: Mapped[str | None] = mapped_column(Text)

    # signature / terms
    signature_name: Mapped[str | None] = mapped_column(Text)
    signature_date: Mapped[date | None] = mapped_column(Date)
    terms_accepted: Mapped[bool | None] = mapped_column(Boolean)

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
    # Account.SalesTerritory__c at order time; null for new/unmatched accounts.
    sales_territory: Mapped[str | None] = mapped_column(Text)
    # The store / account name (distinct from buyer_name, the Bill To person).
    account_name: Mapped[str | None] = mapped_column(Text)
    # Account.Special_Instructions__c at order time; null for new/unmatched.
    special_instructions: Mapped[str | None] = mapped_column(Text)

    # is this a new account? set from the rep's Internal Use radio
    is_new_account: Mapped[bool | None] = mapped_column(Boolean)

    # nearby-stockist conflict verdict — populated by the conflict-check API
    # (feat/nearby-conflict-api); null means "not yet checked", NOT "no conflict".
    has_conflict: Mapped[bool | None] = mapped_column(Boolean)

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
