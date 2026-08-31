"""Turn raw CSV rows into a deduplicated list of scrape targets."""
import csv
import re
from collections import Counter
from urllib.parse import urlparse

from .models import Target

SOCIAL_HOSTS = ("instagram.com", "facebook.com", "twitter.com", "x.com", "tiktok.com")

# Two kinds of address that are not the store's own site. Business directories
# hold no catalogue and no words the store wrote. Marketplace storefronts do,
# but many accounts share one host, and every acquisition strategy here works at
# the domain level — it cannot tell one boutique's stock from its neighbour's.
# Either way, scraping the URL would attribute someone else's page to the store.
DIRECTORY_HOSTS = (
    "yelp.com", "mapquest.com", "manta.com", "yellowpages.com", "tripadvisor.com",
    "foursquare.com", "bizapedia.com", "chamberofcommerce.com", "google.com",
    "shoptiques.com", "squareup.com",
)

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def normalize_url(raw: str) -> str:
    """Add a scheme if missing, strip whitespace and any trailing slash.

    An existing scheme is detected case-insensitively and left alone (so
    "HTTP://..." and "ftp://..." are not mistaken for scheme-less input).
    A protocol-relative value ("//host/path") gets an "https:" prefix rather
    than a full "https://" prepended in front of its own leading slashes.
    """
    u = (raw or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        u = "https:" + u
    elif not _SCHEME_RE.match(u):
        u = "https://" + u
    return u.rstrip("/")


def _host(raw: str) -> str:
    """Lowercase host with userinfo, port, and any leading 'www.' removed.

    Returns "" when the value has no parseable host (e.g. a bare path).
    """
    normalized = normalize_url(raw)
    if not normalized:
        return ""
    host = (urlparse(normalized).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def canonical_domain(raw: str) -> str:
    """Lowercase host with any leading 'www.' removed."""
    return _host(raw)


def website_of(row: dict) -> str:
    """The row's website value, whatever case the header used.

    Google Places exports write 'website'; Salesforce writes 'Website'. Matching
    only one of them silently classifies every row of the other as no_website.
    """
    for key, value in (row or {}).items():
        if isinstance(key, str) and key.strip().lower() == "website":
            return (value or "").strip()
    return ""


# The heading that names the store, in the spellings the usual sources emit.
# Matched on a normalized form, so "store_name", "Store Name" and "STORE NAME"
# all land here.
NAME_HEADINGS = (
    "account name", "store name", "company name", "business name",
    "name", "company", "account", "store",
)


def _normalize_heading(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def name_column(columns: list[str]) -> str:
    """The header that names the store, for records that carry no other label.

    A Salesforce export leads with Id and a Places export with store_name, so
    the position of the name is not fixed; the known spellings are tried in
    order of how specific they are. An unrecognised header falls back to the
    first column, which still tells one record from another.
    """
    if not columns:
        return ""
    normalized = {_normalize_heading(c): c for c in reversed(columns)}
    for heading in NAME_HEADINGS:
        if heading in normalized:
            return normalized[heading]
    return columns[0]


def dedupe_header(header: list[str]) -> list[str]:
    """Make a repeated column name unique: a second 'L12M' becomes 'L12M_2'.

    A spreadsheet often repeats a heading across two blocks of figures — a
    per-period run and its running total. csv.DictReader keeps only the last of
    each name, so the earlier block vanishes without any error.
    """
    seen: Counter = Counter()
    out = []
    for name in header:
        seen[name] += 1
        out.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    return out


def input_columns(csv_path: str) -> list[str]:
    """The input header, in order and made unique, so every column survives."""
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        return dedupe_header(next(csv.reader(fh), []))


def read_rows(csv_path: str) -> list[dict]:
    """Every data row, keyed by the disambiguated header.

    Used in place of csv.DictReader so that repeated headings keep their own
    columns. Short rows are padded and blank lines skipped.
    """
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        header = dedupe_header(next(reader, []))
        rows = []
        for raw in reader:
            if not any(field.strip() for field in raw):
                continue
            padded = list(raw[:len(header)]) + [""] * max(0, len(header) - len(raw))
            rows.append(dict(zip(header, padded)))
        return rows


def _host_matches(host: str, hosts: tuple[str, ...]) -> bool:
    return host in hosts or any(host.endswith("." + h) for h in hosts)


def classify_row(row: dict) -> str:
    """Return 'no_website', 'social_only', 'directory_only', or 'ok'."""
    website = website_of(row)
    if not website:
        return "no_website"
    host = _host(website)
    if not host:
        return "no_website"
    if _host_matches(host, SOCIAL_HOSTS):
        return "social_only"
    if _host_matches(host, DIRECTORY_HOSTS):
        return "directory_only"
    return "ok"


def load_targets(csv_path: str) -> tuple[list[Target], list[tuple[dict, str]]]:
    """Read the input CSV.

    Returns (targets, skipped) where skipped is a list of (row, reason) for
    rows that need no fetching. Every input row appears in exactly one of the two.
    """
    targets: dict[str, Target] = {}
    skipped: list[tuple[dict, str]] = []

    for row in read_rows(csv_path):
        reason = classify_row(row)
        if reason != "ok":
            skipped.append((row, reason))
            continue
        website = website_of(row)
        domain = canonical_domain(website)
        if domain in targets:
            targets[domain].rows.append(row)
        else:
            targets[domain] = Target(
                domain=domain,
                url=normalize_url(website),
                rows=[row],
            )
    return list(targets.values()), skipped
