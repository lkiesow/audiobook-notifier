import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from audiobook_notifier import config, database, metrics, notifications, scraper

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler(job_defaults={"misfire_grace_time": 3600})


def _handle_postponement(old: dict, book: dict, series_title: str) -> None:
    """Re-arm the release notification when a release moved to a later date.

    release_notified_at is a one-shot flag. Without this, a book announced on
    the release date Audible advertised at the time stays marked as announced
    forever, and the actual release day passes in silence.
    """
    old_date = old["release_date"]
    new_date = book["release_date"]
    if old["release_notified_at"] is None:
        return
    if not (scraper.is_iso_date(old_date) and scraper.is_iso_date(new_date)):
        return
    if new_date <= old_date:
        return

    database.clear_release_notified(book["asin"])
    notifications.notify_release_postponed(
        book["title"], series_title, old_date, new_date
    )


def scrape_and_update(series_id: int) -> bool:
    series = database.get_series(series_id)
    if not series:
        logger.warning("Series %d not found; skipping scrape", series_id)
        return False

    result = scraper.scrape_series(series["url"])
    if not result or not result["books"]:
        # scrape_series already retried and logged why. Skip the update
        # entirely rather than writing a half-scraped page over good data.
        logger.error(
            "Failed to scrape series %d (%s); skipping update to avoid data loss",
            series_id,
            series["url"],
        )
        notifications.notify_scrape_error(series["title"] or series["url"])
        metrics.scrapes_total.labels(result="error").inc()
        return False

    books = result["books"]
    existing = database.get_existing_books(series_id)

    # A series is only news once it has been seen at least once, and once it has
    # been through a catalog-API scrape — the move off HTML surfaces editions the
    # old series page never listed, and those are backfill, not new releases.
    notify_new = (
        series["last_scraped_at"] is not None
        and series["api_backfilled_at"] is not None
    )

    for book in books:
        asin = book.get("asin")
        if not asin:
            continue
        if asin not in existing:
            try:
                database.insert_book(series_id, book)
                metrics.new_books_discovered_total.inc()
                if notify_new:
                    notifications.notify_new_book(book["title"], result["series_title"])
            except sqlite3.IntegrityError:
                logger.warning(
                    "ASIN %s already exists in another series; skipping insert", asin
                )
        else:
            database.update_book(asin, book)
            _handle_postponement(existing[asin], book, result["series_title"])

    database.mark_api_backfilled(series_id)
    database.update_series(
        series_id,
        result["series_title"],
        datetime.now(timezone.utc).isoformat(),
    )
    metrics.scrapes_total.labels(result="success").inc()
    return True


def scrape_all_series() -> None:
    series_list = database.get_all_series()
    logger.info("Scheduled scrape starting for %d series", len(series_list))
    for i, series in enumerate(series_list):
        scrape_and_update(series["id"])
        if i < len(series_list) - 1:
            time.sleep(config.SCRAPE_DELAY_SECONDS)
    logger.info("Scheduled scrape complete")
    metrics.last_scrape_timestamp_seconds.set(time.time())


def check_releasing_today() -> None:
    books = database.get_unnotified_books()
    logger.info("Release check found %d book(s) releasing", len(books))
    for book in books:
        # Only stamp on success. The books table doubles as the outbox:
        # release_notified_at IS NULL means "still owed", and the daily cron
        # plus the startup catch-up job redeliver it.
        if notifications.notify_releasing_today(book["title"], book["series_title"]):
            database.mark_release_notified(book["asin"])


def scrape_series_now(series_id: int) -> None:
    t = threading.Thread(
        target=scrape_and_update,
        args=(series_id,),
        daemon=True,
        name=f"scrape-{series_id}",
    )
    t.start()


def start_scheduler() -> None:
    _scheduler.add_job(
        scrape_all_series,
        trigger=IntervalTrigger(hours=config.SCRAPE_INTERVAL_HOURS),
        id="scrape_all",
        coalesce=True,
        max_instances=1,
    )
    _scheduler.add_job(
        check_releasing_today,
        trigger=CronTrigger(hour=config.RELEASE_CHECK_HOUR, minute=config.RELEASE_CHECK_MINUTE),
        id="check_releasing",
        coalesce=True,
        max_instances=1,
    )
    # Catch up immediately on any release that came due while the process was
    # down or during a missed 09:00 slot — an in-memory cron never fires
    # retroactively. Safe to run every start: it only notifies books that are
    # past-release AND not yet notified, then marks them.
    _scheduler.add_job(
        check_releasing_today,
        id="check_releasing_startup",
    )
    _scheduler.start()
    logger.info(
        "Scheduler started (scrape every %dh, release check daily at %02d:%02d)",
        config.SCRAPE_INTERVAL_HOURS,
        config.RELEASE_CHECK_HOUR,
        config.RELEASE_CHECK_MINUTE,
    )


def shutdown_scheduler() -> None:
    _scheduler.shutdown(wait=False)
