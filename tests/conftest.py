import pytest

from audiobook_notifier import config, database


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A fresh, empty database. get_connection() reads DATABASE_PATH per call."""
    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "test.db"))
    database.init_db()
    return database


@pytest.fixture
def series_id(db):
    sid = db.add_series("https://www.audible.de/series/Test-Hoerbuecher/B000000000")
    db.update_series(sid, "Test Series", "2026-08-01T00:00:00+00:00")
    return sid


def make_book(asin="B0TEST0001", release_date="2026-08-12", title="Test Book 1"):
    return {
        "asin": asin,
        "title": title,
        "subtitle": "",
        "author": "An Author",
        "narrator": "A Narrator",
        "duration": "10 Std. und 0 Min.",
        "release_date": release_date,
        "language": "Englisch",
        "book_url": "https://www.audible.de/pd/x",
        "cover_image_url": "https://example.invalid/cover.jpg",
    }
