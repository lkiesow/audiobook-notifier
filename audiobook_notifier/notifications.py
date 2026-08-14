import logging
import time
import uuid
from typing import Callable, Optional
from urllib.parse import quote

import requests

from audiobook_notifier import config, metrics

logger = logging.getLogger(__name__)

_resolved_room_id: str | None = None


def _retry_after_seconds(response: requests.Response, attempt: int) -> float:
    """Backoff before the next attempt, honouring the server's own rate limit."""
    if response is not None and response.status_code == 429:
        try:
            ms = response.json().get("retry_after_ms")
        except ValueError:
            ms = None
        if isinstance(ms, (int, float)):
            return min(ms / 1000, config.MATRIX_RETRY_MAX_BACKOFF_SECONDS)
    backoff = config.MATRIX_RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1)
    return min(backoff, config.MATRIX_RETRY_MAX_BACKOFF_SECONDS)


def _request_with_retry(
    send: Callable[[], requests.Response], what: str
) -> Optional[requests.Response]:
    """Run send() until it succeeds, giving up on errors that cannot heal.

    Retries transport failures, 5xx and 429. A 4xx other than 429 means a bad
    token, room or payload — retrying only delays the log entry.
    """
    for attempt in range(1, config.MATRIX_RETRY_ATTEMPTS + 1):
        response = None
        try:
            response = send()
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            retryable = response is None or response.status_code >= 500 \
                or response.status_code == 429
            last = attempt == config.MATRIX_RETRY_ATTEMPTS
            if not retryable or last:
                logger.error("%s failed (attempt %d): %s", what, attempt, e)
                return None
            delay = _retry_after_seconds(response, attempt)
            logger.warning(
                "%s failed (attempt %d/%d), retrying in %.1fs: %s",
                what, attempt, config.MATRIX_RETRY_ATTEMPTS, delay, e,
            )
            time.sleep(delay)
    return None


def _matrix_enabled() -> bool:
    return bool(
        config.MATRIX_HOMESERVER
        and config.MATRIX_ACCESS_TOKEN
        and config.MATRIX_ROOM_ID
    )


def _resolve_room_id() -> str | None:
    global _resolved_room_id
    if _resolved_room_id:
        return _resolved_room_id
    room = config.MATRIX_ROOM_ID
    if room.startswith("!"):
        _resolved_room_id = room
        return _resolved_room_id
    base = config.MATRIX_HOMESERVER.rstrip("/")
    url = f"{base}/_matrix/client/v3/directory/room/{quote(room, safe='')}"
    response = _request_with_retry(
        lambda: requests.get(url, timeout=config.MATRIX_TIMEOUT_SECONDS),
        f"Resolving Matrix room alias {room}",
    )
    if response is None:
        return None
    try:
        _resolved_room_id = response.json()["room_id"]
    except (ValueError, KeyError):
        logger.error("Matrix room alias %s resolved to an unexpected payload", room)
        return None
    return _resolved_room_id


def _send_matrix(text: str, msgtype: str = "m.notice") -> bool:
    room_id = _resolve_room_id()
    if not room_id:
        return False
    base = config.MATRIX_HOMESERVER.rstrip("/")
    # One transaction ID for all attempts: Matrix deduplicates on it, so a
    # retry cannot post the message twice if the first PUT did land.
    txn_id = str(uuid.uuid4())
    url = (
        f"{base}/_matrix/client/v3/rooms/"
        f"{quote(room_id, safe='')}/send/m.room.message/{txn_id}"
    )
    response = _request_with_retry(
        lambda: requests.put(
            url,
            json={"msgtype": msgtype, "body": text},
            headers={"Authorization": f"Bearer {config.MATRIX_ACCESS_TOKEN}"},
            timeout=config.MATRIX_TIMEOUT_SECONDS,
        ),
        "Sending Matrix notification",
    )
    return response is not None


def _deliver(text: str, msgtype: str, kind: str) -> bool:
    """Send and count. Returns True when Matrix is off — nothing to redeliver."""
    if not _matrix_enabled():
        return True
    if _send_matrix(text, msgtype):
        metrics.notifications_sent_total.labels(type=kind).inc()
        return True
    metrics.notifications_failed_total.labels(type=kind).inc()
    return False


def notify_new_book(book_title: str, series_title: str) -> bool:
    logger.info("New book: %s in %s", book_title, series_title)
    return _deliver(
        f"New audiobook in {series_title}: {book_title}",
        config.MATRIX_MSGTYPE_NEW_BOOK,
        "new_book",
    )


def notify_releasing_today(book_title: str, series_title: str) -> bool:
    logger.info("Releasing today: %s in %s", book_title, series_title)
    return _deliver(
        f"Releasing today in {series_title}: {book_title}",
        config.MATRIX_MSGTYPE_RELEASING_TODAY,
        "releasing_today",
    )


def notify_release_postponed(
    book_title: str, series_title: str, old_date: str, new_date: str
) -> bool:
    logger.info(
        "Release postponed: %s in %s moved from %s to %s",
        book_title,
        series_title,
        old_date,
        new_date,
    )
    return _deliver(
        f"↪ Postponed in {series_title}: {book_title} "
        f"moved from {old_date} to {new_date}",
        config.MATRIX_MSGTYPE_POSTPONED,
        "postponed",
    )


def notify_scrape_error(series_label: str) -> bool:
    if not config.NOTIFY_SCRAPE_ERRORS:
        return True
    return _deliver(
        f"⚠ Scrape failed for {series_label}",
        config.MATRIX_MSGTYPE_SCRAPE_ERROR,
        "scrape_error",
    )
