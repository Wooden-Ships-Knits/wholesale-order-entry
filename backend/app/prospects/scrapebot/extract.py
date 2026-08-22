"""Pure extraction functions. No network, no file I/O, no global state."""
import html
import json
import re
import statistics
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .models import Page, Product

# The vocabulary of a knit sweater, and nothing else. Four terms were measured
# against 227k products and cut, because each qualified far more non-knitwear
# than knitwear: "sweatshirt" is fleece and French terry, "crewneck" is a
# neckline that tags tees, "poncho" is mostly rain capes, and "jumper" means a
# pinafore dress in a US catalogue. "shawl" named a collar, not a garment.
KNIT_TERMS = (
    "knit", "knitwear", "sweater", "cardigan", "pullover", "turtleneck",
    "cashmere", "merino", "lambswool", "wool",
)
# "knitted" makes the same claim as "knit", and a bare `s?` matched neither it
# nor "lambswool", so hand-knitted goods were missed by the list that exists to
# find them. "knitting" is deliberately absent: it names the craft rather than
# the garment, and reached only scissors, straw bags and towels.
KNIT_RE = re.compile(r"\b(" + "|".join(KNIT_TERMS) + r")(?:s|ted)?\b", re.I)

# Fibres rather than garments: they say what a thing is made of, not what it
# is, so they qualify a product only when the title has not already named
# something else. Cashmere sells blazers and neckerchiefs, merino sells base
# layers and socks, wool sells coats.
WEAK_KNIT_TERMS = frozenset({"wool", "lambswool", "cashmere", "merino"})

# Not "woven" — a robe and a scarf can both be knit. These are the words a
# title uses when the product is not a sweater, whatever it is made of.
# Singular only: the suffix group below reaches the plurals, which is what a
# store's own tag is usually written in ("Wool Coats", "Jackets"). "scarves"
# is listed because no suffix reaches it from "scarf".
NON_SWEATER_TERMS = (
    "coat", "jacket", "blazer", "trouser", "pant",
    "bag", "blanket", "rug", "skirt", "short", "jean",
    "denim", "vest", "robe", "gown", "cape", "neckerchief", "wrap", "scarf",
    "scarves",
)
NON_SWEATER_RE = re.compile(r"\b(" + "|".join(NON_SWEATER_TERMS) + r")(?:s|es)?\b", re.I)

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _clean_html(text: str) -> str:
    """Plain text from raw HTML: drop script/style blocks (incl. contents), strip
    remaining tags, unescape entities, collapse whitespace."""
    text = _SCRIPT_STYLE_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def knit_terms_in(text: str | None) -> list[str]:
    """Distinct knit terms present in text, lowercased, in first-seen order."""
    if not text:
        return []
    seen: list[str] = []
    for m in KNIT_RE.finditer(text):
        term = m.group(1).lower()
        if term not in seen:
            seen.append(term)
    return seen


def product_blob(p: Product) -> str:
    """Searchable text for one product. Tolerates null fields from Shopify feeds.

    `description` is raw body_html straight from the Shopify feed, so it is
    cleaned to plain text (tags stripped, entities unescaped, whitespace
    collapsed) BEFORE truncation — otherwise markup can consume the whole
    400-char budget and hide the fabric line that follows it. `Product.description`
    itself is left untouched; only this searchable copy is cleaned.
    """
    tags = p.tags or []
    parts = [
        p.title or "",
        p.product_type or "",
        " ".join(tags) if isinstance(tags, list) else str(tags),
        _clean_html(p.description or "")[:400],
    ]
    return " ".join(part for part in parts if part).strip()


def names_knitwear(text: str | None, name: str | None = None) -> bool:
    """Whether this text names knitwear, fibre-only mentions suppressed.

    The rule `knit_products` applies, lifted out so a shorter piece of text can
    ask the same question. A store's own tag is exactly that: "Sweaters" and
    "Wool Coats" are the same decision as a product title, and a second copy of
    the rule beside this one would drift from it silently.

    `name` is the text checked for a garment that is not a sweater; it defaults
    to `text`. A product searches its whole blob but is judged on its title, so
    a fabric line in the description cannot turn a coat into a sweater. A tag
    names itself, so the default is what a tag wants.
    """
    terms = knit_terms_in(text)
    if not terms:
        return False
    subject = text if name is None else name
    return not (all(t in WEAK_KNIT_TERMS for t in terms)
                and NON_SWEATER_RE.search(subject or ""))


def knit_products(products: list[Product]) -> list[Product]:
    """The subset of products whose searchable text mentions a knit term.

    A product is suppressed when every matched term is "weak" (wool, cashmere,
    merino — fibres, which describe what a thing is made of rather than what it
    is) AND the title names something that is not a sweater (coat, scarf, robe,
    ...). Any strong term present is enough to keep the product regardless of
    title: a cashmere scarf is not knitwear here, but a cashmere knit scarf is.
    """
    return [p for p in products if names_knitwear(product_blob(p), p.title or "")]


