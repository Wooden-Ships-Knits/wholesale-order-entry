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


# --- scoping a run to one territory ----------------------------------------
#
# A whole-book sweep is 1,289 shops and ~6 hours. Run in store_name order that
# leaves every rep's book half-done for the whole run; run per territory and
# each one finishes complete and usable.

def _where_of(**kwargs):
    """The WHERE clause pending() built, as text.

    Deliberately not str(query): that renders the whole SELECT, whose column
    list contains "prospects.territory" whether or not it was filtered on — an
    assertion against it passes for the wrong reason.
    """
    seen = {}
    class _DB:
        def execute(self, q):
            seen["q"] = q
            class _R:
                def scalars(_s):
                    class _S:
                        def all(__s): return []
                    return _S()
            return _R()
    assess.pending(_DB(), **kwargs)
    return str(seen["q"].whereclause)


def test_pending_can_be_scoped_to_one_territory():
    assert "prospects.territory =" in _where_of(territory="CA/HI - Rande Cohen")


def test_pending_without_a_territory_still_covers_everything():
    assert "prospects.territory" not in _where_of()


def test_assess_pending_passes_the_territory_through(monkeypatch):
    """The filter is useless if the batch runner drops it."""
    got = {}
    def _fake_pending(db, limit=None, territory=None):
        got["territory"] = territory
        return []
    monkeypatch.setattr(assess, "pending", _fake_pending)
    # `complete` supplied, so the OpenAI-configured check is never reached.
    assess.assess_pending(object(), territory="Midwest - Aviva Landin",
                          complete=lambda s, u: "{}")
    assert got["territory"] == "Midwest - Aviva Landin"


# --- the unreadable-shelf gate (rule 1) ------------------------------------
#
# A shop whose products all carry its OWN name as the vendor tells us nothing
# about what it buys. Two very different shops look identical from here: a DTC
# label, and a boutique whose site simply does not fill the vendor field.
#
# We cannot tell them apart from a catalogue, so the honest answer is
# `insufficient_data` -- NEVER `weak`. This is not a nicety: nine of our own
# 242 paying accounts classify as house_brand today, burlapranch.com lists all
# 2,000 of its products under "BURLAP RANCH MERCANTILE", and prompt.md rule 1
# already records that four accounts read exactly this way. A gate that
# answered `weak` here would be calling our own customers bad prospects.

def _own_label_shop(name="HILL HOUSE HOME", domain="hillhousehome.com", n=400):
    """Deep catalogue, every product under the shop's own name."""
    return _store([_product(f"Nap Dress {i}", vendor=name) for i in range(n)],
                  domain=domain)


# La Tre carries 45 brands at 44 products each and is a real `strong`. Nine
# brands here, not three: at three the store is house_brand by the existing
# MAX_HOUSE_BRANDS rule and would be weak for a different and correct reason,
# which would leave this test passing without testing the gate at all.
def _deep_multibrand_shop(domain="latreclothingca.com", n=450):
    brands = ["RAILS", "VELVET", "XIRENA", "FRAME", "NILI LOTAN",
              "ULLA JOHNSON", "VINCE", "AGOLDE", "MOTHER"]
    return _store([_product(f"Sweater {i}", vendor=brands[i % len(brands)])
                   for i in range(n)], domain=domain)


def test_a_shop_that_only_names_itself_is_insufficient_data_not_weak():
    complete, calls = _answers(GOOD)
    out = assess.assess_website("https://hillhousehome.com", PATTERN, complete,
                                scrape=lambda url: _own_label_shop(), system="sys")
    assert out["verdict"] == "insufficient_data", "weak would libel our own accounts"
    assert calls == [], "the gate must fire before the model is paid for"


def test_the_gate_says_which_shelf_it_could_not_see():
    """`reasons` is the only place a rep is ever told why."""
    complete, _ = _answers(GOOD)
    out = assess.assess_website("https://hillhousehome.com", PATTERN, complete,
                                scrape=lambda url: _own_label_shop(), system="sys")
    assert "brand" in out["reasons"][0].lower()


