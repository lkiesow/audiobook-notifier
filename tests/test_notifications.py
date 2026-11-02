import json

import pytest
import requests

from audiobook_notifier import config, notifications


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}
        self.text = ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


@pytest.fixture(autouse=True)
def no_push(monkeypatch):
    """Push stays off unless a test turns it on, whatever .env says."""
    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY", "")


@pytest.fixture
def matrix(monkeypatch):
    """Matrix configured with a plain room ID, so no alias lookup happens."""
    monkeypatch.setattr(config, "MATRIX_HOMESERVER", "https://matrix.invalid")
    monkeypatch.setattr(config, "MATRIX_ACCESS_TOKEN", "token")
    monkeypatch.setattr(config, "MATRIX_ROOM_ID", "!room:matrix.invalid")
    monkeypatch.setattr(config, "MATRIX_RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(notifications, "_resolved_room_id", None)
    monkeypatch.setattr(notifications.time, "sleep", lambda s: None)


class Recorder(list):
    """Records every PUT and replies with a scripted sequence of responses."""

    def __init__(self):
        super().__init__()
        self.responses = []

    def __call__(self, url, **kwargs):
        self.append({"url": url, **kwargs})
        return self.responses.pop(0) if self.responses else FakeResponse(200)


@pytest.fixture
def puts(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(requests, "put", recorder)
    return recorder


def test_send_succeeds_first_try(matrix, puts):
    assert "matrix" in notifications.notify_releasing_today("A Book", "A Series")
    assert len(puts) == 1
    assert puts[0]["json"]["body"] == "Releasing today in A Series: A Book"


def test_retries_a_server_error_and_reuses_the_transaction_id(matrix, puts):
    puts.responses.extend([FakeResponse(500), FakeResponse(200)])

    assert "matrix" in notifications.notify_releasing_today("A Book", "A Series")
    assert len(puts) == 2
    # Matrix deduplicates on the transaction ID in the URL, so a retry after a
    # response we never saw cannot post the message twice.
    assert puts[0]["url"] == puts[1]["url"]


def test_gives_up_after_the_configured_attempts(matrix, puts, monkeypatch):
    monkeypatch.setattr(config, "MATRIX_RETRY_ATTEMPTS", 3)
    puts.responses.extend([FakeResponse(500)] * 3)

    assert "matrix" not in notifications.notify_releasing_today("A Book", "A Series")
    assert len(puts) == 3


def test_does_not_retry_a_client_error(matrix, puts):
    puts.responses.append(FakeResponse(403))

    assert "matrix" not in notifications.notify_releasing_today("A Book", "A Series")
    assert len(puts) == 1


def test_retries_a_rate_limit(matrix, puts):
    puts.responses.extend([
        FakeResponse(429, {"retry_after_ms": 50}),
        FakeResponse(200),
    ])

    assert "matrix" in notifications.notify_releasing_today("A Book", "A Series")
    assert len(puts) == 2


def test_retries_a_transport_failure(matrix, puts, monkeypatch):
    attempts = []

    def put(url, **kwargs):
        attempts.append(url)
        if len(attempts) == 1:
            raise requests.ConnectionError("boom")
        return FakeResponse(200)

    monkeypatch.setattr(requests, "put", put)
    assert "matrix" in notifications.notify_releasing_today("A Book", "A Series")
    assert len(attempts) == 2


def test_room_alias_is_resolved_and_cached(matrix, puts, monkeypatch):
    monkeypatch.setattr(config, "MATRIX_ROOM_ID", "#alias:matrix.invalid")
    gets = []

    def get(url, **kwargs):
        gets.append(url)
        return FakeResponse(200, {"room_id": "!resolved:matrix.invalid"})

    monkeypatch.setattr(requests, "get", get)

    assert "matrix" in notifications.notify_releasing_today("A", "S")
    assert "matrix" in notifications.notify_releasing_today("B", "S")
    assert len(gets) == 1
    assert "%21resolved" in puts[0]["url"]


def test_unreachable_matrix_is_not_reported_as_delivered(matrix, puts):
    puts.responses.append(FakeResponse(502))
    puts.responses.append(FakeResponse(502))
    puts.responses.append(FakeResponse(502))

    assert "matrix" not in notifications.notify_release_postponed("B", "S", "2026-08-05", "2026-08-12")


def test_disabled_matrix_counts_as_delivered(monkeypatch):
    monkeypatch.setattr(config, "MATRIX_HOMESERVER", "")
    # Nothing to redeliver when notifications are switched off, so the caller
    # must not keep the book queued forever.
    assert "matrix" in notifications.notify_releasing_today("A Book", "A Series")


# --- Push ---

class FakePusher:
    """Stands in for pywebpush.WebPusher, replying with scripted responses."""

    sent = []
    responses = []

    def __init__(self, info):
        self.info = info

    def send(self, data, headers=None, ttl=0, timeout=None):
        FakePusher.sent.append({"endpoint": self.info["endpoint"], "data": data,
                                "headers": headers, "ttl": ttl})
        return FakePusher.responses.pop(0) if FakePusher.responses else FakeResponse(201)


@pytest.fixture
def push(db, monkeypatch):
    """Push configured with a real key pair and one subscribed device."""
    from audiobook_notifier.setup_push import generate_keys

    public, private = generate_keys()
    monkeypatch.setattr(config, "VAPID_PUBLIC_KEY", public)
    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY", private)
    monkeypatch.setattr(config, "VAPID_SUBJECT", "mailto:test@example.invalid")
    monkeypatch.setattr(config, "PUSH_RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(config, "MATRIX_HOMESERVER", "")
    monkeypatch.setattr(notifications.time, "sleep", lambda s: None)
    monkeypatch.setattr(notifications, "WebPusher", FakePusher)
    FakePusher.sent = []
    FakePusher.responses = []
    db.save_push_subscription("https://push.invalid/phone", "p256dh", "auth", "UA")
    return FakePusher


def test_push_is_sent_signed_with_the_message(push):
    assert "push" in notifications.notify_releasing_today("A Book", "A Series")
    assert len(push.sent) == 1
    sent = push.sent[0]
    assert json.loads(sent["data"])["body"] == "Releasing today in A Series: A Book"
    assert sent["headers"]["Authorization"].startswith("vapid t=")
    assert sent["ttl"] == config.PUSH_TTL_SECONDS


def test_push_server_error_is_retried_then_reported(push, db, monkeypatch):
    monkeypatch.setattr(config, "PUSH_RETRY_ATTEMPTS", 2)
    push.responses.extend([FakeResponse(503), FakeResponse(503)])

    assert "push" not in notifications.notify_releasing_today("A Book", "A Series")
    assert len(push.sent) == 2
    assert len(db.get_push_subscriptions()) == 1


def test_gone_device_is_removed_and_counts_as_done(push, db):
    push.responses.append(FakeResponse(410))

    assert "push" in notifications.notify_releasing_today("A Book", "A Series")
    assert db.get_push_subscriptions() == []


def test_one_failing_device_fails_the_push_channel(push, db, monkeypatch):
    monkeypatch.setattr(config, "PUSH_RETRY_ATTEMPTS", 1)
    db.save_push_subscription("https://push.invalid/tablet", "p256dh", "auth", "UA")
    push.responses.extend([FakeResponse(201), FakeResponse(500)])

    assert "push" not in notifications.notify_releasing_today("A Book", "A Series")
    assert len(push.sent) == 2


def test_event_switched_off_for_push_counts_as_done(push, monkeypatch):
    monkeypatch.setattr(config, "PUSH_RELEASING_TODAY", False)

    assert "push" in notifications.notify_releasing_today("A Book", "A Series")
    assert push.sent == []


def test_no_subscribed_device_counts_as_done(push, db):
    db.delete_push_subscription("https://push.invalid/phone")

    assert "push" in notifications.notify_releasing_today("A Book", "A Series")
    assert push.sent == []


def test_broken_vapid_key_keeps_the_subscription(push, db, monkeypatch):
    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY", "not-a-key")

    assert "push" not in notifications.notify_releasing_today("A Book", "A Series")
    assert push.sent == []
    assert len(db.get_push_subscriptions()) == 1


def test_only_the_requested_channels_are_sent(push, puts, monkeypatch):
    monkeypatch.setattr(config, "MATRIX_HOMESERVER", "https://matrix.invalid")
    monkeypatch.setattr(config, "MATRIX_ACCESS_TOKEN", "token")
    monkeypatch.setattr(config, "MATRIX_ROOM_ID", "!room:matrix.invalid")
    monkeypatch.setattr(notifications, "_resolved_room_id", None)

    done = notifications.notify_releasing_today("A Book", "A Series", channels={"matrix"})

    assert done == {"matrix"}
    assert len(puts) == 1
    assert push.sent == []


def test_matrix_failure_does_not_fail_push(push, puts, monkeypatch):
    monkeypatch.setattr(config, "MATRIX_HOMESERVER", "https://matrix.invalid")
    monkeypatch.setattr(config, "MATRIX_ACCESS_TOKEN", "token")
    monkeypatch.setattr(config, "MATRIX_ROOM_ID", "!room:matrix.invalid")
    monkeypatch.setattr(notifications, "_resolved_room_id", None)
    puts.responses.append(FakeResponse(403))

    assert notifications.notify_releasing_today("A Book", "A Series") == {"push"}


def test_push_payload_is_encrypted_for_the_device(push, db, monkeypatch):
    """The real WebPusher: only the device's private key can read the message."""
    import base64
    import os

    import http_ece
    import pywebpush
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    def b64(data):
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    device_key = ec.generate_private_key(ec.SECP256R1())
    auth = os.urandom(16)
    p256dh = device_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    db.delete_push_subscription("https://push.invalid/phone")
    db.save_push_subscription("https://push.invalid/real", b64(p256dh), b64(auth), "UA")

    posts = []

    def post(url, data=None, headers=None, timeout=None):
        posts.append({"url": url, "data": data, "headers": headers})
        return FakeResponse(201)

    monkeypatch.setattr(notifications, "WebPusher", pywebpush.WebPusher)
    monkeypatch.setattr(requests, "post", post)

    assert "push" in notifications.notify_new_book("A Book", "A Series")

    assert posts[0]["headers"]["content-encoding"] == "aes128gcm"
    plain = http_ece.decrypt(
        posts[0]["data"], private_key=device_key, auth_secret=auth, version="aes128gcm"
    )
    assert json.loads(plain)["body"] == "New audiobook in A Series: A Book"
