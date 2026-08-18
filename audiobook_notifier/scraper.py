import logging
import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import requests

from audiobook_notifier import config

logger = logging.getLogger(__name__)

# Audible's own catalog API, the same one their web frontend talks to. It needs
# no authentication for catalog reads, and unlike the HTML it hands out release
# dates as plain ISO strings — which is the whole reason we moved off scraping.
_API_VERSION = "1.0"

# Everything we need for a book row. product_extended_attrs carries the runtime,
# media the cover, sku the placeholder marker (see _is_placeholder).
_PRODUCT_RESPONSE_GROUPS = ",".join(
    (
        "product_desc",
        "product_attrs",
        "product_extended_attrs",
        "contributors",
        "media",
        "series",
        "sku",
    )
)

# The API happily returned 28 ASINs in one call, but the parameter is a URL
# query string and nobody documents a limit. Chunk well below anything that
# could turn into a truncated response we would read as "books disappeared".
_ASIN_BATCH_SIZE = 50

_HOST_RE = re.compile(r"^(?:www\.)?(audible\.[a-z][a-z.]*[a-z])$")
_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")

_USER_AGENT = "audiobook-notifier (+https://github.com/lkiesow/audiobook-notifier)"


def is_iso_date(value: Optional[str]) -> bool:
    """True if value is a real calendar date in YYYY-MM-DD form."""
    if not value:
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _api_base(series_url: str) -> Optional[str]:
    """The catalog API host for the marketplace this series URL belongs to.

    Series and product ASINs are marketplace-specific — the same series is
    B0937FGLYC on audible.de and B0937JMKYV on audible.com — so the host has to
    follow the URL rather than being pinned to one marketplace.
    """
    match = _HOST_RE.match(urlparse(series_url).netloc.lower())
    if not match:
        return None
    return f"https://api.{match.group(1)}/{_API_VERSION}"


def _web_base(series_url: str) -> str:
    """The storefront origin, for building book links back to the same site."""
    parsed = urlparse(series_url)
    netloc = parsed.netloc.lower()
    if not netloc.startswith("www."):
        netloc = f"www.{netloc}"
    return f"https://{netloc}"


def _series_asin(series_url: str) -> Optional[str]:
    """The series ASIN, which is the last path segment of a series URL."""
    segments = [s for s in urlparse(series_url).path.split("/") if s]
    if not segments or not _ASIN_RE.match(segments[-1]):
        return None
    return segments[-1]


def _get_json(url: str) -> Optional[dict]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            timeout=config.SCRAPE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error("Error fetching %s: %s", url, e)
        return None
    except ValueError as e:
        logger.error("Malformed JSON from %s: %s", url, e)
        return None


def _child_asins(api_base: str, series_asin: str) -> Optional[tuple[str, list[str]]]:
    """The series title and the ASINs of its volumes, or None on failure.

    Asking the wrong marketplace for an ASIN does not fail: it answers 200 with
    a stub carrying nothing but the ASIN back. Treating an absent or empty
    relationships list as a failure keeps that from reading as "series with no
    books" and wiping the stored volumes.
    """
    data = _get_json(
        f"{api_base}/catalog/products/{series_asin}"
        "?response_groups=relationships,product_desc"
    )
    if not data:
        return None
    product = data.get("product") or {}
    asins = [
        rel["asin"]
        for rel in product.get("relationships") or []
        if rel.get("relationship_to_product") == "child"
        and rel.get("relationship_type") == "series"
        and rel.get("asin")
    ]
    if not asins:
        logger.warning(
            "No series children for %s at %s (wrong marketplace?)",
            series_asin,
            api_base,
        )
        return None
    return product.get("title") or "Unknown Series", asins


def _is_placeholder(product: dict) -> bool:
    """True for Audible's stand-in rows for volumes they have not dated yet.

    They carry a 2200-01-01 release date, no cover and no runtime, and would
    otherwise park themselves permanently at the top of the upcoming list. The
    SKU prefix is the reliable marker; the date is not filtered on, so a real
    product that ever landed on that date would still come through.
    """
    sku = product.get("sku") or product.get("sku_lite") or ""
    return sku.startswith("PL_HLDR_")


