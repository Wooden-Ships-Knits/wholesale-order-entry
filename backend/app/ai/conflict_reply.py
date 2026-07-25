"""Conflict-reply classifier.

Reads a captured rep reply (:class:`~app.db.models.InboundReply`) and asks an
LLM whether the potential territory conflict is resolved. The result is only a
*suggestion*: it is surfaced in /admin for a human to confirm, and confirming is
what actually sets ``Order.conflict_resolution`` — the model never flips a
territory decision on its own.

The model call is injected (``complete``), so all parsing/validation logic is
unit-tested without a live key. :func:`_openai_complete` is the real adapter and
imports the OpenAI SDK lazily, so this module imports fine without it installed.
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select

from app.config import settings
from app.db.models import InboundReply, Order

logger = logging.getLogger(__name__)

# Concrete outcomes are confirmable in the Phase-1a resolution endpoint;
# "unclear" means the model couldn't decide and no suggestion is shown.
_CONCRETE = {"cleared", "real_conflict"}
_OUTCOMES = _CONCRETE | {"unclear"}

SYSTEM_PROMPT = (
    "You review a sales rep's email reply about a potential retail territory "
    "conflict for a NEW wholesale account. Classify how the rep answered. "
    "Respond ONLY as a JSON object with keys: "
    'outcome (one of "cleared", "real_conflict", "unclear"), '
    "confidence (number 0..1), reason (short string). "
    '"cleared" = the rep is OK to proceed / says it is not a real conflict. '
    '"real_conflict" = the rep confirms a genuine conflict. '
    '"unclear" = you cannot tell from the reply.'
)

# (system_prompt, user_prompt) → raw JSON text from the model.
Completer = Callable[[str, str], str]


@dataclass
class Suggestion:
    resolved: bool
    outcome: str  # cleared | real_conflict | unclear
    confidence: float
    reason: str


def build_messages(snippet: str) -> tuple[str, str]:
    user = f"Rep reply:\n\n{(snippet or '').strip()}\n\nClassify it as JSON."
    return SYSTEM_PROMPT, user


def parse_suggestion(raw: str) -> Suggestion:
    """Validate the model's JSON into a Suggestion. Never raises: malformed
    output degrades to a low-confidence 'unclear' so a bad response can't crash
    or mis-resolve an order."""
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except (TypeError, ValueError):
        return Suggestion(False, "unclear", 0.0, "Could not parse model output.")

    outcome = data.get("outcome")
    if outcome not in _OUTCOMES:
        outcome = "unclear"
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    # "resolved" = we have a definitive answer, i.e. a concrete outcome. Derived,
    # not taken from the model: a confirmed real_conflict is just as resolved as
    # a clear, even though a model may read "resolved" as "the conflict is gone".
    resolved = outcome in _CONCRETE
    reason = str(data.get("reason", ""))[:500]
    return Suggestion(resolved, outcome, confidence, reason)


def classify_reply(snippet: str, complete: Completer) -> Suggestion:
    system, user = build_messages(snippet)
    return parse_suggestion(complete(system, user))


def _openai_complete(system: str, user: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return resp.choices[0].message.content or ""


def run_classify(db, complete: Completer | None = None) -> int:
    """Classify every unprocessed conflict reply, writing a suggestion onto its
    order. Returns how many suggestions were produced. No-op (0) when OpenAI is
    not configured. Replies whose order a human already resolved are marked
    processed but not classified."""
    if complete is None:
        if not settings.openai_configured:
            logger.info("Classify skipped: OpenAI is not configured")
            return 0
        complete = _openai_complete

    replies = db.execute(
        select(InboundReply).where(
            InboundReply.kind == "conflict",
            InboundReply.processed_at.is_(None),
        )
    ).scalars().all()

    now = datetime.now(timezone.utc)
    suggested = 0
    for reply in replies:
        reply.processed_at = now
        order = db.get(Order, reply.order_id)
        if order is None or order.conflict_resolved_at is not None:
            continue  # already handled by a human, or orphaned — just mark done
        suggestion = classify_reply(reply.snippet or "", complete)
        order.conflict_ai_outcome = suggestion.outcome
        order.conflict_ai_confidence = suggestion.confidence
        order.conflict_ai_reason = suggestion.reason
        order.conflict_ai_at = now
        suggested += 1
    db.commit()
    if suggested:
        logger.info("Classifier produced %d conflict suggestion(s)", suggested)
    return suggested