PRICE_RE = re.compile(r"(\d[\d,]*(?:\.\d{1,2})?)")


def parse_price(raw) -> float | None:
    """First positive number in the input, or None. Handles '$1,395.00' and ranges."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) or None
    m = PRICE_RE.search(str(raw))
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return value if value > 0 else None


def price_stats(products: list[Product]) -> tuple[float | None, float | None, float | None]:
    """(min, max, median) over products that have a price. All None if none do."""
    prices = [p.price for p in products if p.price]
    if not prices:
        return (None, None, None)
    return (min(prices), max(prices), statistics.median(prices))


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
MAILTO_RE = re.compile(r'mailto:([^"\'?>\s]+)', re.I)
TEL_RE = re.compile(r'tel:([+\d][\d\-().\s]{6,})', re.I)
PHONE_TEXT_RE = re.compile(r"\(?\b\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}\b")
ASSET_SUFFIX_RE = re.compile(r"\.(png|jpe?g|gif|svg|webp|css|js)$", re.I)

_IG_RE = re.compile(r'https?://(?:www\.)?instagram\.com/[^"\'\s>]+', re.I)
_FB_RE = re.compile(r'https?://(?:www\.)?facebook\.com/[^"\'\s>]+', re.I)
_SOCIAL_JUNK = ("sharer", "/share", "intent", "plugins/", "/tr?", "dialog/")


def _dedupe(items: list[str]) -> list[str]:
    seen: list[str] = []
    for i in items:
        if i and i not in seen:
            seen.append(i)
    return seen


def extract_emails(html: str) -> list[str]:
    """Emails from mailto: links first, then from page text. Deduplicated, order preserved."""
    found = [m.split("?")[0].strip() for m in MAILTO_RE.findall(html or "")]
    found += EMAIL_RE.findall(html or "")
    return _dedupe([e for e in found if not ASSET_SUFFIX_RE.search(e)])


def extract_phones(html: str) -> list[str]:
    """Phone numbers from tel: links and page text."""
    found = [m.strip() for m in TEL_RE.findall(html or "")]
    found += [m.strip() for m in PHONE_TEXT_RE.findall(html or "")]
    return _dedupe(found)


def extract_socials(html: str) -> dict:
    """First real Instagram and Facebook profile URL. Share/tracking links ignored."""
    out = {"instagram": "", "facebook": ""}
    for key, rx in (("instagram", _IG_RE), ("facebook", _FB_RE)):
        for url in rx.findall(html or ""):
            if any(j in url.lower() for j in _SOCIAL_JUNK):
                continue
            out[key] = url
            break
    return out


# Ordered: the first match wins, so specific e-commerce platforms beat generic CMS markers.
PLATFORM_MARKERS = (
    ("shopify", ("cdn.shopify.com", "shopify.theme", "myshopify.com")),
    ("squarespace", ("squarespace.com", "static1.squarespace", "data-squarespace")),
    ("wix", ("wixstatic.com", "wix.com", "_wixcssimportrule")),
    ("bigcommerce", ("bigcommerce.com", "bcdata", "var bcdata")),
    ("woocommerce", ("woocommerce", "wp-content/plugins/woocommerce")),
    ("other-ecom", ("ecwid", "lightspeed", "shoplightspeed")),
    ("wordpress", ("wp-content", "wp-includes")),
)

KNOWN_CHAINS = (
    "h m", "macys", "charlotte russe", "windsor", "bealls",
    "brandy melville", "four seasons", "nordstrom", "dillards",
    "talbots", "chicos", "anthropologie", "j crew",
)
_STORE_LOCATOR_RE = re.compile(r"find a store|store locator|all locations|our stores", re.I)


def detect_platform(html: str) -> str:
    """Best-guess e-commerce platform from HTML markers."""
    h = (html or "").lower()
    for name, markers in PLATFORM_MARKERS:
        if any(m in h for m in markers):
            return name
    return "custom/unknown"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def is_chain(store_name: str, html: str) -> bool:
    """True for national chains, which are not wholesale prospects.

    Two signals: a known-chain name list, and a store-locator page listing many
    locations. Deliberately simple - it will miss chains not on the list.

    Names are compared with punctuation and spaces removed, so "Macy's", "MACYS"
    and "macy s" all collapse to "macys". Prefix matching is only allowed for
    chain names of 6+ characters, so short names like "h m" (H&M) cannot swallow
    unrelated boutiques.
    """
    slug = _slug(store_name)
    compact = slug.replace(" ", "")
    for chain in KNOWN_CHAINS:
        chain_compact = chain.replace(" ", "")
        if compact == chain_compact:
            return True
        if len(chain_compact) >= 6 and compact.startswith(chain_compact):
            return True
    if _STORE_LOCATOR_RE.search(html or "") and (html or "").lower().count("<li") > 30:
        return True
    return False


def products_from_shopify_feed(data: dict) -> list[Product]:
    """Parse a Shopify /products.json payload. Tolerates null fields throughout."""
    out = []
    for raw in (data or {}).get("products") or []:
        variant_prices = [
            parse_price(v.get("price")) for v in (raw.get("variants") or [])
        ]
        prices = [p for p in variant_prices if p]
        tags = raw.get("tags")
        out.append(Product(
            title=raw.get("title") or "",
            price=min(prices) if prices else None,
            vendor=raw.get("vendor") or "",
            product_type=raw.get("product_type") or "",
            tags=tags if isinstance(tags, list) else [],
            description=raw.get("body_html") or "",
        ))
    return out


def _brand_name(brand) -> str:
    """schema.org states a brand as a bare string or as an object with a name."""
    if isinstance(brand, str):
        return brand.strip()
    if isinstance(brand, dict):
        return (brand.get("name") or "").strip()
    if isinstance(brand, list) and brand:
        return _brand_name(brand[0])
    return ""


def _jsonld_blocks(html: str) -> list:
    """Every parseable JSON-LD block in the page, flattened out of @graph wrappers."""
    blocks = []
    for raw in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html or "", re.S | re.I,
    ):
        try:
            parsed = json.loads(raw.strip())
        except (ValueError, TypeError):
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if isinstance(item, dict):
                blocks.extend(item.get("@graph", [item]))
    return [b for b in blocks if isinstance(b, dict)]


def products_from_jsonld(html: str) -> list[Product]:
    """Products declared via schema.org JSON-LD."""
    out = []
    for block in _jsonld_blocks(html):
        types = block.get("@type", "")
        types = types if isinstance(types, list) else [types]
        if "Product" not in types:
            continue
        offers = block.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        out.append(Product(
            title=block.get("name") or "",
            price=parse_price(offers.get("price") if isinstance(offers, dict) else None),
            vendor=_brand_name(block.get("brand")),
            description=block.get("description") or "",
        ))
    return out


WHOLESALE_RE = re.compile(r"wholesale|stockist|trade[\-_ ]?account|retailer|become[\-_ ]a", re.I)
ABOUT_RE = re.compile(r"/about|/our-story|/pages/about", re.I)
META_DESC_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', re.I
)


# Furniture repeated on every page of a store: the nav tree, the currency
# selector, the footer. None of it is anything the store said about itself.
BOILERPLATE_TAGS = [
    "script", "style", "noscript", "nav", "header", "footer",
    "form", "select", "option", "button", "svg", "iframe", "aside",
]

# Below this, a <main> is an empty theme shell rather than the real content.
MIN_MAIN_TEXT = 200


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def html_to_text(html: str) -> str:
    """Visible text with scripts, styles and whitespace runs removed."""
    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return _collapse(soup.get_text(" "))


def main_text(html: str) -> str:
    """Visible text of the page's own content, with the furniture removed.

    A Shopify About page carries its whole nav tree, a list of every country's
    currency, and a footer in the same document. Taking all the visible text
    buries the store's few sentences about itself — or pushes them past any
    length limit before they are ever reached.

    Prefers <main>, then a role="main" container, then the body. A <main> too
    small to hold real copy is treated as an empty shell and skipped.
    """
    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup(BOILERPLATE_TAGS):
        tag.decompose()

    for container in (soup.find("main"), soup.find(attrs={"role": "main"})):
        if container is not None:
            text = _collapse(container.get_text(" "))
            if len(text) >= MIN_MAIN_TEXT:
                return text

    return _collapse((soup.body or soup).get_text(" "))


ABOUT_TEXT_LIMIT = 4000


def about_text(pages: list[Page], limit: int = ABOUT_TEXT_LIMIT) -> str:
    """Text from an About page, else the meta description.

    The meta-description fallback is marketing copy rather than a company
    description, so a caller comparing stores should expect it to be thin.
    """
    for page in pages:
        if ABOUT_RE.search(page.url) and page.text:
            return page.text[:limit].strip()
    for page in pages:
        m = META_DESC_RE.search(page.html or "")
        if m and m.group(1).strip():
            return m.group(1).strip()[:limit]
    return ""


def about_snippet(pages: list[Page], limit: int = 300) -> str:
    """The opening of the About text, short enough to scan in a spreadsheet."""
    return about_text(pages, limit=limit)


def find_wholesale_page(pages: list[Page]) -> str:
    """URL of a wholesale/stockist/trade page, if one was visited."""
    for page in pages:
        if WHOLESALE_RE.search(page.url):
            return page.url
    return ""


def internal_links(html: str, base_url: str, domain: str) -> list[str]:
    """Absolute, deduplicated, same-domain http(s) links from a page."""
    soup = BeautifulSoup(html or "", "lxml")
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base_url, href).split("#")[0].rstrip("/")
        host = urlparse(url).netloc.lower()
        host = host[4:] if host.startswith("www.") else host
        if host != domain or not url.startswith("http"):
            continue
        if url not in out:
            out.append(url)
    return out
