"""M3 A acceptance: import order independence, contact filtering, and migration."""
from datetime import date, datetime, timezone
from dataclasses import replace
from io import StringIO
import json
import sqlite3
from unittest.mock import MagicMock

import pytest

from dashboard import db
from dashboard.ingest_result import save_extractions, upsert
from ingest.fetch_emails import fetch, gmail_service, supplier_addresses
from ingest.mailboxes import token_available
from ingest.po_import import import_po_list
from rules import sync_exceptions
from schema import ChangeType, EmailMessage, POExtraction, POStatus
from tests.test_fetch_emails import message, part


CSV = ("po_number,supplier,supplier_email,item,quantity,unit_price,currency,sent_date,requested_ship_date\n"
       "PO-1,Alder,sales@alder.example.com,Chair,100,2.5,USD,2026-11-09,2026-12-01\n")


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(str(tmp_path / "test.sqlite"))
    yield connection
    connection.close()


def supplier_update(conn):
    email = EmailMessage("m1", "sales@alder.example.com", "PO-1 update", "2026-11-20",
                         "PO-1 is delayed and partially available at a higher unit price.")
    update = POExtraction("PO-1", "alder.example.com", POStatus.DELAYED, ChangeType.DATE_CHANGE, "m1",
                          original_date="2026-12-15", confirmed_date="2026-12-15",
                          quantity_ordered=50, quantity_confirmed=50, unit_price=3, currency="USD")
    save_extractions(conn, email, [update])
    upsert(conn, update)
    conn.execute("INSERT INTO email_messages (email_id,data) VALUES (?,?)", (email.email_id, email.to_json()))


def test_import_and_sync_orders_produce_identical_exceptions(tmp_path, monkeypatch):
    import rules

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 21, tzinfo=timezone.utc)

    monkeypatch.setattr(rules, "datetime", FixedClock)
    results = []
    for first in ("import", "sync"):
        c = db.connect(str(tmp_path / f"{first}.sqlite"))
        if first == "import":
            assert import_po_list(StringIO(CSV), conn=c).added == 1
            supplier_update(c)
        else:
            supplier_update(c)
            assert sync_exceptions(c) == []
            preview = import_po_list(StringIO(CSV), conn=c, preview=True)
            assert preview.completed == 1
            assert c.execute("SELECT in_po_list FROM purchase_orders").fetchone()[0] == 0
            result = import_po_list(StringIO(CSV), conn=c)
            assert result.completed == 1 and result.added == 0
            assert len(result.to_api_dict()["completed"]) == 1
        sync_exceptions(c, as_of=date(2026, 11, 21))
        row = c.execute("SELECT * FROM purchase_orders").fetchone()
        assert (row["in_po_list"], row["original_date"], row["unit_price"], row["quantity_ordered"]) == (1, "2026-12-01", 2.5, 100)
        assert (row["confirmed_date"], row["quantity_confirmed"], row["status"]) == ("2026-12-15", 50, "delayed")
        assert import_po_list(StringIO(CSV.replace(",100,2.5,", ",200,99,")), conn=c).existing == 1
        results.append([dict(r) for r in c.execute("SELECT * FROM exceptions ORDER BY kind")])
        c.close()
    assert results[0] == results[1]
    assert {r["kind"] for r in results[0]} == {"delayed", "partial", "price_change"}


def test_migration_distinguishes_old_imports_from_email_created_rows(tmp_path):
    path = tmp_path / "old.sqlite"
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE purchase_orders (po_number TEXT PRIMARY KEY, supplier TEXT NOT NULL, "
              "status TEXT NOT NULL, sent_date TEXT, requested_date TEXT, supplier_email TEXT)")
    c.execute("INSERT INTO purchase_orders VALUES ('PO-1','A','pending','2026-11-01','2026-12-01','a@example.com')")
    c.execute("INSERT INTO purchase_orders VALUES ('PO-2','B','delayed',NULL,NULL,NULL)")
    c.commit()
    c.close()
    for _ in range(2):
        c = db.connect(str(path))
        assert dict(c.execute("SELECT po_number,in_po_list FROM purchase_orders")) == {"PO-1": 1, "PO-2": 0}
        c.close()


def test_only_imported_contacts_are_used_and_empty_list_never_contacts_google(conn):
    supplier_update(conn)
    assert supplier_addresses(conn) == []
    service = MagicMock()
    assert fetch("7d", service=service, supplier_emails=[]) == []
    service.users.assert_not_called()
    import_po_list(StringIO(CSV), conn=conn)
    assert supplier_addresses(conn) == ["sales@alder.example.com"]


