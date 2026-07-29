"""Plus-addressed reply-to correlation.

When the admin sends a conflict-inquiry email, we tag it with a Reply-To of the
form ``wholesale+<kind>-<orderid>@wooden-ships.com``. Gmail delivers any
``wholesale+…@`` address to the ``wholesale@`` inbox with the token intact, so a
rep's reply lands back in the same mailbox carrying the order id — no subject
line parsing, no guessing which order a reply belongs to.

Pure string logic: the caller supplies the base address (``settings.mail_sender``)
so this module has no settings dependency and stays trivially testable.
"""
from email.utils import parseaddr

# Flows we tag. Tax cert is handled separately, but keeping it here means the
# parser rejects it explicitly rather than mis-routing an unknown token.
_KINDS = {"conflict", "tax_cert"}


def build_reply_to(order_id: str, kind: str, base_address: str) -> str:
    """``("abc", "conflict", "wholesale@x.com")`` -> ``wholesale+conflict-abc@x.com``.

    The kind goes first so the order id (a dash-bearing UUID) is the whole
    remainder and round-trips cleanly through :func:`parse_reply_to`.
    """
    local, _, domain = base_address.partition("@")
    return f"{local}+{kind}-{order_id}@{domain}"


def parse_token(token: str) -> tuple[str, str] | None:
    """Parse a bare ``<kind>-<order_id>`` token into ``(order_id, kind)``, or
    ``None`` if it isn't a valid tag. Shared by the plus-address and the
    subject-line token, so both use one format."""
    kind, sep, order_id = token.partition("-")
    if not sep or kind not in _KINDS or not order_id:
        return None
    return order_id, kind


def parse_reply_to(header_value: str | None) -> tuple[str, str] | None:
    """Extract ``(order_id, kind)`` from a To / Delivered-To header written to a
    tagged reply address, or ``None`` when there is no valid token.

    Handles bare addresses and ``"Name" <addr>`` header forms.
    """
    _, addr = parseaddr(header_value or "")
    local, _, _ = addr.partition("@")
    if "+" not in local:
        return None
    _, _, token = local.partition("+")
    return parse_token(token)
