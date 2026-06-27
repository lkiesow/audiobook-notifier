import sqlite3
from typing import Optional

from audiobook_notifier import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS series (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT UNIQUE NOT NULL,
    title           TEXT,
    last_scraped_at TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS books (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id            INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    asin                 TEXT NOT NULL UNIQUE,
    title                TEXT,
    subtitle             TEXT,
    author               TEXT,
    narrator             TEXT,
    duration             TEXT,
    release_date         TEXT,
    language             TEXT,
    book_url             TEXT,
    cover_image_url      TEXT,
    first_seen_at        TEXT DEFAULT (datetime('now')),
    release_notified_at  TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(_SCHEMA)


# --- Series ---

def get_all_series() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.*, COUNT(b.id) as book_count,
                (SELECT GROUP_CONCAT(cover_image_url, '|')
                 FROM (SELECT cover_image_url FROM books
                       WHERE series_id = s.id AND cover_image_url IS NOT NULL
                       ORDER BY release_date LIMIT 3)
                ) as cover_images
            FROM series s
            LEFT JOIN books b ON b.series_id = s.id
            GROUP BY s.id
            ORDER BY s.title
            """
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['cover_images'] = d['cover_images'].split('|') if d.get('cover_images') else []
        result.append(d)
    return result


def get_upcoming_books(limit: int = 3) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT b.title, b.release_date, b.cover_image_url, s.title AS series_title
            FROM books b
            JOIN series s ON s.id = b.series_id
            WHERE b.release_date > date('now')
            ORDER BY b.release_date ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_series(series_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM series WHERE id = ?", (series_id,)
        ).fetchone()
    return dict(row) if row else None


def get_series_by_url(url: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM series WHERE url = ?", (url,)
        ).fetchone()
    return dict(row) if row else None


def add_series(url: str) -> int:
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO series (url) VALUES (?)", (url,))
        return cur.lastrowid


def delete_series(series_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM series WHERE id = ?", (series_id,))


def update_series(series_id: int, title: str, last_scraped_at: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE series SET title = ?, last_scraped_at = ? WHERE id = ?",
            (title, last_scraped_at, series_id),
        )


# --- Books ---

def get_books(series_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM books WHERE series_id = ? ORDER BY release_date",
            (series_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_existing_asins(series_id: int) -> set[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT asin FROM books WHERE series_id = ?", (series_id,)
        ).fetchall()
    return {r["asin"] for r in rows}


def insert_book(series_id: int, book: dict) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO books
                (series_id, asin, title, subtitle, author, narrator,
                 duration, release_date, language, book_url, cover_image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                series_id,
                book["asin"],
                book["title"],
                book["subtitle"],
                book["author"],
                book["narrator"],
                book["duration"],
                book["release_date"],
                book["language"],
                book["book_url"],
                book.get("cover_image_url"),
            ),
        )


def update_book(asin: str, book: dict) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE books SET
                title = ?, subtitle = ?, author = ?, narrator = ?,
                duration = ?, release_date = ?, language = ?, book_url = ?,
                cover_image_url = ?
            WHERE asin = ?
            """,
            (
                book["title"],
                book["subtitle"],
                book["author"],
                book["narrator"],
                book["duration"],
                book["release_date"],
                book["language"],
                book["book_url"],
                book.get("cover_image_url"),
                asin,
            ),
        )


def get_books_releasing_today() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT b.*, s.title as series_title
            FROM books b
            JOIN series s ON s.id = b.series_id
            WHERE b.release_date <= date('now')
              AND b.release_notified_at IS NULL
            """
        ).fetchall()
    return [dict(r) for r in rows]


def mark_release_notified(asin: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE books SET release_notified_at = datetime('now') WHERE asin = ?",
            (asin,),
        )
