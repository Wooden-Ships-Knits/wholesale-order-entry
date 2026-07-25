"""Conflict-reply classifier: read a rep's reply and suggest whether the
conflict is resolved. The model call is injected so the parsing/validation
logic is tested without a live OpenAI key. The suggestion is only ever a
proposal — a human confirms it before the order state changes."""
import json
from types import SimpleNamespace

from app.ai import conflict_reply as cc


def _complete(payload):
    """A fake completer that always returns the given dict as JSON text."""
    return lambda system, user: json.dumps(payload)


def test_parse_cleared_suggestion():
    s = cc.parse_suggestion(
        json.dumps({"resolved": True, "outcome": "cleared", "confidence": 0.9, "reason": "diff segment"})
    )
    assert s.resolved is True
    assert s.outcome == "cleared"
    assert s.confidence == 0.9
    assert "segment" in s.reason


def test_parse_unknown_outcome_becomes_unclear():
    s = cc.parse_suggestion(json.dumps({"resolved": True, "outcome": "maybe", "confidence": 0.5}))
    assert s.outcome == "unclear"
    # resolved only holds for a concrete outcome
    assert s.resolved is False


def test_parse_real_conflict_counts_as_resolved():
    # A confirmed real conflict IS a definitive answer — "resolved" is derived
    # from the outcome, not taken from whatever the model put in that field.
    s = cc.parse_suggestion(
        json.dumps({"resolved": False, "outcome": "real_conflict", "confidence": 1.0})
    )
    assert s.outcome == "real_conflict"
    assert s.resolved is True


def test_parse_clamps_confidence():
    assert cc.parse_suggestion(json.dumps({"outcome": "cleared", "confidence": 5})).confidence == 1.0
    assert cc.parse_suggestion(json.dumps({"outcome": "cleared", "confidence": -3})).confidence == 0.0


def test_parse_invalid_json_is_safe_unclear():
    s = cc.parse_suggestion("not json at all")
    assert s.outcome == "unclear"
    assert s.resolved is False
    assert s.confidence == 0.0


def test_classify_reply_uses_injected_completer():
    s = cc.classify_reply(
        "No objection, go ahead.",
        _complete({"resolved": True, "outcome": "cleared", "confidence": 0.8, "reason": "ok"}),
    )
    assert s.outcome == "cleared" and s.resolved is True


def test_build_messages_includes_snippet_and_schema_hint():
    system, user = cc.build_messages("Rep says proceed.")
    assert "json" in system.lower()
    assert "cleared" in system and "real_conflict" in system
    assert "Rep says proceed." in user


# ---- run_classify orchestration (fake db) ----

class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, replies, orders):
        self.replies = replies
        self.orders = {o.id: o for o in orders}
        self.committed = False

    def execute(self, _stmt):
        return _Result(self.replies)

    def get(self, _model, oid):
        return self.orders.get(oid)

    def commit(self):
        self.committed = True


def _reply(oid, mid):
    return SimpleNamespace(
        order_id=oid, kind="conflict", snippet="No conflict, proceed.",
        processed_at=None, message_id=mid,
    )


def _order(oid, resolved=False):
    return SimpleNamespace(
        id=oid,
        conflict_resolved_at=("2026-07-25" if resolved else None),
        conflict_ai_outcome=None, conflict_ai_confidence=None,
        conflict_ai_reason=None, conflict_ai_at=None,
    )


def test_run_classify_suggests_for_unresolved_orders():
    reply = _reply("o1", "<a@x>")
    order = _order("o1")
    db = _FakeSession([reply], [order])
    n = cc.run_classify(db, complete=_complete(
        {"resolved": True, "outcome": "cleared", "confidence": 0.9, "reason": "ok"}
    ))
    assert n == 1
    assert order.conflict_ai_outcome == "cleared"
    assert order.conflict_ai_confidence == 0.9
    assert reply.processed_at is not None
    assert db.committed


def test_run_classify_skips_already_resolved_order_but_marks_processed():
    reply = _reply("o2", "<b@x>")
    order = _order("o2", resolved=True)
    db = _FakeSession([reply], [order])
    n = cc.run_classify(db, complete=_complete(
        {"resolved": True, "outcome": "cleared", "confidence": 0.9, "reason": "ok"}
    ))
    assert n == 0  # human already handled it
    assert order.conflict_ai_outcome is None
    assert reply.processed_at is not None  # still marked so we don't re-look


def test_run_classify_noop_when_openai_unconfigured(monkeypatch):
    monkeypatch.setattr(cc.settings, "openai_api_key", "")
    assert cc.run_classify(db=None) == 0
