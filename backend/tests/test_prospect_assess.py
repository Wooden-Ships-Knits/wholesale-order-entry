"""Prospect scoring: scrape a shop's own catalogue and judge it.

Both slow halves are injected — `scrape` for the network, `complete` for the
model — so nothing here opens a socket or needs a key. The cases that matter
are the ones where NO model call should happen at all: a shop nobody could
read, and a shop the knitwear gate already answers.
"""
import json

import pytest

from app.prospects import assess


def _store(products, status="ok", domain="example.com"):
    return {"domain": domain, "status": status, "about_text": "a boutique",
            "products": products}


def _product(title, price=148.0, vendor="ACME", ptype="Sweaters", tags=("SWEATERS",)):
    return {"title": title, "price": price, "vendor": vendor,
            "product_type": ptype, "tags": list(tags), "description": ""}


def _knitwear_shop(n=60):
    return _store([_product(f"Merino Sweater {i}", vendor=f"BRAND{i % 8}")
                   for i in range(n)])


def _no_knitwear_shop(n=60):
    return _store([_product(f"Silver Hoop Earring {i}", vendor=f"BRAND{i % 8}",
                            ptype="Jewelry", tags=("JEWELRY",))
                   for i in range(n)])


def _answers(payload):
    """A completer returning a fixed answer, and a record of whether it was called."""
    calls = []

    def complete(system, user):
        calls.append(user)
        return json.dumps(payload)
    return complete, calls


PATTERN = {"signature_tags": [{"tag": "SWEATERS", "share_of_accounts": 0.4}]}
GOOD = {"verdict": "strong", "confidence": "high", "reasons": ["stocks knitwear"],
        "for_the_rep": "Worth a call.", "against": ""}


# --- the two paths that must not spend money -------------------------------

def test_an_unreadable_shop_is_insufficient_data_and_costs_no_model_call():
    complete, calls = _answers(GOOD)
    out = assess.assess_website("https://example.com", PATTERN, complete,
                                scrape=lambda url: _store([], status="blocked"),
                                system="sys")
    assert out["verdict"] == "insufficient_data"
    assert calls == []


def test_a_shop_with_no_knitwear_is_weak_and_costs_no_model_call():
    """The gate judge.check() would enforce anyway, applied before paying."""
    complete, calls = _answers(GOOD)
    out = assess.assess_website("https://example.com", PATTERN, complete,
                                scrape=lambda url: _no_knitwear_shop(), system="sys")
    assert out["verdict"] == "weak"
    assert out["knit_evidence"] == "none"
    assert calls == []
    assert "knitwear" in out["against"]


def test_a_readable_shop_with_an_empty_shelf_says_that_not_that_it_was_unreadable():
    """Both roads end in insufficient_data, but the REASON is the only thing on
    the row explaining it, and it is read by a rep. A shop that answered fine
    and simply lists no products used to report "site could not be read: ok",
    which is not a sentence and not what happened."""
    complete, calls = _answers(GOOD)
    out = assess.assess_website("https://example.com", PATTERN, complete,
                                scrape=lambda url: _store([], status="ok"),
                                system="sys")
    assert out["verdict"] == "insufficient_data"
    assert calls == []
    reason = out["reasons"][0]
    assert "could not be read" not in reason
    assert "no products" in reason


def test_an_unreadable_shop_names_the_status_that_stopped_it():
    complete, _ = _answers(GOOD)
    out = assess.assess_website("https://example.com", PATTERN, complete,
                                scrape=lambda url: _store([], status="blocked"),
                                system="sys")
    assert out["reasons"][0] == "site could not be read: blocked"


def test_an_unreadable_shop_still_carries_the_measured_keys():
    """A caller reading result["store_type"] must not get a KeyError on exactly
    the shops it has no other way to learn anything about."""
    out = assess.assess_website("https://example.com", PATTERN, lambda s, u: "{}",
                                scrape=lambda url: _store([], status="error"),
                                system="sys")
    for key in ("store_type", "brand_count", "knitwear_share", "knit_evidence"):
        assert key in out


# --- the ordinary path ------------------------------------------------------

def test_a_knitwear_shop_is_judged_and_the_answer_kept():
    complete, calls = _answers(GOOD)
    out = assess.assess_website("https://example.com", PATTERN, complete,
                                scrape=lambda url: _knitwear_shop(), system="sys")
    assert out["verdict"] == "strong"
    assert len(calls) == 1
    assert out["knit_evidence"] in ("tags+products", "products_only")


def test_a_model_answer_cannot_overwrite_a_measurement():
    """The model is asked for free text and returns whatever it likes. A row a
    rep reads as fact must not carry a number the model invented."""
    liar = dict(GOOD, knitwear_share=0.99, brand_count=999, store_type="multi_brand")
    complete, _ = _answers(liar)
    out = assess.assess_website("https://example.com", PATTERN, complete,
                                scrape=lambda url: _knitwear_shop(), system="sys")
    row = assess.to_columns(out)
    assert row["knitwear_share"] != 0.99
    assert row["brand_count"] == 8          # measured: BRAND0..BRAND7


def test_an_unparseable_answer_raises_rather_than_writing_a_null_verdict():
    out_of_json = lambda system, user: "I think this shop is nice."  # noqa: E731
    with pytest.raises(ValueError):
        assess.assess_website("https://example.com", PATTERN, out_of_json,
                              scrape=lambda url: _knitwear_shop(), system="sys")


# --- shaping a row ----------------------------------------------------------

def test_to_columns_joins_the_list_answers_into_one_text_column():
    row = assess.to_columns({"verdict": "weak", "reasons": ["a", "b"],
                             "problems": [], "signature_tags_carried": ["SWEATERS"],
                             "price_p25_p50_p75": [40, 90, 160]})
    assert row["reasons"] == "a; b"
    assert row["problems"] is None          # empty stays empty, not ""
    assert row["signature_tags_carried"] == "SWEATERS"


def test_to_columns_takes_price_median_from_the_middle_of_the_band():
    row = assess.to_columns({"price_p25_p50_p75": [40, 90, 160]})
    assert row["price_median"] == 90


def test_to_columns_stamps_assessed_at():
    assert assess.to_columns({}).get("assessed_at") is not None


def test_to_columns_never_writes_the_columns_the_sweep_owns():
    """store_name and address belong to the sweep. Two writers on one column
    fight every time the filters are retuned."""
    row = assess.to_columns({"name": "Somewhere Else", "formatted_address": "1 Elsewhere"})
    assert "store_name" not in row
    assert "address" not in row


def test_every_column_to_columns_writes_exists_on_the_model():
    """The whole point of the copy is that these two agree."""
    from app.db.models import Prospect
    columns = set(Prospect.__table__.columns.keys())
    written = set(assess.to_columns({"price_p25_p50_p75": [1, 2, 3]}))
    assert written <= columns, written - columns
