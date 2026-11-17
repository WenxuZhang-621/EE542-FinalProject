"""api/: the endpoints the front end calls, on a temporary database and a fake extractor."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "tests" / "samples"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "po.sqlite"))
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("GMAIL_TEST_ACCOUNT", "")
    monkeypatch.setenv("GMAIL_TOKEN_PATH", str(tmp_path / "token.json"))
    for p in (ROOT, ROOT / "extract", ROOT / "dashboard", ROOT / "ingest"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import db

    importlib.reload(db)  # pick up DB_PATH
    import run_pipeline as rp
    import api.main as api

    monkeypatch.setattr(rp, "EMAILS_OUT", tmp_path / "emails.json")
    monkeypatch.setattr(rp, "EXTRACTIONS_OUT", tmp_path / "extractions.json")
    gold = {}
    for p in SAMPLES.glob("*.email.json"):
        eid = json.loads(p.read_text(encoding="utf-8"))["email_id"]
        gold[eid] = json.loads(p.with_suffix("").with_suffix(".gold.json").read_text(encoding="utf-8"))
    from schema import POExtraction

    monkeypatch.setattr(
        rp, "extract_timed", lambda m: ([POExtraction.from_dict(g) for g in gold.get(m.email_id, [])], 0.01)
    )
    monkeypatch.setattr(api, "fetch_gmail", lambda since, query=None: (
        _ for _ in ()
    ).throw(RuntimeError("no gmail in tests")))
    with TestClient(api.app) as c:
        c.post("/api/reset")
        yield c


def test_health_and_empty_orders(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["llm_configured"] and h["orders"] == 0
    assert client.get("/api/orders").json()["orders"] == []


def test_po_list_import_then_sync_marks_delay_and_no_reply(client):
    csv = (ROOT / "frontend/public/samples/po_list_sample.csv").read_bytes()
    r = client.post("/api/po-list", files={"file": ("po_list_sample.csv", csv, "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["new"]) == 6 and len(body["errors"]) == 1  # PO-2026-0449 has no email
    assert "supplier_email" in body["errors"][0]["error"]
    # importing again: everything already tracked
    again = client.post("/api/po-list", files={"file": ("po_list_sample.csv", csv, "text/csv")}).json()
    assert len(again["new"]) == 0 and len(again["tracked"]) == 6

    s = client.post("/api/sync", json={"source": "samples"}).json()
    assert s["source"] == "samples" and s["newEmails"] == len(list(SAMPLES.glob("*.email.json")))
    orders = {o["po"]: o for o in client.get("/api/orders").json()["orders"]}
    po = orders["PO-2026-0412"]  # imported with requested 2026-12-01, supplier moved it to 12-15
    assert (
        po["status"] == "delayed"
        and po["currentDate"] == "2026-12-15"
        and po["requestedDate"] == "2026-12-01"
    )
    assert any(e["kind"] == "flag" and "delayed" in e["text"] for e in po["events"])
    assert any(e["kind"] == "sent" for e in po["events"])
    # imported orders nobody answered become no_reply once 2 business days have passed
    assert orders["PO-2026-0445"]["status"] == "no_reply"
    # a second sync has no new email and changes nothing
    s2 = client.post("/api/sync", json={"source": "samples"}).json()
    assert s2["newEmails"] == 0 and s2["changed"] == []


def test_order_detail_and_eval_runs(client):
    client.post("/api/sync", json={"source": "samples"})
    d = client.get("/api/orders/PO-2026-0412").json()
    assert d["order"]["po"] == "PO-2026-0412" and d["extraction"]["status"] == "delayed"
    assert d["supplier"]["id"] == "shenzhen-parts.example.com"
    assert any(e["id"] == "sample-001" for e in d["emails"])
    assert client.get("/api/orders/PO-nope").status_code == 404
    assert isinstance(client.get("/api/eval-runs").json(), list)


def test_sync_without_key_is_a_clear_error(client, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY")
    r = client.post("/api/sync", json={"source": "samples"})
    assert r.status_code == 503 and "LLM_API_KEY" in r.json()["detail"]


def test_gold_sync_works_without_a_key(client, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY")
    r = client.post("/api/sync", json={"source": "gold"}).json()
    assert r["source"] == "gold" and r["newEmails"] > 0 and "reference answers" in r["note"]
    assert client.get("/api/orders/PO-2026-0412").json()["order"]["status"] == "delayed"


def test_po_list_rejects_missing_columns(client):
    r = client.post("/api/po-list", files={"file": ("x.csv", b"po_number,item\nPO-1,thing\n", "text/csv")})
    assert r.status_code == 400 and "supplier_email" in r.json()["detail"]


def test_gmail_request_passes_filters_and_never_substitutes_samples(client, monkeypatch):
    import api.main as api
    import run_pipeline as rp

    messages = rp.load_offline(SAMPLES)[:1]
    calls = []

    def fetch(since, query):
        calls.append((since, query))
        return messages

    monkeypatch.setattr(api, "fetch_gmail", fetch)
    result = client.post("/api/sync", json={
        "source": "gmail", "since": "30d", "query": "subject:M2-DEMO",
    })
    assert result.status_code == 200, result.text
    assert calls == [("30d", "subject:M2-DEMO")]
    assert result.json()["source"] == "gmail"
    assert result.json()["matchedEmails"] == result.json()["newEmails"] == 1
    again = client.post("/api/sync", json={"source": "gmail"}).json()
    assert again["newEmails"] == 0
    assert again["changed"] == []


def test_gmail_errors_are_actionable_and_do_not_use_samples(client, monkeypatch):
    import api.main as api
    from google.auth.exceptions import RefreshError

    def revoked(since, query):
        raise RefreshError("invalid_grant")

    monkeypatch.setattr(api, "fetch_gmail", revoked)
    result = client.post("/api/sync", json={"source": "gmail"})
    assert result.status_code == 401
    assert "--auth-only" in result.json()["detail"]
    assert client.get("/api/orders").json()["orders"] == []
    assert client.post("/api/sync", json={"source": "unexpected"}).status_code == 422
    assert client.post("/api/sync", json={"since": "oops"}).status_code == 422


def test_overlapping_sync_and_reset_are_rejected(client):
    import api.main as api

    with api.SYNC_LOCK:
        assert client.post("/api/sync", json={"source": "gmail"}).status_code == 409
        assert client.post("/api/reset").status_code == 409


def test_partial_sync_preserves_email_and_retry_does_not_duplicate_events(client, monkeypatch):
    import api.main as api
    import run_pipeline as rp
    from extract import ExtractionError

    messages = sorted(rp.load_offline(SAMPLES), key=lambda m: m.date)[:2]
    real_extract = rp.extract_timed
    failed = [False]

    def extract(msg):
        if msg.email_id == messages[1].email_id and not failed[0]:
            failed[0] = True
            raise ExtractionError("unusable answer")
        return real_extract(msg)

    monkeypatch.setattr(rp, "extract_timed", extract)
    monkeypatch.setattr(api, "fetch_gmail", lambda since, query: messages)
    first = client.post("/api/sync", json={"source": "gmail"})
    assert first.status_code == 503
    assert not rp.EMAILS_OUT.exists()
    emails = client.get("/api/orders").json()["emails"]
    assert [m["id"] for m in emails] == [messages[0].email_id]
    retry = client.post("/api/sync", json={"source": "gmail"})
    assert retry.status_code == 200, retry.text
    assert retry.json()["newEmails"] == 1
    with api.conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE source_email_id = ?", (messages[0].email_id,)
        ).fetchone()[0]
    assert count == len(real_extract(messages[0])[0])
    assert len(client.get("/api/orders").json()["emails"]) == 2


def test_backfill_keeps_newer_order_state_and_original_evidence(client, monkeypatch):
    from dataclasses import replace
    import api.main as api
    import run_pipeline as rp
    from schema import POStatus, ChangeType

    message = next(m for m in rp.load_offline(SAMPLES) if m.email_id == "sample-001")
    extraction = rp.extract_timed(message)[0][0]
    newest = replace(message, date="2026-11-15T12:00:00+00:00")
    older = replace(message, email_id="older-confirmation", date="2026-11-10T12:00:00+00:00")
    older_ext = replace(extraction, source_email_id=older.email_id, status=POStatus.CONFIRMED,
                        change_type=ChangeType.NONE, confirmed_date="2026-12-01")
    monkeypatch.setattr(rp, "extract_timed", lambda m: (
        [older_ext if m.email_id == older.email_id else extraction], 0.01,
    ))
    monkeypatch.setattr(api, "fetch_gmail", lambda since, query: [newest])
    assert client.post("/api/sync", json={"source": "gmail"}).status_code == 200
    monkeypatch.setattr(api, "fetch_gmail", lambda since, query: [older, newest])
    result = client.post("/api/sync", json={"source": "gmail", "since": "30d"}).json()
    assert result["newEmails"] == 1 and result["changed"] == []
    detail = client.get(f"/api/orders/{extraction.po_number}").json()
    assert detail["order"]["currentDate"] == extraction.confirmed_date
    assert detail["order"]["lastEmailId"] == newest.email_id
    assert detail["extraction"]["source_email_id"] == newest.email_id
    assert {e["id"] for e in detail["emails"]} == {newest.email_id, older.email_id}


def test_non_order_email_is_saved_and_not_reprocessed(client, monkeypatch):
    import api.main as api
    import run_pipeline as rp

    message = next(m for m in rp.load_offline(SAMPLES) if m.email_id == "sample-019")
    monkeypatch.setattr(api, "fetch_gmail", lambda since, query: [message])
    calls = []

    def extract(msg):
        calls.append(msg.email_id)
        return [], 0.01

    monkeypatch.setattr(rp, "extract_timed", extract)
    assert client.post("/api/sync", json={"source": "gmail"}).json()["newEmails"] == 1
    assert client.post("/api/sync", json={"source": "gmail"}).json()["newEmails"] == 0
    assert calls == [message.email_id]
    state = client.get("/api/orders").json()
    assert state["orders"] == [] and len(state["emails"]) == 1


@pytest.mark.parametrize("answer", [{"orders": {}}, {"orders": ""}, {"orders": None}, {}])
def test_malformed_extraction_is_retryable_instead_of_empty(client, monkeypatch, answer):
    import extract
    import run_pipeline as rp

    monkeypatch.setattr(extract, "_call_llm", lambda msg: answer)
    with pytest.raises(extract.ExtractionError):
        extract.extract_one(rp.load_offline(SAMPLES)[0])
