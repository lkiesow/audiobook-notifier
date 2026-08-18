import pytest

from audiobook_notifier import config, scraper

DE = "https://www.audible.de/series/Dungeon-Crawler-Carl-Hoerbuecher/B0937FGLYC"
COM = "https://www.audible.com/series/Dungeon-Crawler-Carl-Audiobooks/B0937JMKYV"

# What the wrong marketplace answers with: HTTP 200, no title, no children.
WRONG_MARKETPLACE = {"product": {"asin": "B0937FGLYC", "asset_details": []}}


def series_response(*asins, title="Dungeon Crawler Carl"):
    return {
        "product": {
            "asin": "B0937FGLYC",
            "title": title,
            "relationships": [
                {
                    "asin": asin,
                    "relationship_to_product": "child",
                    "relationship_type": "series",
                    "sequence": str(i + 1),
                }
                for i, asin in enumerate(asins)
            ],
        }
    }


def products_response(*asins):
    return {
        "products": [
            {
                "asin": asin,
                "title": f"Book {i + 1}",
                "release_date": "2026-08-12",
                "sku": f"BK_ACX0_{i:06d}DE",
                "runtime_length_min": 600,
            }
            for i, asin in enumerate(asins)
        ]
    }


OK_SERIES = series_response("B08V893CH7")
OK_PRODUCTS = products_response("B08V893CH7")


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(scraper.time, "sleep", lambda s: None)
    monkeypatch.setattr(config, "SCRAPE_RETRY_ATTEMPTS", 4)


def responses(monkeypatch, sequence):
    """Serve a scripted sequence of JSON responses; the last one repeats.

    Each element is one _get_json call, so a successful scrape consumes two:
    the series relationships, then the batched products.
    """
    requested = []

    def get_json(url):
        requested.append(url)
        return sequence[min(len(requested) - 1, len(sequence) - 1)]

    monkeypatch.setattr(scraper, "_get_json", get_json)
    return requested


def test_first_attempt_succeeds_without_retrying(monkeypatch):
    requested = responses(monkeypatch, [OK_SERIES, OK_PRODUCTS])
    result = scraper.scrape_series(DE)

    assert len(requested) == 2
    assert result["series_title"] == "Dungeon Crawler Carl"
    assert [b["title"] for b in result["books"]] == ["Book 1"]
    assert result["books"][0]["release_date"] == "2026-08-12"


def test_calls_the_matching_marketplace_api(monkeypatch):
    requested = responses(monkeypatch, [OK_SERIES, OK_PRODUCTS])
    scraper.scrape_series(COM)

    assert requested[0].startswith("https://api.audible.com/1.0/catalog/products/B0937JMKYV")
    assert requested[1].startswith("https://api.audible.com/1.0/catalog/products?asins=")


def test_wrong_marketplace_fails_rather_than_returning_no_books(monkeypatch):
    """A stub response must not read as "this series lost all its books"."""
    requested = responses(monkeypatch, [WRONG_MARKETPLACE])
    assert scraper.scrape_series(DE) is None
    assert len(requested) == 4


def test_retries_a_failed_fetch(monkeypatch):
    requested = responses(monkeypatch, [None, OK_SERIES, OK_PRODUCTS])
    assert scraper.scrape_series(DE) is not None
    assert len(requested) == 3


def test_retries_when_only_the_product_call_fails(monkeypatch):
    requested = responses(monkeypatch, [OK_SERIES, None, OK_SERIES, OK_PRODUCTS])
    assert scraper.scrape_series(DE) is not None
    assert len(requested) == 4


def test_gives_up_after_the_configured_attempts(monkeypatch):
    requested = responses(monkeypatch, [None])
    assert scraper.scrape_series(DE) is None
    assert len(requested) == 4


def test_attempts_are_configurable(monkeypatch):
    monkeypatch.setattr(config, "SCRAPE_RETRY_ATTEMPTS", 1)
    requested = responses(monkeypatch, [None])
    assert scraper.scrape_series(DE) is None
    assert len(requested) == 1


def test_backoff_grows_between_attempts_and_is_capped(monkeypatch):
    delays = []
    monkeypatch.setattr(scraper.time, "sleep", lambda s: delays.append(s))
    monkeypatch.setattr(config, "SCRAPE_RETRY_ATTEMPTS", 5)
    monkeypatch.setattr(config, "SCRAPE_RETRY_BACKOFF_SECONDS", 5)
    monkeypatch.setattr(config, "SCRAPE_RETRY_MAX_BACKOFF_SECONDS", 30)
    responses(monkeypatch, [None])

    scraper.scrape_series(DE)
    assert delays == [5, 10, 20, 30]


def test_placeholders_are_dropped_from_the_result(monkeypatch):
    products = products_response("B08V893CH7", "B0DM8PNW1Y")
    products["products"][1].update(sku="PL_HLDR_155800DE", release_date="2200-01-01")
    responses(monkeypatch, [series_response("B08V893CH7", "B0DM8PNW1Y"), products])

    result = scraper.scrape_series(DE)
    assert [b["asin"] for b in result["books"]] == ["B08V893CH7"]


def test_a_series_of_only_placeholders_is_a_failure(monkeypatch):
    products = products_response("B0DM8PNW1Y")
    products["products"][0]["sku"] = "PL_HLDR_155800DE"
    responses(monkeypatch, [series_response("B0DM8PNW1Y"), products])

    assert scraper.scrape_series(DE) is None


def test_children_are_batched(monkeypatch):
    asins = [f"B{i:09d}" for i in range(120)]
    calls = []

    def get_json(url):
        calls.append(url)
        if "/catalog/products/" in url:
            return series_response(*asins)
        batch = url.split("asins=")[1].split("&")[0].split(",")
        return products_response(*batch)

    monkeypatch.setattr(scraper, "_get_json", get_json)
    result = scraper.scrape_series(DE)

    # 120 children at 50 per call: one series call plus three product calls.
    assert len(calls) == 4
    assert len(result["books"]) == 120


def test_a_failed_batch_fails_the_whole_scrape(monkeypatch):
    """Half a series looks exactly like a series that lost books."""
    asins = [f"B{i:09d}" for i in range(60)]

    def get_json(url):
        if "/catalog/products/" in url:
            return series_response(*asins)
        batch = url.split("asins=")[1].split("&")[0].split(",")
        return None if batch[0] == asins[50] else products_response(*batch)

    monkeypatch.setattr(scraper, "_get_json", get_json)
    assert scraper.scrape_series(DE) is None


def test_a_non_audible_url_fails_without_calling_out(monkeypatch):
    requested = responses(monkeypatch, [OK_SERIES, OK_PRODUCTS])
    assert scraper.scrape_series("https://example.invalid/series/X/B0937FGLYC") is None
    assert requested == []
