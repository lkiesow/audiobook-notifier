import pytest
import requests

from audiobook_notifier import config, notifications


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


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
    assert notifications.notify_releasing_today("A Book", "A Series") is True
    assert len(puts) == 1
    assert puts[0]["json"]["body"] == "Releasing today in A Series: A Book"


def test_retries_a_server_error_and_reuses_the_transaction_id(matrix, puts):
    puts.responses.extend([FakeResponse(500), FakeResponse(200)])

    assert notifications.notify_releasing_today("A Book", "A Series") is True
    assert len(puts) == 2
    # Matrix deduplicates on the transaction ID in the URL, so a retry after a
    # response we never saw cannot post the message twice.
    assert puts[0]["url"] == puts[1]["url"]


def test_gives_up_after_the_configured_attempts(matrix, puts, monkeypatch):
    monkeypatch.setattr(config, "MATRIX_RETRY_ATTEMPTS", 3)
    puts.responses.extend([FakeResponse(500)] * 3)

    assert notifications.notify_releasing_today("A Book", "A Series") is False
    assert len(puts) == 3


def test_does_not_retry_a_client_error(matrix, puts):
    puts.responses.append(FakeResponse(403))

    assert notifications.notify_releasing_today("A Book", "A Series") is False
    assert len(puts) == 1


def test_retries_a_rate_limit(matrix, puts):
    puts.responses.extend([
        FakeResponse(429, {"retry_after_ms": 50}),
        FakeResponse(200),
    ])

    assert notifications.notify_releasing_today("A Book", "A Series") is True
    assert len(puts) == 2


def test_retries_a_transport_failure(matrix, puts, monkeypatch):
    attempts = []

    def put(url, **kwargs):
        attempts.append(url)
        if len(attempts) == 1:
            raise requests.ConnectionError("boom")
        return FakeResponse(200)

    monkeypatch.setattr(requests, "put", put)
    assert notifications.notify_releasing_today("A Book", "A Series") is True
    assert len(attempts) == 2


def test_room_alias_is_resolved_and_cached(matrix, puts, monkeypatch):
    monkeypatch.setattr(config, "MATRIX_ROOM_ID", "#alias:matrix.invalid")
    gets = []

    def get(url, **kwargs):
        gets.append(url)
        return FakeResponse(200, {"room_id": "!resolved:matrix.invalid"})

    monkeypatch.setattr(requests, "get", get)

    assert notifications.notify_releasing_today("A", "S") is True
    assert notifications.notify_releasing_today("B", "S") is True
    assert len(gets) == 1
    assert "%21resolved" in puts[0]["url"]


def test_unreachable_matrix_is_not_reported_as_delivered(matrix, puts):
    puts.responses.append(FakeResponse(502))
    puts.responses.append(FakeResponse(502))
    puts.responses.append(FakeResponse(502))

    assert notifications.notify_release_postponed("B", "S", "2026-08-05", "2026-08-12") is False


def test_disabled_matrix_counts_as_delivered(monkeypatch):
    monkeypatch.setattr(config, "MATRIX_HOMESERVER", "")
    # Nothing to redeliver when notifications are switched off, so the caller
    # must not keep the book queued forever.
    assert notifications.notify_releasing_today("A Book", "A Series") is True
