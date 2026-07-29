"""Fuzzy store-name search over the cached account index.

Exists because SOQL can't do this. `Name = '...'` is exact, and `LIKE '%x%'`
has no notion of case folding, punctuation, possessives or word order — so a
rep typing "Scout & Molly" finds none of the nine "SCOUT & MOLLY'S (CITY)"
franchise locations, and typing "HOOKERSAAS" doesn't surface "HOOKERS".

The account list is small (~4.5k) and changes rarely, so the caller fetches it
once per cache window and matching happens here in Python, where normalising
and scoring is straightforward.

Matching is token-based:
  "SCOUT & MOLLY'S (NASHVILLE)" -> {scout, molly, nashville}
  "Scout & Molly"              -> {scout, molly}          -> matches
  "AI's Store LLC"             -> {ai, store, llc}        -> matches "AI'S STORE"
  "HOOKERSAAS"                 -> {hookersaas}            -> matches "HOOKERS"
"""
import re
from typing import Any, Callable

# "molly's" / "molly’s" -> "molly". Done before punctuation stripping so the
# trailing s goes with the apostrophe instead of becoming its own token.
_POSSESSIVE = re.compile(r"['’]s(?=\b|$)", re.IGNORECASE)
_APOSTROPHE = re.compile(r"['’]")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Below this length a token must match exactly — a 1-2 character prefix would
# otherwise pull in half the catalogue ("a" matching every account with an A).
_MIN_PREFIX_LEN = 3
# Fraction of the typed words that must match before a candidate is offered.
_MIN_COVERAGE = 0.5


def tokens(name: str | None) -> list[str]:
    """Normalise a store name to comparable words."""
    text = (name or "").lower()
    text = _POSSESSIVE.sub("", text)  # molly's -> molly
    text = _APOSTROPHE.sub("", text)  # o'brien -> obrien (not a possessive)
    return [t for t in _NON_ALNUM.sub(" ", text).split() if t]


def _tokens_match(query: str, candidate: str) -> bool:
    """Either token being a prefix of the other counts — that catches both
    abbreviations ("Scout" for "Scout & Molly") and over-typing ("HOOKERSAAS"
    for "HOOKERS"), which are the two ways reps get names wrong."""
    if query == candidate:
        return True
    if len(query) < _MIN_PREFIX_LEN or len(candidate) < _MIN_PREFIX_LEN:
        return False
    return query.startswith(candidate) or candidate.startswith(query)


def score(query_tokens: list[str], candidate_tokens: list[str]) -> float:
    """0 = no match. Higher is better.

    coverage  — how much of what they typed was found. The primary signal.
    tightness — how much of the candidate was used, so "Scout & Molly" ranks
                an exact "SCOUT & MOLLY" above "SCOUT & MOLLY'S (NASHVILLE)"
                without hiding the latter.
    """
    if not query_tokens or not candidate_tokens:
        return 0.0
    matched = sum(1 for q in query_tokens if any(_tokens_match(q, c) for c in candidate_tokens))
    coverage = matched / len(query_tokens)
    if coverage < _MIN_COVERAGE:
        return 0.0
    tightness = matched / len(candidate_tokens)
    return coverage + 0.25 * tightness


def search(
    accounts: list[dict[str, Any]],
    query: str,
    limit: int = 10,
    name_of: Callable[[dict], str | None] = lambda r: r.get("Name"),
) -> list[dict[str, Any]]:
    """Best `limit` accounts for `query`, most relevant first.

    Ties break on name so the order is stable between calls — a list that
    reshuffles under the cursor is worse than one that is slightly wrong.
    """
    q = tokens(query)
    if not q:
        return []
    scored = []
    for rec in accounts:
        s = score(q, tokens(name_of(rec)))
        if s > 0:
            scored.append((s, (name_of(rec) or "").lower(), rec))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [rec for _s, _n, rec in scored[:limit]]
