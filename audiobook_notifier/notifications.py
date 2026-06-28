import logging
import uuid
from urllib.parse import quote

import requests

from audiobook_notifier import config

logger = logging.getLogger(__name__)

_resolved_room_id: str | None = None


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
    try:
        r = requests.get(
            f"{base}/_matrix/client/v3/directory/room/{quote(room, safe='')}",
            timeout=10,
        )
        r.raise_for_status()
        _resolved_room_id = r.json()["room_id"]
        return _resolved_room_id
    except Exception:
        logger.exception("Failed to resolve Matrix room alias %s", room)
        return None


def _send_matrix(text: str) -> None:
    room_id = _resolve_room_id()
    if not room_id:
        return
    base = config.MATRIX_HOMESERVER.rstrip("/")
    txn_id = str(uuid.uuid4())
    url = (
        f"{base}/_matrix/client/v3/rooms/"
        f"{quote(room_id, safe='')}/send/m.room.message/{txn_id}"
    )
    try:
        r = requests.put(
            url,
            json={"msgtype": "m.notice", "body": text},
            headers={"Authorization": f"Bearer {config.MATRIX_ACCESS_TOKEN}"},
            timeout=10,
        )
        r.raise_for_status()
    except Exception:
        logger.exception("Failed to send Matrix notification")


def notify_new_book(book_title: str, series_title: str) -> None:
    logger.info("New book: %s in %s", book_title, series_title)
    if _matrix_enabled():
        _send_matrix(f"New audiobook in {series_title}: {book_title}")


def notify_releasing_today(book_title: str, series_title: str) -> None:
    logger.info("Releasing today: %s in %s", book_title, series_title)
    if _matrix_enabled():
        _send_matrix(f"Releasing today in {series_title}: {book_title}")


def notify_scrape_error(series_label: str) -> None:
    if _matrix_enabled() and config.NOTIFY_SCRAPE_ERRORS:
        _send_matrix(f"⚠ Scrape failed for {series_label}")
