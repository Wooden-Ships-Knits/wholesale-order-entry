"""Inbound reply capture: read the wholesale@ mailbox, correlate each reply to
its order via the plus-address token, and pull out the rep's message so the
classifier (next slice) can read it. The risky logic — parsing a raw email and
finding the token — is pure and tested hard here."""
from datetime import datetime, timezone
from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import patch

from app.email import inbound

OID = "550e8400-e29b-41d4-a716-446655440000"


def _tax_cert_raw(pdf=b"%PDF-1.4 fake resale cert", to=None, with_pdf=True):
    """A customer's tax-cert reply, optionally carrying a PDF attachment."""
    m = EmailMessage()
    m["From"] = "Buyer <buyer@store.com>"
    m["To"] = to or f"wholesale+tax_cert-{OID}@wooden-ships.com"
    m["Subject"] = "Re: Tax Certificate Request - A Pied"
    m["Message-ID"] = "<tc1@store.com>"
    m.set_content("Here is my resale certificate. Thanks!")
    if with_pdf:
        m.add_attachment(pdf, maintype="application", subtype="pdf", filename="resale.pdf")
    return m.as_bytes()


def _raw(to=f"wholesale+conflict-{OID}@wooden-ships.com", body="Go ahead — no conflict.",
         frm="Jane Rep <jane@repco.com>", extra_headers="", msgid="<r1@repco.com>"):
    return (
        f"From: {frm}\r\n"
        f"To: {to}\r\n"
        f"Subject: Re: CONFLICT Inquiry — A Pied Boutique\r\n"
        f"Message-ID: {msgid}\r\n"
        f"Date: Fri, 25 Jul 2026 10:00:00 -0400\r\n"
        f"{extra_headers}"
        f"Content-Type: text/plain; charset=\"utf-8\"\r\n"
        f"\r\n"
        f"{body}\r\n"
    ).encode()


def test_extract_reply_correlates_to_order_and_pulls_body():
    r = inbound.extract_reply(_raw())
    assert r is not None
    assert r.order_id == OID
    assert r.kind == "conflict"
    assert r.from_address == "jane@repco.com"
    assert "no conflict" in r.snippet.lower()
    assert r.message_id == "<r1@repco.com>"
    assert r.received_at is not None
    assert "A Pied Boutique" in r.subject


def test_extract_reply_reads_token_from_delivered_to():
    # Some providers only carry the plus address on Delivered-To.
    raw = _raw(
        to="wholesale@wooden-ships.com",
        extra_headers=f"Delivered-To: wholesale+conflict-{OID}@wooden-ships.com\r\n",
    )
    r = inbound.extract_reply(raw)
    assert r is not None and r.order_id == OID


def test_extract_reply_uses_plain_text_part_of_multipart():
    raw = (
        f"From: jane@repco.com\r\n"
        f"To: wholesale+conflict-{OID}@wooden-ships.com\r\n"
        f"Subject: Re\r\n"
        f"Message-ID: <m@x>\r\n"
        f'Content-Type: multipart/alternative; boundary="B"\r\n'
        f"\r\n"
        f"--B\r\n"
        f'Content-Type: text/plain; charset="utf-8"\r\n\r\n'
        f"Plain says proceed.\r\n"
        f"--B\r\n"
        f'Content-Type: text/html; charset="utf-8"\r\n\r\n'
        f"<p>HTML says proceed.</p>\r\n"
        f"--B--\r\n"
    ).encode()
    r = inbound.extract_reply(raw)
    assert r is not None
    assert "Plain says proceed." in r.snippet
    assert "<p>" not in r.snippet


def test_extract_reply_returns_none_without_token():
    raw = _raw(to="wholesale@wooden-ships.com", extra_headers="")
    assert inbound.extract_reply(raw) is None


def test_extract_reply_falls_back_to_subject_token():
    # Reply came back to the BARE wholesale@ (no plus-token), but the subject
    # still carries the kind-tagged order token — correlate off that.
    raw = (
        f"From: jane@repco.com\r\n"
        f"To: wholesale@wooden-ships.com\r\n"
        f"Subject: Re: CONFLICT Inquiry — TES2 [#conflict-{OID}]\r\n"
        f"Message-ID: <s1@x>\r\n"
        f'Content-Type: text/plain; charset="utf-8"\r\n\r\n'
        f"No conflict, go ahead.\r\n"
    ).encode()
    r = inbound.extract_reply(raw)
    assert r is not None
    assert r.order_id == OID
    assert r.kind == "conflict"


def test_tax_cert_subject_token_correlates_as_tax_cert():
    # A tax-cert reply to the bare wholesale@ — the subject token carries the
    # kind, so it isn't mistaken for a conflict.
    raw = (
        f"From: buyer@store.com\r\n"
        f"To: wholesale@wooden-ships.com\r\n"
        f"Subject: Re: Tax Certificate Request - A Pied [#tax_cert-{OID}]\r\n"
        f"Message-ID: <tc-subj@x>\r\n"
        f'Content-Type: text/plain; charset="utf-8"\r\n\r\n'
        f"cert attached\r\n"
    ).encode()
    r = inbound.extract_reply(raw)
    assert r is not None
    assert r.order_id == OID
    assert r.kind == "tax_cert"


