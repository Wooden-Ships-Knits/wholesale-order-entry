"""Pydantic models for POST /api/orders.

Card number and CVV are SecretStr: excluded from repr/str and never logged.
They are read exactly once (card_last4 derivation now; PDF rendering in
Phase 4) and never persisted.
"""
import base64
import binascii
from datetime import date
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class BillTo(CamelModel):
    buyer_name: str = ""
    street: str = ""
    city_state: str = ""
    zip: str = ""
    tel: str = ""
    fax: str = ""
    # Captured by the Google Places address search (optional).
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)


class ShipTo(CamelModel):
    email: EmailStr
    street: str = ""
    city_state: str = ""
    zip: str = ""
    resale_tax_id: str = ""
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)


class Payment(CamelModel):
    # No format constraints: a constraint violation would echo the value back
    # in the 422 response. Card fields are validated leniently and redacted.
    card_number: SecretStr = SecretStr("")
    card_name: str = ""
    exp_date: str = ""
    cvv: SecretStr = SecretStr("")
    method: str = ""  # "link" | "card" | ""
    approval_before_charge: bool | None = None


# Tax-exemption certificate upload (base64 inside the JSON payload).
CERT_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
CERT_MAX_BYTES = 10 * 1024 * 1024  # decoded size


class CertFile(CamelModel):
    name: str = Field(min_length=1, max_length=255)
    content_base64: str

    @field_validator("name")
    @classmethod
    def _allowed_extension(cls, v: str) -> str:
        if PurePosixPath(v.replace("\\", "/")).suffix.lower() not in CERT_ALLOWED_EXTENSIONS:
            raise ValueError("Certificate must be a PDF, JPG or PNG file.")
        return v

    @field_validator("content_base64")
    @classmethod
    def _valid_and_small_enough(cls, v: str) -> str:
        try:
            decoded = base64.b64decode(v, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("Certificate file content is not valid base64.")
        if len(decoded) > CERT_MAX_BYTES:
            raise ValueError("Certificate file is larger than 10 MB.")
        return v

    def decoded(self) -> bytes:
        return base64.b64decode(self.content_base64, validate=True)


class TaxExemption(CamelModel):
    rep_notified: bool = False
    sending_cert: bool = False
    cert_on_file: bool = False
    cert_file: CertFile | None = None


class Terms(CamelModel):
    signature_name: str = ""
    signature_date: date | None = None
    accepted: bool = False


class Internal(CamelModel):
    new_or_reorder: str = ""
    account_status: str = ""
    campaign: str = ""
    campaign_other: str = ""
    po_number: str = ""
    rep: str = ""
    order_written_by: str = ""
    split: bool | None = None
    split_with: str = ""


class OrderItemIn(CamelModel):
    style_name: str
    color: str
    qty_xs: int = Field(0, ge=0)
    qty_sm: int = Field(0, ge=0)
    qty_ml: int = Field(0, ge=0)

    @property
    def pieces(self) -> int:
        return self.qty_xs + self.qty_sm + self.qty_ml


class OrderSubmission(CamelModel):
    season: str = Field(pattern=r"^[FS]\d{2}$")
    order_date: date | None = None
    part_ship_ok: bool | None = None
    ship_window: str = ""
    filled_by: str = ""  # "rep" | "customer" | ""
    # Customer-filled forms only: "is this your first order?". None = unanswered.
    first_order: bool | None = None
    notes: str = ""
    sf_account_id: str | None = None
    # Account.SalesTerritory__c, carried from the buyer lookup; null if unmatched.
    sales_territory: str | None = None
    # Account.Special_Instructions__c, carried from the buyer lookup.
    special_instructions: str | None = None
    bill_to: BillTo = BillTo()
    ship_to: ShipTo
    payment: Payment = Payment()
    tax_exemption: TaxExemption = TaxExemption()
    terms: Terms = Terms()
    internal: Internal = Internal()
    items: list[OrderItemIn] = []
