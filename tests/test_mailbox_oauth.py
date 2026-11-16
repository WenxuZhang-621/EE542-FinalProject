"""OAuth callback lifecycle, state verification and reconnect identity checks."""
from urllib.parse import urlencode, urlparse
import time

import httpx
import pytest

from test_mailboxes import workspace, fake_credentials
from ingest.mailbox_oauth import OAuthSessions


class FakeFlow:
    def __init__(self):
        self.redirect_uri = None
        self.credentials = fake_credentials()
        self.exchanges = 0

    def authorization_url(self, **kwargs):
        assert kwargs["access_type"] == "offline"
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "state": "test-state", "redirect_uri": self.redirect_uri,
        }), "test-state"

    def fetch_token(self, **kwargs):
        assert kwargs["code"] == "test-code"
        self.exchanges += 1


@pytest.fixture
def oauth(workspace, monkeypatch):
    api, store, folder = workspace
    import ingest.mailbox_oauth as auth
    flow = FakeFlow()
    monkeypatch.setattr(auth, "make_flow", lambda: flow)
    monkeypatch.setattr(auth, "authorized_address", lambda credentials: "one@example.com")
    manager = OAuthSessions()
    monkeypatch.setattr(api, "oauth_sessions", manager)
    yield manager, flow, store
    for session in manager.sessions.values():
        session.stop.set()


def test_loopback_callback_state_success_and_replay(oauth):
    manager, flow, store = oauth
    started = manager.start(store)
    sid = started["sessionId"]
    assert urlparse(flow.redirect_uri).hostname == "127.0.0.1"
    bad = httpx.get(flow.redirect_uri, params={"state": "wrong", "code": "test-code"})
    assert bad.status_code == 400 and flow.exchanges == 0
    assert manager.status(sid)["status"] == "pending"
    good = httpx.get(flow.redirect_uri, params={"state": "test-state", "code": "test-code"})
    assert good.status_code == 200
    assert manager.status(sid)["status"] == "connected"
    assert len(store.list()["mailboxes"]) == 1
    assert manager.callback(manager.get(sid), {"state": ["test-state"], "code": ["test-code"]})[1] == 410
    assert flow.exchanges == 1


def test_cancel_and_expire_never_add_an_account(oauth):
    manager, _, store = oauth
    sid = manager.start(store)["sessionId"]
    assert manager.cancel(sid)["status"] == "cancelled"
    assert store.list()["mailboxes"] == []
    sid = manager.start(store)["sessionId"]
    manager.get(sid).expires = time.monotonic() - 1
    assert manager.status(sid)["status"] == "expired"
    assert store.list()["mailboxes"] == []


def test_google_denial_and_wrong_reconnect_account(oauth):
    manager, _, store = oauth
    sid = manager.start(store)["sessionId"]
    manager.callback(manager.get(sid), {"state": ["test-state"], "error": ["access_denied"]})
    assert manager.status(sid)["status"] == "cancelled"
    different = store.add("two@example.com", fake_credentials())
    store.disconnect(different)
    sid = manager.start(store, different)["sessionId"]
    manager.callback(manager.get(sid), {"state": ["test-state"], "code": ["test-code"]})
    assert manager.status(sid)["status"] == "error"
    assert len(store.list()["mailboxes"]) == 1
    assert not store.list()["mailboxes"][0]["connected"]


def test_connection_endpoints(oauth, workspace):
    from fastapi.testclient import TestClient
    api, _, _ = workspace
    with TestClient(api.app, base_url="http://localhost:8000") as c:
        result = c.post("/api/mailboxes/connect", json={})
        assert result.status_code == 200
        sid = result.json()["sessionId"]
        assert c.get(f"/api/mailboxes/connections/{sid}").json()["status"] == "pending"
        assert c.post("/api/mailboxes/connect", json={}).status_code == 400
        assert c.post(f"/api/mailboxes/connections/{sid}/cancel").json()["status"] == "cancelled"
        assert c.get("/api/mailboxes/connections/nonexistent").status_code == 404
