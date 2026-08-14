import pytest
from bs4 import BeautifulSoup

from audiobook_notifier import config, scraper

LEGACY = """
<html><body>
  <h1 class="bc-text-bold">A Series</h1>
  <li class="productListItem">
    <ul class="bc-list-nostyle"><h2 class="bc-text-bold">Book One</h2></ul>
    <li class="releaseDateLabel">Erscheinungsdatum: 12.08.2026</li>
    <div class="adbl-asin-impression" data-asin="B0TEST0001"></div>
  </li>
</body></html>
"""

# Audible's web-component layout: same titles, no productListItem, no dates.
NEW_LAYOUT = """
<html><body>
  <h1 class="bc-text-bold">A Series</h1>
  <adbl-product-row variant="catalog">
    <h3 slot="title"><a href="/pd/x/B0TEST0001">Book One</a></h3>
  </adbl-product-row>
</body></html>
"""


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(scraper.time, "sleep", lambda s: None)
    monkeypatch.setattr(config, "SCRAPE_RETRY_ATTEMPTS", 4)


def pages(monkeypatch, sequence):
    """Serve a scripted sequence of pages; the last one repeats."""
    fetched = []

    def fetch(url):
        fetched.append(url)
        return sequence[min(len(fetched) - 1, len(sequence) - 1)]

    monkeypatch.setattr(scraper, "fetch_page", fetch)
    return fetched


def test_detects_the_unsupported_layout():
    assert scraper.uses_unsupported_layout(BeautifulSoup(NEW_LAYOUT, "html.parser"))
    assert not scraper.uses_unsupported_layout(BeautifulSoup(LEGACY, "html.parser"))


def test_first_attempt_succeeds_without_retrying(monkeypatch):
    fetched = pages(monkeypatch, [LEGACY])
    result = scraper.scrape_series("https://audible.de/series/x/B0")

    assert len(fetched) == 1
    assert [b["title"] for b in result["books"]] == ["Book One"]
    assert result["books"][0]["release_date"] == "2026-08-12"


def test_retries_past_the_unsupported_layout(monkeypatch):
    """The layout varies per request, so asking again is the whole fix."""
    fetched = pages(monkeypatch, [NEW_LAYOUT, NEW_LAYOUT, LEGACY])
    result = scraper.scrape_series("https://audible.de/series/x/B0")

    assert len(fetched) == 3
    assert [b["title"] for b in result["books"]] == ["Book One"]


def test_retries_a_failed_fetch(monkeypatch):
    fetched = pages(monkeypatch, [None, LEGACY])
    assert scraper.scrape_series("https://audible.de/series/x/B0") is not None
    assert len(fetched) == 2


def test_gives_up_after_the_configured_attempts(monkeypatch):
    fetched = pages(monkeypatch, [NEW_LAYOUT])
    assert scraper.scrape_series("https://audible.de/series/x/B0") is None
    assert len(fetched) == 4


def test_attempts_are_configurable(monkeypatch):
    monkeypatch.setattr(config, "SCRAPE_RETRY_ATTEMPTS", 1)
    fetched = pages(monkeypatch, [NEW_LAYOUT])
    assert scraper.scrape_series("https://audible.de/series/x/B0") is None
    assert len(fetched) == 1


def test_backoff_grows_between_attempts_and_is_capped(monkeypatch):
    delays = []
    monkeypatch.setattr(scraper.time, "sleep", lambda s: delays.append(s))
    monkeypatch.setattr(config, "SCRAPE_RETRY_ATTEMPTS", 5)
    monkeypatch.setattr(config, "SCRAPE_RETRY_BACKOFF_SECONDS", 5)
    monkeypatch.setattr(config, "SCRAPE_RETRY_MAX_BACKOFF_SECONDS", 30)
    pages(monkeypatch, [NEW_LAYOUT])

    scraper.scrape_series("https://audible.de/series/x/B0")
    assert delays == [5, 10, 20, 30]
