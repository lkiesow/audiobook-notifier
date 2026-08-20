from datetime import datetime, timezone

from tests.conftest import make_book

# date('now') in SQLite is UTC, so the "today" boundary has to be too.
TODAY = datetime.now(timezone.utc).date().isoformat()


def _row(db, asin):
    with db.get_connection() as conn:
        return dict(conn.execute(
            "SELECT * FROM books WHERE asin = ?", (asin,)
        ).fetchone())


def test_insert_past_release_is_pre_stamped(db, series_id):
    db.insert_book(series_id, make_book(release_date="2020-01-01"))
    assert _row(db, "B0TEST0001")["release_notified_at"] is not None


def test_insert_future_release_is_not_stamped(db, series_id):
    db.insert_book(series_id, make_book(release_date="2099-01-01"))
    assert _row(db, "B0TEST0001")["release_notified_at"] is None


def test_insert_with_unparsable_date_is_not_stamped(db, series_id):
    # '' <= date('now') is true in SQLite, which used to silently mark a book
    # as already announced so it could never notify.
    db.insert_book(series_id, make_book(release_date=""))
    assert _row(db, "B0TEST0001")["release_notified_at"] is None


def test_update_does_not_clobber_a_known_date_with_junk(db, series_id):
    db.insert_book(series_id, make_book(release_date="2099-01-01"))
    db.update_book("B0TEST0001", make_book(release_date=""))
    assert _row(db, "B0TEST0001")["release_date"] == "2099-01-01"


def test_update_applies_a_valid_new_date(db, series_id):
    db.insert_book(series_id, make_book(release_date="2099-01-01"))
    db.update_book("B0TEST0001", make_book(release_date="2099-02-02"))
    assert _row(db, "B0TEST0001")["release_date"] == "2099-02-02"


def test_unnotified_includes_past_and_today(db, series_id):
    db.insert_book(series_id, make_book(asin="A1", release_date="2020-01-01"))
    db.clear_release_notified("A1")
    assert {b["asin"] for b in db.get_unnotified_books()} == {"A1"}


def test_unnotified_excludes_future_and_already_notified(db, series_id):
    db.insert_book(series_id, make_book(asin="A1", release_date="2099-01-01"))
    db.insert_book(series_id, make_book(asin="A2", release_date="2020-01-01"))
    assert db.get_unnotified_books() == []


def test_unnotified_excludes_malformed_dates(db, series_id):
    db.insert_book(series_id, make_book(asin="A1", release_date=""))
    db.insert_book(series_id, make_book(asin="A2", release_date="12.08.26"))
    assert db.get_unnotified_books() == []


def test_clear_release_notified_round_trip(db, series_id):
    db.insert_book(series_id, make_book(release_date="2020-01-01"))
    db.clear_release_notified("B0TEST0001")
    assert _row(db, "B0TEST0001")["release_notified_at"] is None
    db.mark_release_notified("B0TEST0001")
    assert _row(db, "B0TEST0001")["release_notified_at"] is not None


def test_released_books_newest_first_with_today_included(db, series_id):
    db.insert_book(series_id, make_book(asin="A1", release_date="2020-01-01", title="Old"))
    db.insert_book(series_id, make_book(asin="A2", release_date=TODAY, title="Today"))
    db.insert_book(series_id, make_book(asin="A3", release_date="2023-06-15", title="Middle"))
    books = db.get_released_books()
    assert [b["title"] for b in books] == ["Today", "Middle", "Old"]
    assert books[0]["author"] == "An Author"
    assert books[0]["series_title"] == "Test Series"


def test_released_books_excludes_future(db, series_id):
    db.insert_book(series_id, make_book(asin="A1", release_date="2099-01-01"))
    assert db.get_released_books() == []


def test_released_books_excludes_malformed_dates(db, series_id):
    # '' and non-ISO values sort before date('now') and would read as released.
    db.insert_book(series_id, make_book(asin="A1", release_date=""))
    db.insert_book(series_id, make_book(asin="A2", release_date="Bald verfügbar"))
    assert db.get_released_books() == []


def test_get_existing_books_carries_notification_state(db, series_id):
    db.insert_book(series_id, make_book(asin="A1", release_date="2020-01-01"))
    db.insert_book(series_id, make_book(asin="A2", release_date="2099-01-01"))
    existing = db.get_existing_books(series_id)
    assert set(existing) == {"A1", "A2"}
    assert existing["A1"]["release_notified_at"] is not None
    assert existing["A2"]["release_notified_at"] is None
    assert existing["A2"]["release_date"] == "2099-01-01"
