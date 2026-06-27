import itertools
import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15.7; rv:150.0) Gecko/20100101 Firefox/150.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_7_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    # Firefox on Linux
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:150.0) Gecko/20100101 Firefox/150.0",
]

_ua_cycle = itertools.cycle(_USER_AGENTS)


def fetch_page(url: str) -> Optional[str]:
    try:
        response = requests.get(
            url, headers={"User-Agent": next(_ua_cycle)}, timeout=30
        )
        response.raise_for_status()
        logger.debug("Fetched URL: %s", response.url)
        return response.text
    except requests.RequestException as e:
        logger.error("Error fetching %s: %s", url, e)
        return None


def parse_release_date(date_str: str, series_url: str = "") -> str:
    if not date_str:
        return ""

    # German format: DD.MM.YYYY
    match = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", date_str)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"

    # English/numeric format: MM-DD-YY or DD-MM-YY
    match = re.match(r"(\d{2})-(\d{2})-(\d{2})", date_str)
    if match:
        if "audible.com" in series_url:
            month, day, year = match.groups()
        else:
            day, month, year = match.groups()
        current_year = datetime.now().year % 100
        year = f"19{year}" if int(year) > current_year else f"20{year}"
        return f"{year}-{month}-{day}"

    return date_str


def extract_series_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1", class_="bc-text-bold")
    if h1:
        return h1.get_text(strip=True)
    return "Unknown Series"


def extract_book_info(product_item, base_url: str) -> dict:
    # Title
    title_elem = product_item.find("ul", class_="bc-list-nostyle")
    if title_elem:
        title_elem = title_elem.find("h2", class_="bc-text-bold")
    else:
        title_elem = product_item.find("h2", class_="bc-text-bold")
    title = title_elem.get_text(strip=True) if title_elem else ""

    # Subtitle
    subtitle = ""
    subtitle_elem = product_item.find("li", class_="subtitle")
    if subtitle_elem:
        span = subtitle_elem.find("span", class_="bc-text")
        subtitle = span.get_text(strip=True) if span else ""

    # Author
    author = ""
    author_elem = product_item.find("li", class_="authorLabel")
    if author_elem:
        link = author_elem.find("a", class_="bc-link")
        author = link.get_text(strip=True) if link else ""

    # Narrator
    narrator = ""
    narrator_elem = product_item.find("li", class_="narratorLabel")
    if narrator_elem:
        link = narrator_elem.find("a", class_="bc-link")
        narrator = link.get_text(strip=True) if link else ""

    # Duration
    duration = ""
    runtime_elem = product_item.find("li", class_="runtimeLabel")
    if runtime_elem:
        duration = runtime_elem.get_text(strip=True).split(":", 1)[-1].strip()

    # Release date
    release_date_raw = ""
    release_elem = product_item.find("li", class_="releaseDateLabel")
    if release_elem:
        release_date_raw = release_elem.get_text(strip=True).split(":", 1)[-1].strip()
    release_date = parse_release_date(release_date_raw, series_url=base_url)

    # Language
    language = ""
    language_elem = product_item.find("li", class_="languageLabel")
    if language_elem:
        span = language_elem.find("span", class_="bc-text")
        if span:
            language = span.get_text(strip=True)
            language = language.split(":", 1)[-1].strip() if ":" in language else language

    # ASIN
    asin_div = product_item.find("div", class_="adbl-asin-impression")
    asin = asin_div.get("data-asin", "") if asin_div else ""

    # Book URL
    book_url = ""
    book_link = product_item.find("a", href=True)
    if book_link:
        href = book_link.get("href", "")
        if href.startswith("/pd/"):
            parsed = urlparse(urljoin(base_url, href))
            book_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    # Cover image
    img = product_item.find("img")
    cover_image_url = img.get("src") if img else None

    return {
        "title": title,
        "subtitle": subtitle,
        "author": author,
        "narrator": narrator,
        "duration": duration,
        "release_date": release_date,
        "language": language,
        "asin": asin,
        "book_url": book_url,
        "cover_image_url": cover_image_url,
    }


def extract_books(soup: BeautifulSoup, base_url: str) -> list[dict]:
    items = soup.find_all("li", class_="productListItem")
    return [extract_book_info(item, base_url) for item in items]


def scrape_series(url: str) -> Optional[dict]:
    html = fetch_page(url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    return {
        "series_title": extract_series_title(soup),
        "books": extract_books(soup, url),
    }
