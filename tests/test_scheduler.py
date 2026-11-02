from datetime import datetime

import pytest

from audiobook_notifier import notifications, scheduler, scraper
from tests.conftest import make_book


@pytest.fixture
def sent(monkeypatch):
    """Capture notifications instead of sending them. Delivery succeeds."""
    # Shrink calls["done"] to simulate channels being unreachable.
    calls = {
        "postponed": [], "new_book": [], "releasing_today": [], "channels": [],
        "done": set(notifications.CHANNELS),
    }

    def record(kind):
        def capture(*args, channels=notifications.CHANNELS):
            calls[kind].append(args)
            calls["channels"].append(set(channels))
            return set(channels) & calls["done"]
        return capture

    monkeypatch.setattr(notifications, "notify_release_postponed", record("postponed"))
    monkeypatch.setattr(notifications, "notify_new_book", record("new_book"))
    monkeypatch.setattr(
        notifications, "notify_releasing_today", record("releasing_today")
    )
    return calls


def scrape_returns(monkeypatch, books, series_title="Test Series"):
    monkeypatch.setattr(
        scraper, "scrape_series",
        lambda url: {"series_title": series_title, "books": books},
    )


def notified_at(db, asin, column="release_notified_at"):
    with db.get_connection() as conn:
        return conn.execute(
            f"SELECT {column} FROM books WHERE asin = ?", (asin,)
        ).fetchone()[0]


def pushed_at(db, asin):
    return notified_at(db, asin, "release_pushed_at")


def test_postponed_release_is_rearmed_and_announced(db, series_id, sent, monkeypatch):
    """The Path of Ascension 12 incident.

    Announced on the date Audible advertised at the time, then postponed by a
    week. The book must become eligible again for the real release day.
    """
    db.insert_book(series_id, make_book(release_date="2026-08-05"))
    assert notified_at(db, "B0TEST0001") is not None

    scrape_returns(monkeypatch, [make_book(release_date="2026-08-12")])
    assert scheduler.scrape_and_update(series_id) is True

    assert notified_at(db, "B0TEST0001") is None
    assert sent["postponed"] == [
        ("Test Book 1", "Test Series", "2026-08-05", "2026-08-12")
    ]
    # Eligible again, so the next release check announces it on the real date.
    assert [b["asin"] for b in db.get_unnotified_books()] == ["B0TEST0001"]


def test_unchanged_date_is_not_treated_as_a_postponement(db, series_id, sent, monkeypatch):
    db.insert_book(series_id, make_book(release_date="2020-01-01"))
    scrape_returns(monkeypatch, [make_book(release_date="2020-01-01")])
    scheduler.scrape_and_update(series_id)

    assert notified_at(db, "B0TEST0001") is not None
    assert sent["postponed"] == []


def test_date_moving_earlier_is_not_a_postponement(db, series_id, sent, monkeypatch):
    db.insert_book(series_id, make_book(release_date="2020-06-01"))
    scrape_returns(monkeypatch, [make_book(release_date="2020-01-01")])
    scheduler.scrape_and_update(series_id)

    assert notified_at(db, "B0TEST0001") is not None
    assert sent["postponed"] == []


def test_unannounced_book_moving_later_stays_quiet(db, series_id, sent, monkeypatch):
    db.insert_book(series_id, make_book(release_date="2099-01-01"))
    scrape_returns(monkeypatch, [make_book(release_date="2099-06-01")])
    scheduler.scrape_and_update(series_id)

    assert notified_at(db, "B0TEST0001") is None
    assert sent["postponed"] == []


def test_unparsable_new_date_is_not_a_postponement(db, series_id, sent, monkeypatch):
    """A degraded page yielding no date must not re-arm or rewrite anything."""
    db.insert_book(series_id, make_book(release_date="2020-01-01"))
    scrape_returns(monkeypatch, [make_book(release_date="")])
    scheduler.scrape_and_update(series_id)

    assert notified_at(db, "B0TEST0001") is not None
    assert sent["postponed"] == []
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT release_date FROM books WHERE asin = ?", ("B0TEST0001",)
        ).fetchone()
    assert row[0] == "2020-01-01"


def test_empty_scrape_result_skips_the_update(db, series_id, sent, monkeypatch):
    db.insert_book(series_id, make_book(release_date="2020-01-01"))
    scrape_returns(monkeypatch, [])
    monkeypatch.setattr("audiobook_notifier.notifications.notify_scrape_error",
                        lambda *a: None)

    assert scheduler.scrape_and_update(series_id) is False