def test_a_deep_catalogue_of_other_peoples_brands_still_reaches_the_model():
    """La Tre carries RAILS at 44 products per brand and is a real `strong`.
    Depth alone must never gate — only depth plus a shelf we cannot read."""
    complete, calls = _answers(GOOD)
    out = assess.assess_website("https://latreclothingca.com", PATTERN, complete,
                                scrape=lambda url: _deep_multibrand_shop(), system="sys")
    assert out["verdict"] == "strong"
    assert len(calls) == 1


def test_the_gate_needs_depth_as_well_as_a_self_named_shelf():
    """The name alone must not gate. A shop with 12 products under its own name
    is a thin scrape; only depth turns that into "we cannot see the shelf"."""
    from app.prospects.analysis.llm_payload import unreadable_reason
    shallow = {"domain": "tiny.com", "products_per_brand": 12.0,
               "catalogue_size": 60, "top_brands": ["TINY"]}
    assert unreadable_reason(shallow, min_products_per_brand=40.6) is None
    assert unreadable_reason({**shallow, "products_per_brand": 138.0},
                             min_products_per_brand=40.6) is not None


# --- rule 3 asks whether the shop stocks knitwear in OUR band ---------------
#
# `knitwear_price_median` is a MEDIAN. Sandy's Boutique sits at $218 -- $18
# over -- yet 33% of its knitwear is inside $100-$200 and its p25 is $125. It
# was rejected anyway. Ypsilon Dresses sits at $250 with 0% in band and should
# be rejected. One number cannot tell those two apart; a share can.

def _priced_knit_shop(prices, domain="boutique.com"):
    return _store([_product(f"Sweater {i}", price=p, vendor=f"BRAND{i % 9}")
                   for i, p in enumerate(prices)], domain=domain)


def test_knit_in_band_share_counts_knitwear_inside_our_retail_band():
    from app.prospects.analysis.llm_payload import store_payload
    # 4 of 8 inside $100-200.
    shop = _priced_knit_shop([40, 60, 120, 150, 180, 195, 300, 400] * 8)
    pay = store_payload("boutique.com", shop, shop["about_text"],
                        assess.tag_signature(PATTERN))
    assert pay["knit_in_band_share"] == pytest.approx(0.5, abs=0.01)


def test_a_shop_priced_entirely_above_us_has_no_share_in_band():
    from app.prospects.analysis.llm_payload import store_payload
    shop = _priced_knit_shop([225, 250, 300, 450] * 16)
    pay = store_payload("ypsilon.com", shop, shop["about_text"],
                        assess.tag_signature(PATTERN))
    assert pay["knit_in_band_share"] == 0.0


def test_the_payload_carries_knit_price_percentiles_not_just_a_median():
    """A median hides the spread that decides whether we fit on the shelf."""
    from app.prospects.analysis.llm_payload import store_payload
    shop = _priced_knit_shop([100, 125, 150, 218, 400] * 13)
    pay = store_payload("boutique.com", shop, shop["about_text"],
                        assess.tag_signature(PATTERN))
    lo, mid, hi = pay["knit_price_p25_p50_p75"]
    assert lo < mid < hi
    assert lo <= 150


# --- the shelf, persisted -------------------------------------------------

def test_the_brands_are_written_to_the_row_deepest_first():
    """`top_brands` decided the gate and was thrown away, so the one column the
    rule turns on could not be checked from the table. Order is the payload's --
    deepest-stocked first -- because the FIRST entry is what the domain-echo
    test reads."""
    from app.prospects.analysis.llm_payload import store_payload
    shop = _store([_product(f"S{i}", vendor=v) for i, v in enumerate(
        ["RAILS"] * 9 + ["VELVET"] * 5 + ["FRAME"] * 2)])
    pay = store_payload("boutique.com", shop, "", assess.tag_signature(PATTERN))
    row = assess.to_columns(pay)
    assert row["top_brands"] == "RAILS; VELVET; FRAME"


def test_a_shelf_with_no_vendor_field_writes_null_not_an_empty_string():
    from app.prospects.analysis.llm_payload import store_payload
    shop = _store([_product(f"S{i}", vendor="") for i in range(60)])
    pay = store_payload("boutique.com", shop, "", assess.tag_signature(PATTERN))
    assert assess.to_columns(pay)["top_brands"] is None


