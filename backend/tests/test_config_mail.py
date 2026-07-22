"""SMTP config helpers on Settings."""
from app.config import settings


def test_mail_configured_true_when_host_user_pass_set(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_user", "wholesale@wooden-ships.com")
    monkeypatch.setattr(settings, "smtp_pass", "app-password")
    assert settings.mail_configured is True


def test_mail_configured_false_when_any_missing(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_user", "wholesale@wooden-ships.com")
    monkeypatch.setattr(settings, "smtp_pass", "")
    assert settings.mail_configured is False


def test_mail_sender_falls_back_to_smtp_user(monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "wholesale@wooden-ships.com")
    monkeypatch.setattr(settings, "mail_from", "")
    assert settings.mail_sender == "wholesale@wooden-ships.com"


def test_mail_sender_prefers_explicit_from(monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "login@wooden-ships.com")
    monkeypatch.setattr(settings, "mail_from", "wholesale@wooden-ships.com")
    assert settings.mail_sender == "wholesale@wooden-ships.com"