def test_check_releasing_today_announces_and_stamps(db, series_id, sent):
    db.insert_book(series_id, make_book(release_date="2020-01-01"))
    db.clear_release_notified("B0TEST0001")

    scheduler.check_releasing_today()

    assert sent["releasing_today"] == [("Test Book 1", "Test Series")]
    assert notified_at(db, "B0TEST0001") is not None


def test_undelivered_release_stays_queued_for_the_next_check(db, series_id, sent):
    """A lost message must not consume the flag — the books table is the outbox."""
    db.insert_book(series_id, make_book(release_date="2020-01-01"))
    db.clear_release_notified("B0TEST0001")
    sent["done"] = set()

    scheduler.check_releasing_today()
    assert notified_at(db, "B0TEST0001") is None

    sent["done"] = set(notifications.CHANNELS)
    scheduler.check_releasing_today()
    assert notified_at(db, "B0TEST0001") is not None
    assert len(sent["releasing_today"]) == 2


def test_first_api_scrape_imports_silently(db, series_id, sent, monkeypatch):
    """The cutover from HTML scraping must not fire a burst of new-book alerts.

    The catalog API lists editions the old series page never showed — re-recordings
    and alternate publishers — so the first API scrape of an existing series turns
    up a pile of books that are new to us but not to the user.
    """
    scrape_returns(monkeypatch, [make_book(), make_book(asin="B0TEST0002")])
    scheduler.scrape_and_update(series_id)

    assert sent["new_book"] == []
    assert len(db.get_books(series_id)) == 2
    assert db.get_series(series_id)["api_backfilled_at"] is not None


def test_books_found_after_the_backfill_are_announced(db, series_id, sent, monkeypatch):
    scrape_returns(monkeypatch, [make_book()])
    scheduler.scrape_and_update(series_id)
    assert sent["new_book"] == []

    scrape_returns(monkeypatch, [make_book(), make_book(asin="B0TEST0002",
                                                        title="Test Book 2")])
    scheduler.scrape_and_update(series_id)

    assert sent["new_book"] == [("Test Book 2", "Test Series")]


def test_a_never_scraped_series_stays_quiet_on_its_first_run(db, sent, monkeypatch):
    """Adding a series imports its back catalogue; none of that is news."""
    sid = db.add_series("https://www.audible.de/series/New-Hoerbuecher/B000000001")
    scrape_returns(monkeypatch, [make_book()])
    scheduler.scrape_and_update(sid)

    assert sent["new_book"] == []


def test_failed_channel_is_retried_alone(db, series_id, sent):
    """Matrix down, push fine: the next check must not push the phone again."""
    db.insert_book(series_id, make_book(release_date="2020-01-01"))
    db.clear_release_notified("B0TEST0001")
    sent["done"] = {"push"}

    scheduler.check_releasing_today()
    assert notified_at(db, "B0TEST0001") is None
    assert pushed_at(db, "B0TEST0001") is not None

    sent["done"] = set(notifications.CHANNELS)
    scheduler.check_releasing_today()
    assert sent["channels"] == [{"matrix", "push"}, {"matrix"}]
    assert notified_at(db, "B0TEST0001") is not None


def test_postponement_rearms_every_channel(db, series_id, sent, monkeypatch):
    db.insert_book(series_id, make_book(release_date="2026-08-05"))
    # Announced by push only, Matrix still owed.
    with db.get_connection() as conn:
        conn.execute("UPDATE books SET release_notified_at = NULL")

    scrape_returns(monkeypatch, [make_book(release_date="2026-08-12")])
    scheduler.scrape_and_update(series_id)

    assert pushed_at(db, "B0TEST0001") is None
    assert len(sent["postponed"]) == 1


class _Clock:
    """Stands in for the datetime class in scheduler, frozen at one moment."""

    def __init__(self, hour, minute):
        self.moment = datetime(2026, 8, 12, hour, minute)

    def now(self, tz=None):
        return self.moment


def test_hourly_retry_waits_for_the_release_check_time(db, series_id, sent, monkeypatch):
    db.insert_book(series_id, make_book(release_date="2020-01-01"))
    db.clear_release_notified("B0TEST0001")
    monkeypatch.setattr(scheduler.config, "RELEASE_CHECK_HOUR", 9)
    monkeypatch.setattr(scheduler.config, "RELEASE_CHECK_MINUTE", 0)

    monkeypatch.setattr(scheduler, "datetime", _Clock(8, 59))
    scheduler.retry_owed_releases()
    assert sent["releasing_today"] == []

    monkeypatch.setattr(scheduler, "datetime", _Clock(9, 0))
    scheduler.retry_owed_releases()
    assert len(sent["releasing_today"]) == 1