# --- a mean cannot see a label hiding behind accessories --------------------
#
# Phoebe Jon carries 114 of its own 124 products, plus nine "brands" holding one
# glove, one belt and one scarf apiece. 92% of the shelf under one name -- at a
# mean of 12.4, which is an ordinary boutique's number. It scored `strong` at
# HIGH confidence and topped a rep's call list, its own $148-$228 sweaters
# reading as a perfect price match precisely because they compete with ours.
#
# Same error already fixed once on price: there a median hid the distribution,
# here a mean hides the concentration.

FILLERS = ["PORTOLANO", "LINEN WAY", "ELMNTL", "MACHETE", "FURBISH STUDIO",
           "B-LOW THE BELT", "SOMERVILLE SCARVES", "HAKNE", "J SOCIETY"]


def _accessory_screened_label(own=114, domain="thephoebejon.com"):
    products = [_product(f"Cardigan {i}", vendor="PHOEBE JON") for i in range(own)]
    products += [_product(f"Glove {i}", vendor=b) for i, b in enumerate(FILLERS)]
    return _store(products, domain=domain)


def test_top_brand_share_is_not_diluted_by_one_product_labels():
    from app.prospects.analysis.signature import top_brand_share
    store = _accessory_screened_label()
    assert round(top_brand_share(store), 2) == 0.93
    # ...while the mean the gate used to trust reads like any boutique.
    assert round(len(store["products"]) / 10, 1) == 12.3


def test_top_brand_share_is_none_when_nothing_names_a_brand():
    """None is not zero. A shelf with no vendor field at all is a different
    fact from one brand holding everything, and 0 would say the opposite."""
    from app.prospects.analysis.signature import top_brand_share
    assert top_brand_share(_store([_product("X", vendor="")])) is None


def test_a_label_hiding_behind_accessory_brands_never_reaches_the_model():
    complete, calls = _answers(GOOD)
    out = assess.assess_website("https://thephoebejon.com", PATTERN, complete,
                                scrape=lambda url: _accessory_screened_label(),
                                system="sys")
    assert out["verdict"] == "insufficient_data", "strong put a rival top of the list"
    assert calls == [], "the gate must fire before the model is paid for"


def test_the_gate_names_the_share_when_the_mean_looks_ordinary():
    """A reader checking this row finds nothing in products_per_brand that
    explains it, so the reason has to carry the number that did."""
    from app.prospects.analysis.llm_payload import unreadable_reason
    reason = unreadable_reason(
        {"domain": "thephoebejon.com", "catalogue_size": 124,
         "products_per_brand": 12.4, "top_brand_share": 0.919,
         "top_brands": ["PHOEBE JON"]}, min_products_per_brand=40.6)
    assert "92%" in reason


def test_a_thin_self_named_catalogue_is_a_failed_scrape_not_a_label():
    """THE REGRESSION THAT PROTECTS PAYING CUSTOMERS. Seven of our own accounts
    hold 1-34 products under a single name. 100% of 22 products is our failure
    to read the site; gating it would have hidden a real customer from a rep."""
    from app.prospects.analysis.llm_payload import unreadable_reason
    thin = {"domain": "hulamoonboutique.com", "catalogue_size": 22,
            "products_per_brand": 22.0, "top_brand_share": 1.0,
            "top_brands": ["HULA MOON BOUTIQUE"]}
    assert unreadable_reason(thin, min_products_per_brand=40.6) is None


def test_backing_one_outside_brand_heavily_is_a_buying_decision_not_a_gate():
    """Society Beach carries 76% under one label that is NOT its own. That is a
    shelf we can read perfectly well -- it just has a favourite."""
    from app.prospects.analysis.llm_payload import unreadable_reason
    p = {"domain": "societybeach.com", "catalogue_size": 200,
         "products_per_brand": 15.0, "top_brand_share": 0.76,
         "top_brands": ["VELVET", "RAILS"]}
    assert unreadable_reason(p, min_products_per_brand=40.6) is None


def test_the_payload_carries_the_concentration_the_gate_reads():
    from app.prospects.analysis.llm_payload import store_payload
    payload = store_payload("thephoebejon.com", _accessory_screened_label(),
                            "a boutique", set())
    assert round(payload["top_brand_share"], 2) == 0.93


