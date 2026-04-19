#!/usr/bin/env python3
"""
audiobook_extractor.py

Extracts audiobook series information from Audible series pages.
"""

import json
import re
import requests
import sys
from datetime import datetime

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Optional


# The URL of the Audible series page to scrape
SERIES_URL = "https://www.audible.de/series/Ultimate-Level-1-Hoerbuecher/B0D33QYZV2"
SERIES_URL = "https://www.audible.de/series/Wizarding-World-Hoerbuecher/B07CMBKWY8"


def fetch_page(url: str) -> Optional[str]:
    """Fetch the HTML content from the given URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        print(response.url)
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching URL: {e}", file=sys.stderr)
        return None


def parse_release_date(date_str: str) -> str:
    """Parse and unify release date to ISO format (YYYY-MM-DD)."""
    if not date_str:
        return ""

    # Try German format: DD.MM.YYYY
    match = re.match(r'(\d{2})\.(\d{2})\.(\d{4})', date_str)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"

    # Try English format: MM-DD-YY
    match = re.match(r'(\d{2})-(\d{2})-(\d{2})', date_str)
    if match:
        if 'audible.com' in SERIES_URL:
            month, day, year = match.groups()
        else:
            day, month, year = match.groups()
        # Convert 2-digit year to 4-digit
        # If year is greater than current year, assume 19xx, otherwise 20xx
        current_year = datetime.now().year % 100
        year = f"19{year}" if int(year) > current_year else f"20{year}"
        return f"{year}-{month}-{day}"

    # Return original if no match
    return date_str


def extract_series_title(soup: BeautifulSoup) -> str:
    """Extract the series title from the h1 tag."""
    h1 = soup.find('h1', class_='bc-text-bold')
    if h1:
        return h1.get_text(strip=True)
    return "Unknown Series"


def extract_book_info(product_item) -> Dict[str, str]:
    """Extract information from a single product list item."""
    # Title from h2 - look for h2 inside the nested ul.bc-list structure
    # The title is inside: productListItem > div > div > span > ul > li > h2
    title_elem = product_item.find('ul', class_='bc-list-nostyle')
    if title_elem:
        title_elem = title_elem.find('h2', class_='bc-text-bold')
    else:
        # Fallback to finding any h2 with bc-text-bold
        title_elem = product_item.find('h2', class_='bc-text-bold')
    title = title_elem.get_text(strip=True) if title_elem else "Unknown Title"

    # Subtitle
    subtitle_elem = product_item.find('li', class_='subtitle')
    if subtitle_elem:
        span = subtitle_elem.find('span', class_='bc-text')
        subtitle = span.get_text(strip=True) if span else ""
    else:
        subtitle = ""

    # Author
    author_elem = product_item.find('li', class_='authorLabel')
    if author_elem:
        author_link = author_elem.find('a', class_='bc-link')
        author = author_link.get_text(strip=True) if author_link else ""
    else:
        author = ""

    # Narrator
    narrator_elem = product_item.find('li', class_='narratorLabel')
    if narrator_elem:
        narrator_link = narrator_elem.find('a', class_='bc-link')
        narrator = narrator_link.get_text(strip=True) if narrator_link else ""
    else:
        narrator = ""

    # Duration/Runtime
    duration = ""
    runtime_elem = product_item.find('li', class_='runtimeLabel')
    if runtime_elem:
        duration = runtime_elem.get_text(strip=True).split(':', 1)[-1].strip()

    # Release Date
    release_date_raw = ""
    release_elem = product_item.find('li', class_='releaseDateLabel')
    if release_elem:
        release_date_raw = release_elem.get_text(strip=True).split(':', 1)[-1].strip()
    release_date = parse_release_date(release_date_raw)

    # Language
    language_elem = product_item.find('li', class_='languageLabel')
    if language_elem:
        span = language_elem.find('span', class_='bc-text')
        if span:
            language = span.get_text(strip=True)
            # Remove label prefix (e.g., "Sprache:" or "Language:")
            language = language.split(':', 1)[-1].strip() if ':' in language else language
        else:
            language = ""
    else:
        language = ""

    # ASIN from data-asin attribute
    asin_div = product_item.find('div', class_='adbl-asin-impression')
    asin = asin_div.get('data-asin', '') if asin_div else ""

    # Book URL from the product link
    book_link = product_item.find('a', href=True)
    book_url = ""
    if book_link:
        href = book_link.get('href', '')
        if href.startswith('/pd/'):
            url = urlparse(urljoin(SERIES_URL, href))
            book_url = f'{url.scheme}://{url.netloc}{url.path}'

    return {
        'title': title,
        'subtitle': subtitle,
        'author': author,
        'narrator': narrator,
        'duration': duration,
        'release_date': release_date,
        'language': language,
        'asin': asin,
        'book_url': book_url
    }


def extract_books(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """Extract all books from the series page."""
    books = []
    product_items = soup.find_all('li', class_='productListItem')

    for item in product_items:
        book_info = extract_book_info(item)
        books.append(book_info)

    return books


def main():
    # Fetch the page (try local file first, then URL)
    html_content = fetch_page(SERIES_URL)

    if not html_content:
        sys.exit(1)

    # Parse HTML
    soup = BeautifulSoup(html_content, 'html.parser')

    # Extract data
    series_title = extract_series_title(soup)
    books = extract_books(soup)

    result = {
        'series_title': series_title,
        'books': books
    }

    # Output as JSON
    output_data = json.dumps(result, indent=2, ensure_ascii=False)
    print(output_data)


if __name__ == '__main__':
    main()