def _fetch_products(api_base: str, asins: list[str]) -> Optional[list[dict]]:
    """Full metadata for the given ASINs, or None if any batch failed.

    All-or-nothing on purpose: a half-fetched series looks exactly like a series
    that lost books, and the caller would write that over good data.
    """
    products = []
    for start in range(0, len(asins), _ASIN_BATCH_SIZE):
        batch = asins[start:start + _ASIN_BATCH_SIZE]
        data = _get_json(
            f"{api_base}/catalog/products"
            f"?asins={','.join(batch)}"
            f"&response_groups={_PRODUCT_RESPONSE_GROUPS}"
        )
        if not data or not data.get("products"):
            return None
        products.extend(data["products"])
    return products


def _format_duration(minutes: Optional[int]) -> str:
    """Render a runtime the way the HTML pages did, so stored rows don't churn."""
    if not minutes:
        return ""
    hours, remainder = divmod(int(minutes), 60)
    if not hours:
        return f"{remainder} Min."
    if not remainder:
        return f"{hours} Std."
    return f"{hours} Std. und {remainder} Min."


def _first_name(people: Optional[list[dict]]) -> str:
    for person in people or []:
        if person.get("name"):
            return person["name"]
    return ""


def _to_book(product: dict, web_base: str) -> dict:
    release_date = product.get("release_date") or ""
    if not is_iso_date(release_date):
        logger.warning(
            "Unusable release date %r for %s", release_date, product.get("asin")
        )
        release_date = ""

    images = product.get("product_images") or {}
    return {
        "title": product.get("title") or "",
        "subtitle": product.get("subtitle") or "",
        "author": _first_name(product.get("authors")),
        "narrator": _first_name(product.get("narrators")),
        "duration": _format_duration(product.get("runtime_length_min")),
        "release_date": release_date,
        "language": product.get("language") or "",
        "asin": product.get("asin") or "",
        "book_url": f"{web_base}/pd/{product['asin']}" if product.get("asin") else "",
        "cover_image_url": images.get("500"),
    }


def _scrape_once(url: str) -> Optional[dict]:
    api_base = _api_base(url)
    if not api_base:
        logger.error("Not an Audible URL: %s", url)
        return None
    series_asin = _series_asin(url)
    if not series_asin:
        logger.error("No series ASIN in URL: %s", url)
        return None

    children = _child_asins(api_base, series_asin)
    if not children:
        return None
    series_title, asins = children

    products = _fetch_products(api_base, asins)
    if not products:
        return None

    placeholders = [p for p in products if _is_placeholder(p)]
    if placeholders:
        logger.debug(
            "Skipping %d placeholder product(s) in %s", len(placeholders), series_title
        )

    web_base = _web_base(url)
    books = [_to_book(p, web_base) for p in products if not _is_placeholder(p)]
    if not books:
        logger.warning("No usable books for %s", url)
        return None
    return {"series_title": series_title, "books": books}


def scrape_series(url: str) -> Optional[dict]:
    """Fetch a series and its books from the Audible catalog API.

    Retried as a whole because the failures worth retrying are transient ones —
    a timeout, a 5xx, a truncated body. A malformed URL fails the same way every
    time and just burns the attempts, which is cheap enough not to special-case.
    """
    attempts = max(1, config.SCRAPE_RETRY_ATTEMPTS)
    for attempt in range(1, attempts + 1):
        result = _scrape_once(url)
        if result:
            if attempt > 1:
                logger.info("Scraped %s on attempt %d/%d", url, attempt, attempts)
            return result
        if attempt < attempts:
            delay = min(
                config.SCRAPE_RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1),
                config.SCRAPE_RETRY_MAX_BACKOFF_SECONDS,
            )
            logger.info(
                "Retrying %s in %.0fs (attempt %d/%d failed)",
                url, delay, attempt, attempts,
            )
            time.sleep(delay)
    logger.error("Giving up on %s after %d attempts", url, attempts)
    return None
