import json
import logging
import time
import uuid
from typing import Callable, Iterable, Optional
from urllib.parse import quote, urlparse

import requests
from py_vapid import Vapid
from pywebpush import WebPusher, WebPushException

from audiobook_notifier import config, database, metrics

logger = logging.getLogger(__name__)

CHANNELS = frozenset({"matrix", "push"})

# Push services answer these for a subscription that no longer exists, e.g.
# because the app was uninstalled or notifications were revoked.
_PUSH_GONE = (404, 410)

_resolved_room_id: str | None = None


def _retry_after_seconds(
    response: requests.Response, attempt: int, backoff: float, max_backoff: float
) -> float:
    """Backoff before the next attempt, honouring the server's own rate limit.

    Matrix sends retry_after_ms in the body, push services a Retry-After header.
    """
    if response is not None and response.status_code == 429:
        header = response.headers.get("Retry-After", "")
        if header.isdigit():
            return min(int(header), max_backoff)
        try:
            ms = response.json().get("retry_after_ms")
        except ValueError:
            ms = None
        if isinstance(ms, (int, float)):
            return min(ms / 1000, max_backoff)
    return min(backoff * 2 ** (attempt - 1), max_backoff)


def _request_with_retry(
    send: Callable[[], requests.Response],
    what: str,
    attempts: int,
    backoff: float,
    max_backoff: float,
    final: tuple[int, ...] = (),
) -> Optional[requests.Response]:
    """Run send() until it succeeds, giving up on errors that cannot heal.

    Retries transport failures, 5xx and 429. A 4xx other than 429 means a bad
    token, room or payload — retrying only delays the log entry. A status in
    `final` is returned as is, for callers that handle it themselves.
    """
    for attempt in range(1, attempts + 1):
        response = None
        try:
            response = send()
            if response.status_code in final:
                return response
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            retryable = response is None or response.status_code >= 500 \
                or response.status_code == 429
            last = attempt == attempts
            if not retryable or last:
                logger.error("%s failed (attempt %d): %s", what, attempt, e)
                return None
            delay = _retry_after_seconds(response, attempt, backoff, max_backoff)
            logger.warning(
                "%s failed (attempt %d/%d), retrying in %.1fs: %s",
                what, attempt, attempts, delay, e,
            )
            time.sleep(delay)
    return None


def _matrix_request(send: Callable[[], requests.Response], what: str):
    return _request_with_retry(
        send,
        what,
        config.MATRIX_RETRY_ATTEMPTS,
        config.MATRIX_RETRY_BACKOFF_SECONDS,
        config.MATRIX_RETRY_MAX_BACKOFF_SECONDS,
    )


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
    response = _matrix_request(
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
    response = _matrix_request(
        lambda: requests.put(
            url,
            json={"msgtype": msgtype, "body": text},
            headers={"Authorization": f"Bearer {config.MATRIX_ACCESS_TOKEN}"},
            timeout=config.MATRIX_TIMEOUT_SECONDS,
        ),
        "Sending Matrix notification",
    )
    return response is not None


def push_enabled() -> bool:
    return bool(
        config.VAPID_PUBLIC_KEY
        and config.VAPID_PRIVATE_KEY
        and config.VAPID_SUBJECT
    )


def _vapid_headers(endpoint: str) -> dict:
    """Sign a VAPID token for the push service that owns the endpoint."""
    parsed = urlparse(endpoint)
    claims = {
        "sub": config.VAPID_SUBJECT,
        "aud": f"{parsed.scheme}://{parsed.netloc}",
        "exp": int(time.time()) + 12 * 60 * 60,
    }
    return Vapid.from_string(config.VAPID_PRIVATE_KEY).sign(claims)


def _send_push_to(subscription: dict, payload: dict) -> bool:
    """Push to one device. False only for a failure worth retrying later.

    A device the push service no longer knows is removed and counts as done,
    as does one whose stored keys cannot be used — neither will ever recover.
    """
    endpoint = subscription["endpoint"]
    info = {
        "endpoint": endpoint,
        "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth"]},
    }
    try:
        headers = _vapid_headers(endpoint)
    except ValueError as e:
        # Our key is broken, not the device: keep the subscription.
        logger.error("Cannot sign push request, check VAPID_PRIVATE_KEY: %s", e)
        return False
    try:
        pusher = WebPusher(info)
        response = _request_with_retry(
            lambda: pusher.send(
                json.dumps(payload),
                headers=headers,
                ttl=config.PUSH_TTL_SECONDS,
                timeout=config.PUSH_TIMEOUT_SECONDS,
            ),
            "Sending push notification",
            config.PUSH_RETRY_ATTEMPTS,
            config.PUSH_RETRY_BACKOFF_SECONDS,
            config.PUSH_RETRY_MAX_BACKOFF_SECONDS,
            final=_PUSH_GONE,
        )
    except (WebPushException, ValueError) as e:
        logger.warning("Removing unusable push subscription %s: %s", endpoint, e)
        database.delete_push_subscription(endpoint)
        return True
    if response is None:
        return False
    if response.status_code in _PUSH_GONE:
        logger.info("Push subscription expired, removing %s", endpoint)
        database.delete_push_subscription(endpoint)
    return True


