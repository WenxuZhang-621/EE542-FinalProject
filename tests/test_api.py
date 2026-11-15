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
    api.fetch_gmail = lambda since: (_ for _ in ()).throw(NotImplementedError("no gmail in tests"))
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
