"""Multiple mailboxes: independent credentials, source IDs, defaults and disconnects."""
from contextlib import closing
import importlib
import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT / "dashboard", ROOT / "extract", ROOT / "ingest"):
    sys.path.insert(0, str(folder))

from ingest.fetch_emails import SCOPES
from ingest.mailboxes import MailboxStore
from schema import EmailMessage, POExtraction, POStatus, ChangeType


def fake_credentials():
    return Credentials(token="test-access-token", refresh_token="test-refresh-token",
                       token_uri="https://oauth2.googleapis.com/token", client_id="test-client",
                       client_secret="test-secret", scopes=SCOPES)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "po.sqlite"))
    monkeypatch.setenv("GMAIL_TEST_ACCOUNT", "")
    monkeypatch.setenv("GMAIL_TOKEN_PATH", str(tmp_path / "legacy.json"))
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    import db
    importlib.reload(db)
    import api.main as api
    import run_pipeline as rp
    monkeypatch.setattr(rp, "EMAILS_OUT", tmp_path / "emails.json")
    monkeypatch.setattr(rp, "EXTRACTIONS_OUT", tmp_path / "extractions.json")
    return api, api.mailbox_store(), tmp_path


def test_two_accounts_with_same_gmail_id_sync_independently(workspace, monkeypatch):
    api, store, _ = workspace
    import ingest.fetch_emails as ingest
    import run_pipeline as rp
    first = store.add("one@example.com", fake_credentials())
    second = store.add("two@example.com", fake_credentials())
    calls = []

    def fetch(since, *, service, query, expected_account, supplier_emails):
        assert supplier_emails == ["supplier@example.com"]
        calls.append(expected_account)
        mid = first if expected_account == "one@example.com" else second
        assert service["token_file"].name == f"{mid}.json"
        po = "PO-ONE" if mid == first else "PO-TWO"
        return [EmailMessage("abc123", "supplier@example.com", po, "2026-11-15", po)]

    monkeypatch.setattr(ingest, "gmail_service", lambda **kwargs: kwargs)
    monkeypatch.setattr(ingest, "fetch", fetch)
    monkeypatch.setattr(rp, "extract_timed", lambda m: ([POExtraction(
        po_number=m.body_text, supplier="example.com", status=POStatus.CONFIRMED,
        change_type=ChangeType.NONE, source_email_id=m.email_id,
    )], 0.01))
    with TestClient(api.app, base_url="http://localhost:8000") as c:
        with api.conn() as connection:
            connection.executemany("INSERT INTO purchase_orders "
                                   "(po_number,supplier,supplier_email,status,in_po_list) "
                                   "VALUES (?,'Supplier','supplier@example.com','pending',1)",
                                   [("PO-ONE",), ("PO-TWO",)])
        for mid in (first, second):
            result = c.post("/api/sync", json={"source": "gmail", "mailboxId": mid})
            assert result.status_code == 200, result.text
            assert result.json()["newEmails"] == 1
        state = c.get("/api/orders").json()
        assert len(state["orders"]) == len(state["emails"]) == 2
        assert len({m["id"] for m in state["emails"]}) == 2
        assert {m["mailbox"] for m in state["emails"]} == {"one@example.com", "two@example.com"}
        for mid in (first, second):
            assert c.post("/api/sync", json={"source": "gmail", "mailboxId": mid}).json()["newEmails"] == 0
        assert c.post(f"/api/mailboxes/{second}/default").json()["defaultMailboxId"] == second
        assert c.get("/api/gmail/status").json()["account"] == "two@example.com"
        assert c.post("/api/sync", json={"source": "gmail"}).json()["mailboxId"] == second
        before = len(calls)
        assert c.post(f"/api/mailboxes/{second}/disconnect").status_code == 200
        assert c.post("/api/sync", json={"source": "gmail", "mailboxId": second}).status_code == 503
        assert len(calls) == before
        assert len(c.get("/api/orders").json()["orders"]) == 2
        detail = c.get("/api/orders/PO-TWO").json()
        assert detail["emails"][0]["mailbox"] == "two@example.com"
        listing = c.get("/api/mailboxes").json()
        assert listing["defaultMailboxId"] == first
        assert "test-secret" not in json.dumps(listing)
        assert "token_path" not in json.dumps(listing)
        assert listing["mailboxes"][0]["lastSyncAt"] is not None


def test_management_rejects_cross_origin_and_disconnect_during_sync(workspace):
    api, store, _ = workspace
    mid = store.add("one@example.com", fake_credentials())
    with TestClient(api.app, base_url="http://localhost:8000") as c:
        assert c.post(f"/api/mailboxes/{mid}/disconnect", headers={"Origin": "https://example.net"}).status_code == 403
        assert store.get(mid)["connected"]
        with api.SYNC_LOCK:
            assert c.post(f"/api/mailboxes/{mid}/disconnect").status_code == 409
        assert c.post("/api/mailboxes/nonexistent/default").status_code == 404


def test_legacy_import_preserves_ids_and_does_not_reconnect_after_disconnect(workspace, monkeypatch):
    _, store, folder = workspace
    token = folder / "legacy.json"
    token.write_text(fake_credentials().to_json(), encoding="utf-8")
    monkeypatch.setenv("GMAIL_TEST_ACCOUNT", "legacy@example.com")
    message = EmailMessage("abc123", "supplier@example.com", "PO-1", "2026-11-15", "PO-1")
    store.emails_path.write_text(json.dumps([json.loads(message.to_json())]), encoding="utf-8")
    listing = store.list()
    mid = listing["defaultMailboxId"]
    assert store.namespace(mid, [message])[0].email_id == "abc123"
    store.disconnect(mid)
    assert store.list()["defaultMailboxId"] is None
    assert not store.list()["mailboxes"][0]["connected"]
    assert token.exists()
    assert store.add("legacy@example.com", fake_credentials()) == mid
    assert len(store.list()["mailboxes"]) == 1
    assert store.namespace(mid, [message])[0].email_id == "abc123"


def test_reset_clears_orders_but_keeps_connections(workspace):
    api, store, _ = workspace
    mid = store.add("one@example.com", fake_credentials())
    with TestClient(api.app, base_url="http://localhost:8000") as c:
        assert c.post("/api/reset").status_code == 200
    assert store.get(mid)["connected"]


def test_missing_authorization_file_requires_reconnect(workspace, monkeypatch):
    api, store, _ = workspace
    import ingest.fetch_emails as ingest
    mid = store.add("one@example.com", fake_credentials())
    Path(store.get(mid)["token_path"]).unlink()

    def unexpected(**kwargs):
        raise AssertionError("A missing authorization must not contact Gmail")

    monkeypatch.setattr(ingest, "gmail_service", unexpected)
    with TestClient(api.app, base_url="http://localhost:8000") as c:
        with api.conn() as connection:
            connection.execute("INSERT INTO purchase_orders "
                               "(po_number,supplier,supplier_email,status,in_po_list) "
                               "VALUES ('PO-1','Supplier','supplier@example.com','pending',1)")
        result = c.post("/api/sync", json={"source": "gmail", "mailboxId": mid})
        assert result.status_code == 503
        assert "Settings > Mailboxes" in result.json()["detail"]
        assert not c.get("/api/mailboxes").json()["mailboxes"][0]["authorized"]
