"""Score a prospect's own website and write the verdict onto its row.

The sweep (app/maps/prospecting.py) says a shop EXISTS. This says whether it is
worth a rep's time: does it buy from brands at all, does it sell our kind of
thing, and can it afford us. Three questions, answered from the shop's own
catalogue and nothing else -- a prospect has no purchase history with us, so a
rule built on revenue could not be applied to both sides.

WHY THERE IS NO HTTP CALL HERE. The scrapebot ships an HTTP API and a SQLite
job queue, and neither was copied. They exist to bridge two separate processes;
in here the scoring code is a function call away and Postgres is already open,
so the queue would only add a second place for a job to get stuck. What was
copied is the part that does the work. See README.md.

Everything slow or paid is injected -- `complete` for the model, `scrape` for
the network -- so the whole path is tested without a socket or a key.

    from app.db.session import SessionLocal
    from app.prospects import assess
    with SessionLocal() as db:
        assess.assess_pending(db, limit=20)
"""
import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.db.models import Prospect

from .analysis.judge import judge_one, system_message
from .analysis.llm_payload import skip_reason, store_payload, unreadable_reason
from .scrapebot.store import scrape_one

logger = logging.getLogger(__name__)

PATTERN_FILE = Path(__file__).with_name("pattern.json")

# Scrape statuses that mean the shelf could not be seen. Not a failure of the
# shop and not a fact about it -- it reads as insufficient_data, never as weak.
UNREADABLE = ("blocked", "error", "js_required")

# Answers that arrive as lists and live in one Text column. Joined the way
# judge.verdict_rows joins them for its CSV, so a row reads the same in both.
JOINED = ("reasons", "problems", "signature_tags_carried", "knit_tags_carried")

# Measurements copied onto the row as they are. Deliberately a whitelist: the
# model is asked for free text and returns whatever it likes, so an answer
# echoing `knitwear_share` back would otherwise overwrite a measurement with an
# invented number, in a column a rep reads as fact.
MEASURED = ("store_type", "brand_count", "products_per_brand", "tag_lift",
            "price_range", "knitwear_share", "knitwear_price_median",
            "knit_evidence", "knit_in_band_share")
ANSWERED = ("verdict", "confidence", "for_the_rep", "against")

# The five keys prompt.md asks the model for, plus judge_one's own `problems`.
# Anything else it returns is not an answer to the question that was put to it.
ANSWER_KEYS = ("verdict", "confidence", "reasons", "for_the_rep", "against")


@lru_cache(maxsize=1)
def load_pattern() -> dict:
    """What our accounts look like. Read once -- it is ~5,200 tokens of context
    resent on every model call, and it changes only when someone rebuilds it."""
    return json.loads(PATTERN_FILE.read_text(encoding="utf-8"))


def tag_signature(pattern: dict) -> frozenset:
    """The tag signature as `store_payload` wants it, recovered from the pattern.

    This is what lets the app score without the 242 account catalogues the
    pattern was built from: it already carries every tag and its share.
    """
    return frozenset(t["tag"] for t in pattern.get("signature_tags", []))


def _openai_complete(system: str, user: str) -> str:
    """The real model call, shaped like app.ai.conflict_reply's completer.

    Same signature the judge expects and the same one the conflict classifier
    already uses, so the app has one key, one model setting and one place where
    a call is made. Imported lazily so this module loads without the SDK.
    """
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        # Narrows the distribution; does NOT collapse it. Measured 2026-08-22:
        # lspace.com scored five times over one cached catalogue returned
        # `possible` x4 and `weak` x1. Shops near a rule boundary flip, so a
        # single verdict is not reproducible evidence — see the status doc.
        temperature=0,
    )
    return resp.choices[0].message.content or ""


def _scrape(website: str) -> dict:
    """scrape_one, pointed at the mounted cache rather than its own default.

    Its default is the relative "data/.cache", which resolves inside the
    container to a directory thrown away on the next rebuild.
    """
    return scrape_one(website, cache_dir=Path(settings.prospect_cache_dir))


def _unreadable(reason: str, payload: dict) -> dict:
    """The verdict for a shop nothing could be learned about.

    Scored like any other -- an empty shelf measures as zeros and Nones, which
    store_payload already handles -- so a caller reading result["store_type"]
    gets an answer on exactly the shops it has no other way to learn about.
    """
    return {**payload, "verdict": "insufficient_data", "confidence": "high",
            "reasons": [reason], "for_the_rep": "", "against": "", "problems": []}


def _gated(reason: str, payload: dict) -> dict:
    """The verdict the knitwear gate already decides, without paying for it.

    judge.check() forces `weak` when knit_evidence is "none", so a model call
    here can only agree or be flagged for disagreeing. The CLI drops these
    shops from candidates.jsonl entirely; a row in a table cannot be dropped,
    so it is written with the reason that decided it. Measured on one run: 5 of
    28 candidates, every one of them a call not made.
    """
    return {**payload, "verdict": "weak", "confidence": "high",
            "reasons": [reason],
            "for_the_rep": f"Not worth a call: {reason}.",
            "against": reason, "problems": []}