def test_plus_token_wins_over_subject_token():
    # If both are present, the authoritative plus-address token is used.
    other = "11111111-2222-4333-8444-555555555555"
    raw = (
        f"From: jane@repco.com\r\n"
        f"To: wholesale+conflict-{OID}@wooden-ships.com\r\n"
        f"Subject: Re: CONFLICT Inquiry — TES2 [#conflict-{other}]\r\n"
        f"Message-ID: <p1@x>\r\n"
        f'Content-Type: text/plain; charset="utf-8"\r\n\r\n'
        f"ok\r\n"
    ).encode()
    assert inbound.extract_reply(raw).order_id == OID


def test_select_new_drops_already_seen_message_ids():
    r1 = inbound.extract_reply(_raw(msgid="<a@x>"))
    r2 = inbound.extract_reply(_raw(msgid="<b@x>"))
    fresh = inbound.select_new([r1, r2], existing_message_ids={"<a@x>"})
    assert [r.message_id for r in fresh] == ["<b@x>"]


def test_parse_replies_skips_untokened_messages():
    good = _raw(msgid="<g@x>")
    bad = _raw(to="wholesale@wooden-ships.com", msgid="<b@x>")
    out = inbound.parse_replies([good, bad])
    assert [r.message_id for r in out] == ["<g@x>"]


def test_fetch_unseen_raw_returns_message_bytes():
    """Union of the per-marker searches, each message fetched exactly once."""
    class FakeIMAP:
        def __init__(self):
            self.searches = []

        def search(self, charset, *criteria):
            self.searches.append(criteria)
            # Two searches match, and they overlap on message 2.
            if "FROM" in criteria:
                return ("OK", [b"2 3"])
            if criteria[1] == "HEADER":
                return ("OK", [b"1 2"])
            return ("OK", [b""])

        def fetch(self, num, spec):
            return ("OK", [(num + b" (RFC822 {n}", b"RAW-" + num), b")"])

    imap = FakeIMAP()
    raws = inbound.fetch_unseen_raw(imap)
    # 2 appears in two searches but is fetched once — fetching marks it \Seen.
    assert raws == [b"RAW-1", b"RAW-2", b"RAW-3"]
    # Never a bare UNSEEN: that would read the team's own mail.
    assert all(c != ("UNSEEN",) for c in imap.searches)
    assert all(c[0] == "UNSEEN" for c in imap.searches)


def test_fetch_unseen_raw_handles_empty_mailbox():
    class EmptyIMAP:
        def search(self, charset, *criteria):
            return ("OK", [b""])

        def fetch(self, num, spec):  # pragma: no cover - must not be called
            raise AssertionError("fetch should not run on an empty mailbox")

    assert inbound.fetch_unseen_raw(EmptyIMAP()) == []


def test_fetch_unseen_raw_survives_one_unsupported_search():
    """A server that rejects HEADER TO must still yield the bounces."""
    class PickyIMAP:
        def search(self, charset, *criteria):
            if criteria[1] == "HEADER":
                raise RuntimeError("BAD search")
            if "FROM" in criteria:
                return ("OK", [b"7"])
            return ("OK", [b""])

        def fetch(self, num, spec):
            return ("OK", [(num + b" (RFC822 {n}", b"RAW-" + num), b")"])

    assert inbound.fetch_unseen_raw(PickyIMAP()) == [b"RAW-7"]


def test_run_poll_is_noop_when_imap_unconfigured(monkeypatch):
    monkeypatch.setattr(inbound.settings, "imap_host", "")
    assert inbound.run_poll(db=None) == 0


# ---- tax-certificate reply: attachment capture + save ----

def test_extract_reply_captures_pdf_attachment():
    r = inbound.extract_reply(_tax_cert_raw())
    assert r.kind == "tax_cert" and r.order_id == OID
    names = [a[0] for a in r.attachments]
    assert names == ["resale.pdf"]
    assert r.attachments[0][1].startswith(b"%PDF")


def test_extract_reply_has_no_attachments_for_plain_reply():
    r = inbound.extract_reply(_raw())  # conflict text reply, no attachment
    assert r.attachments == []


def _cert_order():
    return SimpleNamespace(
        id=OID, season_code="F26", buyer_name="A Pied",
        created_at=datetime(2026, 7, 25, tzinfo=timezone.utc), cert_filename=None,
    )


def test_save_tax_cert_writes_pdf_and_sets_cert_filename():
    order = _cert_order()
    reply = inbound.extract_reply(_tax_cert_raw())
    with patch("app.email.inbound.pdf_render.save_output_file") as save:
        ok = inbound.save_tax_cert(order, reply)
    assert ok is True
    assert order.cert_filename and order.cert_filename.endswith(".pdf")
    # written into the secure output dir under the standard cert name
    save.assert_called_once()
    assert save.call_args[0][1] == order.cert_filename  # (bytes, filename)


def test_save_tax_cert_returns_false_without_attachment():
    order = _cert_order()
    reply = inbound.extract_reply(_tax_cert_raw(with_pdf=False))
    assert inbound.save_tax_cert(order, reply) is False
    assert order.cert_filename is None
