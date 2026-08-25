# Prospect scoring — status, 2026-08-25

Where the scoring pipeline stands after three full passes over the dev database.
Supersedes the 2026-08-22 note, which described a 92-row first run and was two
runs stale.

## The run

1,437 prospect rows; **1,381 have a website and have been judged**, 56 have none
and can never be assessed by this path. Re-judged from the page cache — the
cache holds raw HTTP bodies and extraction runs fresh on every pass, so a
re-judge costs ~1.5 s/row against ~20 s/row for a fresh scrape. 0 exceptions,
0 territories failed.

| verdict | count | flagged `problems` |
|---|---|---|
| insufficient_data | 1,027 | 14 |
| weak | 228 | 2 |
| strong | 65 | 4 |
| possible | 61 | 2 |

**465 rows carry a sentence written for a rep.** The rest are gated or
unreadable.

## The headline is still reach, not judgement

**1,027 of 1,381 rows say `insufficient_data`.** That is not the model being
cautious — it is us being unable to see the shop:

| why | count |
|---|---|
| no vendor field on any product | 736 |
| shelf readable | 645 |

More than half of all shops never record who made what they sell. Every rule in
`prompt.md` reads the shelf, so for those shops there is nothing to read. **The
largest available win is scrape reach, not rule tuning.**

## Fixed in this pass — the concentration gate

`products_per_brand` is a MEAN, and a mean is diluted by exactly the thing that
disguises a house brand.

**Phoebe Jon** carried 114 of its own 124 products, plus nine "brands" holding
one glove, one belt and one scarf apiece. 92% of the shelf under one name — at
a mean of 12.4, an ordinary boutique's number. It scored **`strong` at high
confidence** and topped a rep's call list. Its own $148–$228 sweaters read as a
perfect price match *precisely because they compete with ours*: the better the
price fit, the worse the prospect.

The domain-echo test was right and never ran — `unreadable_reason` returned at
`ppb <= floor` before reaching it.

`top_brand_share` now gates alongside the mean. Both shapes still require
`brands_echo_domain`, and both still answer `insufficient_data`, never `weak`:
a catalogue cannot tell a label from a site that never fills its vendor field,
so neither will we.

**23 rows caught**, mean products-per-brand 10.8 to 38.5 — every one of them
below the 40.6 floor, so the mean gate caught **none**:

| | |
|---|---|
| off the call list | Phoebe Jon (92%), Rebelie Wear (91%), Sara Campbell ×3 (80%), Kulua Studio Shop (79%) |
| already `weak`, now honest | 17 rows — Uncle Kyle's Sweater Emporium (95%), Kealopiko, Minnow, Frankie Shop, Robindira Unsworth, … |

Those 17 matter as much as the 6. `weak` was a claim about their shelf we had no
right to make.

**Cost to real accounts: zero.** Measured across all 242 accounts with a
readable vendor field, the gate catches exactly the 13 the mean gate already
caught. The catalogue floor of 75 is what buys that: seven of our own accounts
hold 1–34 products under a single name, and 100% of twenty products is a failed
scrape, not a label.

## Reading the diff honestly

68 verdicts moved out of 1,381.

| cause | count |
|---|---|
| the new gate | 23 |
| no pre-existing measurement moved | 45 |

All 23 gated rows moved, and nothing else moved into `insufficient_data`. The
gate is fully attributable.

**The other 45 are not simply noise, and should not be reported as such.** Their
direction is asymmetric — 34 up, 11 down — which a coin flip does not produce.
Every row also gained a measurement it did not have before: `top_brand_share` is
now in the payload for every shop, and rule 1 tells the model to read it. For a
shop with LOW concentration that is a new *positive* signal.

Tested rather than assumed: among shops that were `weak`, the ones that moved up
average **0.146** concentration against **0.324** for the ones that stayed, at
practically the same brand count (82.4 vs 80.6). That supports the mechanism but
does not prove it row by row — 28 rows against 225.

So: the gate did what it was measured to do, and the same run drifted 23 shops
upward for a reason that is plausible and unproven.

## Open

1. **Scrape reach.** 736 of 1,381 shops record no vendor at all. This is the
   ceiling on everything else.
2. **`strong` has never been validated against known customers.** `prompt.md`
   prescribes the test — score accounts that already buy from us; a good judge
   calls most of them `strong` or `possible`, a flattering one calls everybody
   `strong`. It has not been run. ~$0.05 and five minutes.
3. **Verdicts near a boundary are unstable run to run**, and nothing records how
   stable one is: a shop scoring 5/5 `weak` and one scoring 3/5 `weak` are
   written identically. Fixing it costs N model calls per shop.
4. **53 duplicate store-name groups** (Reformation ×5, Alo ×4). Not a bug —
   different OSM elements sharing one website — but we pay the model once per
   element for the same catalogue.
5. **`scrapping-bot`'s own test suite is red**: 20 failures, none touching the
   concentration gate. 14 come from the `KNIT_TERMS` edits, 4 from the rule-3
   change, 2 are environmental. It is the source of truth for everything
   vendored here, and its tests currently guard nothing.
6. **The VM is behind** — it still holds the older 225-row CA/HI restore.
