# Prospect scoring — status, 2026-08-25 (second pass)

Where the pipeline stands after restoring the knit vocabulary, testing the
rubric against known customers for the first time, and adding a third gate.

## The run

1,437 prospect rows; **1,381 have a website and have been judged**, 56 have none
and can never be assessed by this path. Re-judged from the page cache. 0
exceptions, 0 territories failed.

| verdict | before | now |
|---|---|---|
| insufficient_data | 1,027 | 1,034 |
| weak | 228 | 268 |
| strong | 65 | 53 |
| possible | 61 | 26 |

**Worth a call: 126 → 79.** The list shrank by 37%, and the reason is the
vocabulary, not the new gate.

**Flagged `problems`: 22 → 7.** Fewer answers the judge disagrees with.

## Why the call list shrank

`turtleneck` and the four fibres had been removed from `KNIT_TERMS`.
`WEAK_KNIT_TERMS` still listed those four and `names_knitwear` suppresses a
product only when EVERY matched term is weak — but `knit_terms_in` reads
`KNIT_RE`, built from `KNIT_TERMS`, so those terms could never come back. The
suppression branch and `NON_SWEATER_RE` were unreachable. "Cashmere Crewneck"
and "Turtleneck" stopped counting as knitwear; "Wool Coat", the case the
suppression exists for, was never being suppressed because it was never
matching.

Three independent confirmations that this was a regression:

- 14 assertions in `test_extract_knit.py` go green on restoring it — the
  `scrapping-bot` suite drops from **20 failures to 2** (both missing local data)
- the comment above `WEAK_KNIT_TERMS` only parses if the fibres are in `KNIT_TERMS`
- the rebuilt band returns to **p10 2.3% / median 11% / p90 22.4%** — the
  figures `docs/prospect-rule-changes.md` §2b already quotes as ours

Our accounts are knitwear retailers, so restoring the vocabulary raised their
measured knit share more than it raised a general boutique's. Prospects are now
compared against a correctly-measured band and compare worse. **That is more
honest, not more pessimistic.**

Of 71 verdict changes: **48 carried a moved knit measurement**, 7 were the new
gate, and 16 moved with no measurement behind them.

## The rubric was tested against real customers — the first time

`prompt.md` prescribes this and it had never been run.

| group | result |
|---|---|
| 25 real accounts | 13 `strong`, 7 `possible`, 4 `weak`, 1 `insufficient_data` → **80% recognised** |
| 10 planted known-bad shops | **0** `strong`, **0** `possible` |

The failure `prompt.md` warns about — "if everything comes back `strong`, the
model is agreeing with you rather than judging" — does not occur. It called 4
real customers `weak` and 3 luxury shops `weak`.

**Three limits, stated because the result is otherwise easy to over-read:**

1. **7 of the 10 planted controls never reached the model** — they were gated
   first. Only 3 actually tested the rubric.
2. **The accounts are not held out.** `data/raw` covers only the l5y set, so the
   17 accounts genuinely outside the pattern have no catalogue. The pattern is
   aggregate statistics rather than per-shop data, so the leakage is weak — but
   it is there.
3. **4 real customers were called `weak`** — 16% of paying customers a rep
   would never be told to call.

## The three gates

All answer `insufficient_data`, never `weak`: a catalogue cannot tell a label
from a shop that never fills its vendor field, so neither do we.

| gate | catches | reads |
|---|---|---|
| mean | 183 | `products_per_brand` above the account band |
| concentration | 23 | one brand holding most of the shelf |
| **whose name is on the clothes** | **7** | own name across the catalogue AND across the knitwear |

The third exists because the first two ran out of room. Artemesia is a label at
**64%** own-name across its catalogue — it buys candles, soap and greetings
cards from thirteen brands and its clothes from nobody. `tinademel.com` is a
customer stocking **23 Wooden Ships products**, at **62.3%**. Two points apart,
and no threshold on that axis separates them.

Their knit shelves are nothing alike, and that is the whole design: **one signal
being wrong is not enough to hide a customer.** Measured across all 242
accounts, the gate costs **zero** additional accounts at every threshold from
60% to 70%.

Caught: East Magnolia (70/80), Alicia Peru (69/85), Meg (69/100), Sage Boutique
(68/58), American Drifter (68/100), Harvest Moon Home (67/83), Artemesia
(66/55). Sandy's Boutique, Society Beach and À-Tout-Àge carry none of their own
name on any knitwear and stay ungated.

## The headline is still reach

**1,034 of 1,381 rows are `insufficient_data`**, and 736 shops record no vendor
on any product. Every rule reads the shelf; for those shops there is nothing to
read. **The largest available win is scrape reach, not rule tuning** — this is
the fourth patch to rule 1, and each has moved single figures.

## Open

1. **Scrape reach.** 736 of 1,381 shops name no brand at all. The ceiling on
   everything else.
2. **Hosiery still counts as knitwear.** Merino tights and wool socks inflate a
   short knit shelf — five of Artemesia's eleven knit products are one hosiery
   brand's. Suppressing them costs 61 of 27,076 account knit products (0.23%),
   but it fails `test_knit_products_keeps_wool_socks`, and commit `f6781b1`
   ("stop guard deleting knit accessories") shows that outcome was deliberate.
   Needs its own decision, not a side effect.
3. **6 of 664 price medians are absurd** (thereformation.com reads $7,282,000).
   A price-parsing bug, and rule 3 reads that field.
4. **Verdicts near a boundary are unstable run to run**, and nothing records how
   stable one is.
5. **53 duplicate store-name groups** — different OSM elements sharing one
   website. Not a bug, but the model is paid once per element.
6. **The VM is behind** — still the older 225-row CA/HI restore.