def assess_website(website: str, pattern=None, complete=None, scrape=None,
                   system=None) -> dict:
    """Scrape one shop and judge it. The measurements, then the answer.

    Raises ValueError, from scrape_one, when `website` is not a hostname -- an
    OSM `website` tag is free text a mapper typed, so "Ask the owner" and bare
    phone numbers genuinely arrive. That is a finding about the element rather
    than a fault here, so it is left to the caller to record.
    """
    pattern = pattern if pattern is not None else load_pattern()
    scrape = scrape or _scrape
    store = scrape(website)

    payload = store_payload(store.get("domain") or "", store,
                            store.get("about_text"), tag_signature(pattern))

    # Two different findings, and `reasons` is the only place either is ever
    # explained to a rep. Collapsing them produced "site could not be read: ok"
    # on a shop that answered perfectly well and simply lists nothing.
    status = store.get("status")
    if status in UNREADABLE:
        return _unreadable(f"site could not be read: {status}", payload)
    if not store.get("products"):
        return _unreadable("site was read but lists no products", payload)

    # Rule 1, before rule 2 and before the model. A shelf whose every brand is
    # the shop's own name cannot be read at all, and that is a DIFFERENT answer
    # from the gate below: `insufficient_data`, never `weak`. Nine of our own
    # 242 accounts have this shape -- burlapranch.com lists all 2,000 of its
    # products under its own name -- so `weak` here would call paying customers
    # bad prospects.
    #
    # The depth threshold comes from the accounts rather than a literal, so a
    # rebuilt pattern carries a corrected one.
    depth = (pattern.get("products_per_brand_p10_median_p90") or {}).get("p90")
    reason = unreadable_reason(payload,
                               min_products_per_brand=depth * 2 if depth else None)
    if reason:
        return _unreadable(reason, payload)

    reason = skip_reason(payload)
    if reason:
        return _gated(reason, payload)

    complete = complete or _openai_complete
    system = system if system is not None else system_message(pattern)
    answer = judge_one(payload, pattern, complete, system=system)
    if answer.get("verdict") is None:
        # judge_one reports a malformed answer rather than raising, because the
        # CLI wants it written to verdicts.jsonl beside the good ones. A row in
        # a table cannot hold "no verdict" and still mean "assessed", so here it
        # is an error the caller retries.
        raise ValueError(answer.get("raw") or "the answer carried no verdict")

    # The measurements are written LAST, over the answer, and the answer is cut
    # to the keys it was asked for. Both halves matter. The model is asked for
    # free text and returns whatever it likes: an answer echoing knitwear_share
    # back would otherwise replace a measurement with an invented number, in a
    # column a rep reads as fact, with nothing in the row to show which it is.
    # A test caught exactly that -- the merge used to run the other way.
    said = {k: answer.get(k) for k in ANSWER_KEYS}
    said["problems"] = answer.get("problems") or []
    return {**said, **payload}


def to_columns(result: dict) -> dict:
    """One result as Prospect column values.

    store_name and address are NOT set. They belong to the sweep, which owns
    where a shop is and what it is called; writing them from here would mean
    two writers fighting over one column every time the filters are retuned.
    """
    prices = result.get("price_p25_p50_p75") or [None, None, None]
    row = {k: result.get(k) for k in ANSWERED}
    row.update({k: result.get(k) for k in MEASURED})
    row.update({k: "; ".join(str(x) for x in (result.get(k) or []) if x not in (None, ""))
                or None for k in JOINED})
    row["price_median"] = prices[1]
    row["assessed_at"] = datetime.now(timezone.utc)
    return row


def pending(db, limit=None, territory=None):
    """Prospects with a website that nobody has assessed yet.

    Filtered on `website` because the assessment reads a shop's own catalogue
    and there is nothing to read without one -- of 225 real sweep rows, 92 have
    the tag. Sending the other 133 would buy a scrape each to be told so.

    `territory` scopes a run to one rep's book. A whole-book sweep is ~1,300
    shops and six hours; run in store_name order that leaves every territory
    half-assessed for the entire run, and a batch stopped halfway helps nobody.
    One territory at a time finishes each book complete and usable.
    """
    q = (select(Prospect)
         .where(Prospect.website.isnot(None), Prospect.website != "",
                Prospect.assessed_at.is_(None)))
    if territory:
        q = q.where(Prospect.territory == territory)
    q = q.order_by(Prospect.store_name)
    if limit:
        q = q.limit(limit)
    return db.execute(q).scalars().all()


def assess_pending(db, limit=None, complete=None, scrape=None,
                   territory=None) -> int:
    """Assess every unassessed prospect with a website. Returns how many were
    written. No-op when OpenAI is not configured, matching run_classify.

    Committed one row at a time, deliberately. Each row costs a scrape and up to
    one model call, and a batch that dies on row 60 must not throw away the 59
    already paid for.
    """
    if complete is None:
        if not settings.openai_configured:
            logger.info("Assessment skipped: OpenAI is not configured")
            return 0
        complete = _openai_complete

    pattern = load_pattern()
    system = system_message(pattern)          # ~5,200 tokens, built once
    rows = pending(db, limit, territory)
    logger.info("Assessing %d prospect(s)%s", len(rows),
                f" in {territory}" if territory else "")

    written = 0
    for p in rows:
        try:
            result = assess_website(p.website, pattern, complete, scrape, system)
        except Exception:                      # noqa: BLE001 — one bad shop, not the batch
            logger.warning("Could not assess %s (%s)", p.osm_id, p.website,
                           exc_info=True)
            continue
        for key, value in to_columns(result).items():
            setattr(p, key, value)
        db.commit()
        written += 1
        logger.info("%s %s -> %s", p.osm_id, result.get("domain"), p.verdict)
    return written
