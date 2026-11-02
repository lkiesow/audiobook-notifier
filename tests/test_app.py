import pytest

from audiobook_notifier import app as app_module
from audiobook_notifier import notifications

SUBSCRIPTION = {
    "endpoint": "https://push.invalid/phone",
    "keys": {"p256dh": "p256dh", "auth": "auth"},
}


class SyncThread:
    """Runs the target on start(), so the welcome push is done when we look."""

    def __init__(self, target, args=(), **kwargs):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(app_module, "_auth_enabled", False)
    monkeypatch.setattr(app_module, "_push_enabled", True)
    monkeypatch.setattr(app_module.config, "VAPID_PUBLIC_KEY", "public-key")
    monkeypatch.setattr(app_module.threading, "Thread", SyncThread)
    return app_module.app.test_client()


@pytest.fixture
def welcomed(monkeypatch):
    calls = []
    monkeypatch.setattr(notifications, "send_push_welcome", calls.append)
    return calls


def test_key_is_hidden_when_push_is_off(client, monkeypatch):
    monkeypatch.setattr(app_module, "_push_enabled", False)
    assert client.get("/api/push/key").status_code == 404


def test_key(client):
    assert client.get("/api/push/key").get_json() == {"publicKey": "public-key"}


def test_subscribe_stores_once_and_welcomes_only_new_devices(client, db, welcomed):
    assert client.post("/api/push/subscriptions", json=SUBSCRIPTION).status_code == 201
    # Every page load re-sends the subscription; that must not buzz the phone.
    assert client.post("/api/push/subscriptions", json=SUBSCRIPTION).status_code == 200

    assert len(db.get_push_subscriptions()) == 1
    assert welcomed == [
        {"endpoint": "https://push.invalid/phone", "p256dh": "p256dh", "auth": "auth"}
    ]


@pytest.mark.parametrize("body", [
    {},
    {"endpoint": "http://push.invalid/phone", "keys": {"p256dh": "k", "auth": "a"}},
    {"endpoint": "https://push.invalid/phone", "keys": {"p256dh": "k"}},
])
def test_subscribe_rejects_invalid_subscriptions(client, db, welcomed, body):
    assert client.post("/api/push/subscriptions", json=body).status_code == 400
    assert db.get_push_subscriptions() == []


def test_unsubscribe(client, db, welcomed):
    client.post("/api/push/subscriptions", json=SUBSCRIPTION)

    response = client.delete(
        "/api/push/subscriptions", json={"endpoint": SUBSCRIPTION["endpoint"]}
    )

    assert response.status_code == 204
    assert db.get_push_subscriptions() == []


def test_header_shows_the_bell_only_with_push(client, monkeypatch):
    assert b'id="push-toggle"' in client.get("/").data
    monkeypatch.setattr(app_module, "_push_enabled", False)
    assert b'id="push-toggle"' not in client.get("/").data
