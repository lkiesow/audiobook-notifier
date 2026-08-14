from audiobook_notifier import scraper

DE = "https://www.audible.de/series/X/B0"
COM = "https://www.audible.com/series/X/B0"


def test_german_format():
    assert scraper.parse_release_date("12.08.2026", DE) == "2026-08-12"


def test_numeric_format_is_day_first_outside_dot_com():
    assert scraper.parse_release_date("12-08-26", DE) == "2026-08-12"


def test_numeric_format_is_month_first_on_dot_com():
    assert scraper.parse_release_date("12-08-26", COM) == "2026-12-08"


def test_two_digit_year_pivots_to_last_century():
    # Years after the current one are read as 19xx.
    assert scraper.parse_release_date("12-08-99", DE) == "1999-08-12"


def test_empty_input():
    assert scraper.parse_release_date("", DE) == ""


def test_impossible_date_is_rejected():
    assert scraper.parse_release_date("99.99.9999", DE) == ""


def test_month_13_is_rejected():
    assert scraper.parse_release_date("01.13.2026", DE) == ""


def test_unrecognised_format_is_not_passed_through():
    # Must not leak through: "12. August 2026" sorts before every ISO date.
    assert scraper.parse_release_date("Erscheint am 12. August 2026", DE) == ""


def test_is_iso_date():
    assert scraper.is_iso_date("2026-08-12")
    assert not scraper.is_iso_date("")
    assert not scraper.is_iso_date(None)
    assert not scraper.is_iso_date("12.08.26")
    assert not scraper.is_iso_date("2026-02-30")
