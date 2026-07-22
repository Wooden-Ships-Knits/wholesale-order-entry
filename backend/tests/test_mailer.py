"""SMTP transport: message building, send, and the unconfigured no-op."""
from unittest.mock import MagicMock, patch

from app.email import mailer


def _configure(monkeypatch):
    monkeypatch.setattr(mailer.settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(mailer.settings, "smtp_port", 587)
    monkeypatch.setattr(mailer.settings, "smtp_user", "wholesale@wooden-ships.com")
    monkeypatch.setattr(mailer.settings, "smtp_pass", "pw")
    monkeypatch.setattr(mailer.settings, "mail_from", "")


def test_send_email_builds_message_and_sends(monkeypatch):
    _configure(monkeypatch)
    fake_smtp = MagicMock()
    ctx_mgr = MagicMock()
    ctx_mgr.__enter__.return_value = fake_smtp
    with patch("app.email.mailer.smtplib.SMTP", return_value=ctx_mgr) as SMTP:
        ok = mailer.send_email(
            "cust@store.com", "Subj", "Body text",
            [("order.pdf", b"%PDF-1.4", "pdf")],
        )
    assert ok is True
    SMTP.assert_called_once_with("smtp.test", 587, timeout=10)
    fake_smtp.starttls.assert_called_once()
    fake_smtp.login.assert_called_once_with("wholesale@wooden-ships.com", "pw")
    sent = fake_smtp.send_message.call_args[0][0]
    assert sent["To"] == "cust@store.com"
    assert sent["From"] == "wholesale@wooden-ships.com"
    assert sent["Subject"] == "Subj"
    attachments = list(sent.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "order.pdf"


def test_send_email_skips_when_unconfigured(monkeypatch):
    monkeypatch.setattr(mailer.settings, "smtp_host", "")
    with patch("app.email.mailer.smtplib.SMTP") as SMTP:
        ok = mailer.send_email("cust@store.com", "S", "B")
    assert ok is False
    SMTP.assert_not_called()


def test_send_email_returns_false_on_smtp_error(monkeypatch):
    _configure(monkeypatch)
    with patch("app.email.mailer.smtplib.SMTP", side_effect=OSError("boom")):
        ok = mailer.send_email("cust@store.com", "S", "B")
    assert ok is False
