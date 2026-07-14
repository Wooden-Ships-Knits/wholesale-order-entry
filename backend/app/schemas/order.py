"""Pydantic models for POST /api/orders.

Card number and CVV are SecretStr: excluded from repr/str and never logged.
They are read exactly once (card_last4 derivation now; PDF rendering in
Phase 4) and never persisted.
"""
from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr
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


class ShipTo(CamelModel):
    email: EmailStr
    street: str = ""
    city_state: str = ""
    zip: str = ""
    resale_tax_id: str = ""


class Payment(CamelModel):
    # No format constraints: a constraint violation would echo the value back
    # in the 422 response. Card fields are validated leniently and redacted.
    card_number: SecretStr = SecretStr("")
    card_name: str = ""
    exp_date: str = ""
    cvv: SecretStr = SecretStr("")


class TaxExemption(CamelModel):
    rep_notified: bool = False
    sending_cert: bool = False
    cert_on_file: bool = False


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
    sf_account_id: str | None = None
    bill_to: BillTo = BillTo()
    ship_to: ShipTo
    payment: Payment = Payment()
    tax_exemption: TaxExemption = TaxExemption()
    terms: Terms = Terms()
    internal: Internal = Internal()
    items: list[OrderItemIn] = []