# --- whose name is on the CLOTHES ------------------------------------------
#
# Artemesia's apparel is 100% its own label at $325-$465, while it buys candles,
# soap and greetings cards from thirteen brands. Those thirteen pad the
# catalogue count, so concentration reads 66% -- under the bar -- and the mean
# reads 5.8. Both gates above wave it through.
#
# The near miss that shapes the rule: tinademel.com sits at 62.3% own-name,
# two points away, and stocks 23 Wooden Ships products. No threshold on that
# axis separates them. Its KNIT shelf does: 48 third-party sweaters.

def _own_label_apparel(domain="artemesiamade.com"):
    """Clothes all its own; the outside brands are homeware and hosiery."""
    ps = [_product(f"Cardigan {i}", vendor="ARTEMESIAMADE") for i in range(56)]
    ps += [_product("Coat", vendor="ARTEMESIA", ptype="Coat", tags=("COATS",))]
    ps += [_product(f"Candle {i}", vendor=b, ptype="Candle", tags=("HOME",))
           for i, b in enumerate(["BROOKLYN CANDLE", "TATINE", "HIMALAYAN"] * 10)]
    return _store(ps, domain=domain)


def _house_line_retailer(domain="tinademel.com"):
    """A retailer with its own line that still BUYS its knitwear."""
    ps = [_product(f"House Tee {i}", vendor="TINA DEMEL", ptype="Tops",
                   tags=("TOPS",)) for i in range(60)]
    ps += [_product(f"Sweater {i}", vendor=b)
           for i, b in enumerate(["LAUREN MOSHI", "MICHAEL LAUREN", "IN BLOOM",
                                  "WOODEN SHIPS", "JOCELYN"] * 8)]
    return _store(ps, domain=domain)


def test_own_name_share_counts_every_spelling_of_the_shop():
    """56 under ARTEMESIAMADE and one under ARTEMESIA is one shop, not two --
    counting only the deepest entry dilutes a shop by its own second spelling."""
    from app.prospects.analysis.signature import own_name_share, top_brand_share
    store = _own_label_apparel()
    assert own_name_share("artemesiamade.com", store) > top_brand_share(store)


def test_the_knit_shelf_is_measured_apart_from_the_candles():
    from app.prospects.analysis.signature import knit_own_name_share
    assert knit_own_name_share("artemesiamade.com", _own_label_apparel()) == 1.0


def test_a_short_knit_shelf_reports_none_rather_than_all_its_own():
    """None is not 1.0. Two knit products under the shop's own name is not
    evidence that it makes its own knitwear -- it is no evidence at all."""
    from app.prospects.analysis.signature import knit_own_name_share
    store = _store([_product("Sweater", vendor="TINY"),
                    _product("Cardigan", vendor="TINY")], domain="tiny.com")
    assert knit_own_name_share("tiny.com", store) is None


def test_a_shop_whose_clothes_are_its_own_never_reaches_the_model():
    complete, calls = _answers(GOOD)
    out = assess.assess_website("https://artemesiamade.com", PATTERN, complete,
                                scrape=lambda url: _own_label_apparel(), system="sys")
    assert out["verdict"] == "insufficient_data"
    assert calls == [], "the gate must fire before the model is paid for"


def test_a_retailer_with_a_house_line_still_reaches_the_model():
    """THE REGRESSION THAT PROTECTS A PAYING CUSTOMER. tinademel.com is two
    points from Artemesia on catalogue own-name share and stocks 23 of our own
    products. Only the knit shelf tells them apart."""
    complete, calls = _answers(GOOD)
    out = assess.assess_website("https://tinademel.com", PATTERN, complete,
                                scrape=lambda url: _house_line_retailer(), system="sys")
    assert out["verdict"] == "strong"
    assert len(calls) == 1


def test_the_gate_names_the_knit_shelf_not_the_catalogue():
    """The catalogue figure is the unremarkable one; a reader checking the row
    needs the number that actually decided it."""
    from app.prospects.analysis.llm_payload import unreadable_reason
    reason = unreadable_reason(
        {"domain": "artemesiamade.com", "catalogue_size": 87,
         "products_per_brand": 5.8, "top_brand_share": 0.64,
         "own_name_share": 0.66, "knit_own_name_share": 0.55,
         "top_brands": ["ARTEMESIAMADE"]}, min_products_per_brand=40.6)
    assert reason is not None and "knitwear" in reason
