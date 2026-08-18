import pytest

from audiobook_notifier import scraper

# The same series in two marketplaces. Note the ASINs differ: Audible mints
# separate ones per storefront, which is why the API host has to follow the URL.
DE = "https://www.audible.de/series/Dungeon-Crawler-Carl-Hoerbuecher/B0937FGLYC"
COM = "https://www.audible.com/series/Dungeon-Crawler-Carl-Audiobooks/B0937JMKYV"
UK = "https://www.audible.co.uk/series/Dungeon-Crawler-Carl-Audiobooks/B0937JMKYV"


def product(**overrides):
    """A product object shaped like the catalog API's, trimmed to what we read."""
    base = {
        "asin": "B08V893CH7",
        "title": "Dungeon Crawler Carl",
        "subtitle": "A LitRPG/Gamelit Adventure",
        "authors": [{"name": "Matt Dinniman"}],
        "narrators": [{"name": "Jeff Hays"}],
        "runtime_length_min": 811,
        "release_date": "2021-01-28",
        "language": "english",
        "sku": "BK_ACX0_234484DE",
        "product_images": {"500": "https://m.media-amazon.com/images/I/51HIZdnqASL._SL500_.jpg"},
    }
    base.update(overrides)
    return base


# --- Marketplaces ---

@pytest.mark.parametrize("url,expected", [
    (DE, "https://api.audible.de/1.0"),
    (COM, "https://api.audible.com/1.0"),
    (UK, "https://api.audible.co.uk/1.0"),
    # The UI accepts a bare host too.
    ("https://audible.de/series/X/B0937FGLYC", "https://api.audible.de/1.0"),
])
def test_api_host_follows_the_marketplace(url, expected):
    assert scraper._api_base(url) == expected


def test_non_audible_host_is_rejected():
    assert scraper._api_base("https://example.invalid/series/X/B0937FGLYC") is None
    assert scraper._api_base("https://notaudible.de/series/X/B0937FGLYC") is None


@pytest.mark.parametrize("url,host", [
    (DE, "www.audible.de"),
    (COM, "www.audible.com"),
    (UK, "www.audible.co.uk"),
])
def test_book_links_stay_on_the_series_marketplace(url, host):
    """A .com series must never hand out an audible.de book link."""
    book = scraper._to_book(product(), scraper._web_base(url))
    assert book["book_url"] == f"https://{host}/pd/B08V893CH7"


# --- Series ASIN ---

def test_series_asin_is_the_last_path_segment():
    assert scraper._series_asin(DE) == "B0937FGLYC"
    assert scraper._series_asin(COM) == "B0937JMKYV"


def test_series_asin_tolerates_a_trailing_slash():
    assert scraper._series_asin(DE + "/") == "B0937FGLYC"


def test_series_asin_rejects_a_non_asin_segment():
    assert scraper._series_asin("https://www.audible.de/series/Some-Series") is None
    assert scraper._series_asin("https://www.audible.de/") is None


# --- Field mapping ---

def test_maps_a_product_to_a_book():
    book = scraper._to_book(product(), scraper._web_base(DE))
    assert book == {
        "title": "Dungeon Crawler Carl",
        "subtitle": "A LitRPG/Gamelit Adventure",
        "author": "Matt Dinniman",
        "narrator": "Jeff Hays",
        "duration": "13 Std. und 31 Min.",
        "release_date": "2021-01-28",
        "language": "english",
        "asin": "B08V893CH7",
        "book_url": "https://www.audible.de/pd/B08V893CH7",
        "cover_image_url": "https://m.media-amazon.com/images/I/51HIZdnqASL._SL500_.jpg",
    }


def test_missing_optional_fields_become_empty():
    book = scraper._to_book({"asin": "B08V893CH7"}, scraper._web_base(DE))
    assert book["subtitle"] == ""
    assert book["author"] == ""
    assert book["narrator"] == ""
    assert book["duration"] == ""
    assert book["cover_image_url"] is None


def test_first_contributor_wins_when_there_are_several():
    book = scraper._to_book(
        product(narrators=[{"name": "Jeff Hays"}, {"name": "Travis Baldree"}]),
        scraper._web_base(DE),
    )
    assert book["narrator"] == "Jeff Hays"


def test_a_non_iso_release_date_is_dropped_rather_than_stored():
    # release_date is compared lexicographically against date('now'), so a
    # foreign-format value would read as "already released".
    book = scraper._to_book(product(release_date="28.01.2021"), scraper._web_base(DE))
    assert book["release_date"] == ""


@pytest.mark.parametrize("minutes,expected", [
    (811, "13 Std. und 31 Min."),
    (1720, "28 Std. und 40 Min."),
    (45, "45 Min."),
    (60, "1 Std."),
    (300, "5 Std."),
    (None, ""),
    (0, ""),
])
def test_format_duration(minutes, expected):
    assert scraper._format_duration(minutes) == expected


# --- Placeholders ---

def test_placeholder_products_are_detected_by_sku():
    assert scraper._is_placeholder(product(sku="PL_HLDR_155800DE"))
    assert not scraper._is_placeholder(product())


def test_placeholder_detection_falls_back_to_sku_lite():
    assert scraper._is_placeholder({"sku_lite": "PL_HLDR_155800"})


def test_a_real_product_dated_2200_is_not_treated_as_a_placeholder():
    assert not scraper._is_placeholder(product(release_date="2200-01-01"))


def test_is_iso_date():
    assert scraper.is_iso_date("2026-08-12")
    assert not scraper.is_iso_date("")
    assert not scraper.is_iso_date(None)
    assert not scraper.is_iso_date("12.08.26")
    assert not scraper.is_iso_date("2026-02-30")
