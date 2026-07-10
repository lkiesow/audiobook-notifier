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


def scrape_and_update(series_id: int) -> bool:
    series = database.get_series(series_id)
    if not series:
        logger.warning("Series %d not found; skipping scrape", series_id)
        return False

    result = scraper.scrape_series(series["url"])
    if result is None:
        logger.error("Failed to scrape series %d (%s)", series_id, series["url"])
        notifications.notify_scrape_error(series["title"] or series["url"])
        metrics.scrapes_total.labels(result="error").inc()
        return False

    books = result["books"]
    if not books:
        logger.error(
            "Scraper returned no books for series %d (%s); skipping update to avoid data loss",
            series_id,
            series["url"],
        )
        notifications.notify_scrape_error(series["title"] or series["url"])
        metrics.scrapes_total.labels(result="error").inc()
        return False

    existing_asins = database.get_existing_asins(series_id)

    for book in books:
        asin = book.get("asin")
        if not asin:
            continue
        if asin not in existing_asins:
            try:
                database.insert_book(series_id, book)
                metrics.new_books_discovered_total.inc()
                if series["last_scraped_at"] is not None:
                    notifications.notify_new_book(book["title"], result["series_title"])
            except sqlite3.IntegrityError:
                logger.warning(
                    "ASIN %s already exists in another series; skipping insert", asin
                )
        else:
            database.update_book(asin, book)

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
    books = database.get_books_releasing_today()
    logger.info("Release check found %d book(s) releasing", len(books))
    for book in books:
        notifications.notify_releasing_today(book["title"], book["series_title"])
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
        trigger=CronTrigger(hour=9, minute=0),
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
        "Scheduler started (scrape every %dh, release check daily at 09:00)",
        config.SCRAPE_INTERVAL_HOURS,
    )


def shutdown_scheduler() -> None:
    _scheduler.shutdown(wait=False)