def test_supplier_filter_preserves_query_and_rejects_unrelated_message():
    service = MagicMock()
    service.users().getProfile().execute.return_value = {"emailAddress": "buyer@example.com"}
    service.users().messages().list().execute.return_value = {"messages": [{"id": "m1"}, {"id": "m2"}]}
    good = message(part("text/plain", "PO-1 delayed"), "m1")
    unrelated = message(part("text/plain", "Newsletter"), "m2")
    unrelated["payload"]["headers"][0]["value"] = "newsletter@example.com"
    service.users().messages().get().execute.side_effect = [good, unrelated]
    messages = fetch("7d", service=service, expected_account="buyer@example.com",
                     supplier_emails=["SUPPLIER@example.com"], query="subject:PO OR subject:Update")
    assert [m.email_id for m in messages] == ["m1"]
    query = service.users().messages().list.call_args.kwargs["q"]
    assert "(subject:PO OR subject:Update)" in query
    assert query.endswith("from:(supplier@example.com)")


def test_batched_queries_return_latest_messages_without_duplicates(monkeypatch):
    import ingest.fetch_emails as ingest
    monkeypatch.setattr(ingest, "SUPPLIER_BATCH_SIZE", 1)
    service = MagicMock()
    service.users().getProfile().execute.return_value = {"emailAddress": "buyer@example.com"}
    service.users().messages().list().execute.side_effect = [
        {"messages": [{"id": "m1"}]}, {"messages": [{"id": "m1"}, {"id": "m2"}]},
    ]
    older = message(part("text/plain", "Older"), "m1")
    newer = message(part("text/plain", "Newer"), "m2")
    newer["internalDate"] = str(int(older["internalDate"]) + 1000)
    newer["payload"]["headers"][0]["value"] = "supplier2@example.com"
    service.users().messages().get().execute.side_effect = [older, newer]
    emails = fetch("7d", service=service, expected_account="buyer@example.com", max_messages=1,
                   supplier_emails=["supplier@example.com", "supplier2@example.com"])
    assert [m.email_id for m in emails] == ["m2"]


def test_old_readonly_token_requires_reconnect_without_refresh(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"token": "fake", "refresh_token": "fake", "client_id": "fake",
                               "client_secret": "fake", "scopes": ["https://www.googleapis.com/auth/gmail.readonly"]}))
    assert not token_available(str(path))
    with pytest.raises(RuntimeError, match="Reconnect"):
        gmail_service(interactive=False, token_file=path)


def test_history_fixture_rules_and_rag_with_shared_demo_sender(tmp_path, monkeypatch):
    import run_pipeline as rp
    from agent.draft import draft_followup
    from ingest.make_m3_history import build_history
    from rag.embed import HashingEmbedder

    folder = tmp_path / "history"
    build_history(folder, senders={k: "shared@example.com" for k in ("alder", "birch", "cedar")})
    c = db.connect(str(tmp_path / "history.sqlite"))
    monkeypatch.setattr(rp, "EMAILS_OUT", tmp_path / "absent.json")
    import_po_list(folder / "po_list.csv", conn=c)
    for path in sorted(folder.glob("*.email.json")):
        msg = EmailMessage.from_dict(json.loads(path.read_text(encoding="utf-8")))
        gold = path.with_name(path.name.replace(".email.json", ".gold.json"))
        updates = [POExtraction.from_dict(e) for e in json.loads(gold.read_text())]
        save_extractions(c, msg, updates)
        for update in updates:
            upsert(c, update)
        c.execute("INSERT INTO email_messages (email_id,data) VALUES (?,?)", (msg.email_id, msg.to_json()))
    found = sync_exceptions(c, as_of=date(2026, 11, 21))
    expected = json.loads((folder / "manifest.json").read_text())["expected_active_exceptions"]
    assert sorted((e.po_number, e.kind) for e in found) == sorted((e["po_number"], e["kind"]) for e in expected)
    prompts = []

    def model(messages, schema):
        prompts.append(messages[1]["content"])
        return {"subject": "Recovery plan", "body": "Please explain the repeated failure and provide a recovery plan.",
                "why": "Repeated delay.", "rule_ids": ["3", "8"], "email_refs": ["E1"]}

    draft = draft_followup(c, "PO-M3-ALDER-CURRENT", llm=model, embed=HashingEmbedder(), today=date(2026, 11, 21))
    assert draft.to == "shared@example.com" and draft.reply_to_email_id == "m3-alder-05"
    history = prompts[0].split("## This supplier's earlier emails")[1].split("## Playbook rules")[0]
    assert "PO-M3-ALDER-HISTORY" in history
    assert "PO-M3-BIRCH" not in history and "PO-M3-CEDAR" not in history
    c.close()