def _push_payload(text: str, kind: str) -> dict:
    # The tag makes a repeat of the same message replace the earlier one on
    # the device instead of stacking a second notification.
    return {"title": "Audiobook Notifier", "body": text, "tag": f"{kind}:{text}", "url": "/"}


def _count(ok: bool, kind: str, channel: str) -> bool:
    counter = metrics.notifications_sent_total if ok else metrics.notifications_failed_total
    counter.labels(type=kind, channel=channel).inc()
    return ok


def _deliver(
    text: str,
    msgtype: str,
    kind: str,
    push_on: bool,
    channels: Iterable[str] = CHANNELS,
) -> set[str]:
    """Send on the given channels and return the ones that are done.

    A channel is done when it delivered, or when it had nothing to deliver:
    not configured, the event switched off for push, or no device subscribed.
    Callers that queue undelivered messages would otherwise keep them forever,
    and replay them all the day the channel is switched on.
    """
    done = set()
    if "matrix" in channels:
        if not _matrix_enabled() or _count(_send_matrix(text, msgtype), kind, "matrix"):
            done.add("matrix")
    if "push" in channels:
        subscriptions = database.get_push_subscriptions() \
            if push_on and push_enabled() else []
        payload = _push_payload(text, kind)
        results = [_send_push_to(s, payload) for s in subscriptions]
        if not results or _count(all(results), kind, "push"):
            done.add("push")
    return done


def send_push_welcome(subscription: dict) -> bool:
    """Confirm a newly subscribed device, so the user sees push works."""
    return _send_push_to(
        subscription,
        _push_payload("Notifications are enabled on this device.", "welcome"),
    )


def notify_new_book(book_title: str, series_title: str) -> set[str]:
    logger.info("New book: %s in %s", book_title, series_title)
    return _deliver(
        f"New audiobook in {series_title}: {book_title}",
        config.MATRIX_MSGTYPE_NEW_BOOK,
        "new_book",
        config.PUSH_NEW_BOOK,
    )


def notify_releasing_today(
    book_title: str, series_title: str, channels: Iterable[str] = CHANNELS
) -> set[str]:
    logger.info("Releasing today: %s in %s", book_title, series_title)
    return _deliver(
        f"Releasing today in {series_title}: {book_title}",
        config.MATRIX_MSGTYPE_RELEASING_TODAY,
        "releasing_today",
        config.PUSH_RELEASING_TODAY,
        channels,
    )


def notify_release_postponed(
    book_title: str, series_title: str, old_date: str, new_date: str
) -> set[str]:
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
        config.PUSH_POSTPONED,
    )


def notify_scrape_error(series_label: str) -> set[str]:
    if not config.NOTIFY_SCRAPE_ERRORS:
        return set(CHANNELS)
    return _deliver(
        f"⚠ Scrape failed for {series_label}",
        config.MATRIX_MSGTYPE_SCRAPE_ERROR,
        "scrape_error",
        config.PUSH_SCRAPE_ERROR,
    )
