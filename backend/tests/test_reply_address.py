"""Plus-addressed reply-to correlation: tag an outbound conflict email so the
rep's reply comes back to wholesale+<kind>-<orderid>@… and we know which order
and flow it belongs to — no subject-line guessing."""
from app.email import reply_address

BASE = "wholesale@wooden-ships.com"
# A real order id is a UUID (contains dashes) — the parser must survive that.
OID = "550e8400-e29b-41d4-a716-446655440000"


def test_build_reply_to_embeds_kind_and_order_id():
    addr = reply_address.build_reply_to(OID, "conflict", BASE)
    assert addr == f"wholesale+conflict-{OID}@wooden-ships.com"


def test_parse_round_trips_build_for_uuid_order_id():
    addr = reply_address.build_reply_to(OID, "conflict", BASE)
    assert reply_address.parse_reply_to(addr) == (OID, "conflict")


def test_parse_extracts_from_named_header():
    # Real inbound To/Delivered-To headers are often "Name <addr>".
    header = f'"Wooden Ships" <wholesale+conflict-{OID}@wooden-ships.com>'
    assert reply_address.parse_reply_to(header) == (OID, "conflict")


def test_parse_returns_none_for_plain_address():
    assert reply_address.parse_reply_to("rep@example.com") is None


def test_parse_returns_none_for_unknown_kind():
    assert reply_address.parse_reply_to(f"wholesale+bogus-{OID}@wooden-ships.com") is None


def test_parse_returns_none_without_order_id():
    assert reply_address.parse_reply_to("wholesale+conflict@wooden-ships.com") is None


def test_parse_handles_empty_and_none():
    assert reply_address.parse_reply_to("") is None
    assert reply_address.parse_reply_to(None) is None
