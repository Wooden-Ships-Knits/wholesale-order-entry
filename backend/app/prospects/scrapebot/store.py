"""One store, scraped and shaped. Returns the record instead of writing it,
so an API worker can call this as well as the CLI.

`cli.py` writes these records to data/raw/<domain>.json; the scoring service
holds the same record in memory. (The fetch cache underneath is still on disk.)
"""
import re
from dataclasses import asdict
from pathlib import Path

from . import extract
from .fetch import Fetcher
from .models import Acquired, Target
from .resolve import canonical_domain, normalize_url
from .sources import acquire

PAGE_TEXT_CHARS = 5000     # what a raw record keeps of each page

DEFAULT_CACHE_DIR = Path("data/.cache")

_WHITESPACE_RE = re.compile(r"\s")


def raw_record(target: Target, acquired: Acquired) -> dict:
    """One store's findings, in the shape `data/raw/<domain>.json` holds.

    `about_text` is derived here, from the Page objects, rather than downstream
    from the serialised copy: pages are truncated to PAGE_TEXT_CHARS on the way
    out and an About page can run past that.
    """
    return {
        "domain": target.domain,
        "url": target.url,
        "status": acquired.status,
        "source_used": acquired.source_used,
        "catalogue_truncated": acquired.catalogue_truncated,
        "products": [asdict(p) for p in acquired.products],
        "pages": [{"url": p.url, "text": p.text[:PAGE_TEXT_CHARS]} for p in acquired.pages],
        "source_rows": target.rows,
        "about_text": extract.about_text(acquired.pages),
    }


def scrape_one(url: str, fetcher=None, cache_dir=DEFAULT_CACHE_DIR) -> dict:
    """Scrape a single store by URL.

    The domain is canonicalised the same way the CSV path canonicalises it, so
    the same shop keys identically whether the caller said www. or not.
    """
    domain = canonical_domain(url)
    # Once normalize_url has prefixed a scheme, urlparse reads a bare phrase as
    # a netloc verbatim: canonical_domain("not a url") is "not a url", not "",
    # so an emptiness check alone never fires and the fetcher is handed
    # "https://not a url". No hostname contains whitespace, so that is the one
    # check `_host` doesn't make. Nothing further is asserted: "localhost",
    # "[::1]" and an IDN host are all real, and a name that simply doesn't
    # resolve is the fetcher's business, ending as status "error" like any
    # other unreachable store.
    if not domain or _WHITESPACE_RE.search(domain):
        raise ValueError(f"not a hostname: {url!r}")
    target = Target(domain=domain, url=normalize_url(url), rows=[])
    fetcher = fetcher or Fetcher(cache_dir=cache_dir)
    return raw_record(target, acquire(target, fetcher))
