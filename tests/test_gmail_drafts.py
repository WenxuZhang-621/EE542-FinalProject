"""Approved draft export, with no external Gmail calls."""
import base64
from dataclasses import replace
from email import policy
from email.parser import BytesParser
from unittest.mock import MagicMock

import pytest

from dashboard import db
from ingest.gmail_drafts import DraftSaveError, save_draft
from schema import FollowUpDraft


@pytest.fixture
def workspace(tmp_path):
    c = db.connect(str(tmp_path / "drafts.sqlite"))
    c.executemany("INSERT INTO mailboxes(id,address,token_path) VALUES (?,?,?)", [
        ("default", "default@example.com", "default.json"), ("source", "source@example.com", "source.json")])
    c.execute("INSERT INTO mailbox_settings VALUES ('default','default')")
    c.execute("INSERT INTO mailbox_messages VALUES ('gmail:source:abc','source','abc')")
    c.execute("INSERT INTO purchase_orders(po_number,supplier,supplier_email,status,in_po_list) "
              "VALUES ('PO-1','Supplier','supplier@example.com','delayed',1)")
    draft = FollowUpDraft("d1", "PO-1", "supplier@example.com", "AI subject", "Please confirm the recovery plan.",
                          "Delay", reply_to_email_id="gmail:source:abc", thread_id="untrusted-thread")
    service = MagicMock()
    service.users().getProfile().execute.return_value = {"emailAddress": "source@example.com"}
    service.users().messages().get().execute.return_value = {"threadId": "actual-thread", "payload": {"headers": [
        {"name": "Message-ID", "value": "<original@supplier.example.com>"},
        {"name": "References", "value": "<earlier@example.com>"},
        {"name": "Subject", "value": "PO-1 update"},
    ]}}
    service.users().drafts().create().execute.return_value = {"id": "gmail-draft-1"}
    yield c, draft, service
    c.close()


def test_saved_to_original_mailbox_with_real_reply_headers(workspace, monkeypatch):
    import ingest.gmail_drafts as drafts
    c, draft, service = workspace
    called = []

    def client(**kwargs):
        called.append(kwargs)
        return service

    monkeypatch.setattr(drafts, "gmail_service", client)
    assert save_draft(draft, conn=c) == "gmail-draft-1"
    assert called[0]["token_file"].name == "source.json" and called[0]["interactive"] is False
    service.users().messages().get.assert_called_with(userId="me", id="abc", format="metadata",
                                                     metadataHeaders=["Message-ID", "References", "Subject"])
    body = service.users().drafts().create.call_args.kwargs["body"]
    assert body["message"]["threadId"] == "actual-thread"
    mime = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(body["message"]["raw"]))
    assert mime["From"] == "source@example.com" and mime["To"] == draft.to
    assert mime["Subject"] == "Re: PO-1 update"
    assert mime["In-Reply-To"] == "<original@supplier.example.com>"
    assert mime["References"] == "<earlier@example.com> <original@supplier.example.com>"
    assert mime.get_content().strip() == draft.body
    service.users().drafts().send.assert_not_called()
    service.users().messages().send.assert_not_called()
    service.users().drafts().create().execute.assert_called_once_with(num_retries=0)


@pytest.mark.parametrize("changes", [
    {"reply_to_email_id": None}, {"reply_to_email_id": "unknown"}, {"to": "other@example.com"},
    {"to": "supplier@example.com\r\nBcc: other@example.com"}, {"body": " "}, {"state": "rejected"},
])
def test_invalid_draft_never_contacts_google(workspace, changes):
    c, draft, _ = workspace
    unused = MagicMock()
    with pytest.raises(DraftSaveError):
        save_draft(replace(draft, **changes), conn=c, service=unused)
    unused.users.assert_not_called()


def test_disconnected_source_never_falls_back_to_default(workspace):
    c, draft, _ = workspace
    c.execute("UPDATE mailboxes SET connected=0 WHERE id='source'")
    unused = MagicMock()
    with pytest.raises(DraftSaveError, match="disconnected"):
        save_draft(draft, conn=c, service=unused)
    unused.users.assert_not_called()


def test_wrong_account_and_missing_thread_do_not_create_drafts(workspace):
    c, draft, service = workspace
    service.reset_mock()
    service.users().getProfile().execute.return_value = {"emailAddress": "wrong@example.com"}
    with pytest.raises(RuntimeError, match="does not match"):
        save_draft(draft, conn=c, service=service)
    service.users().drafts.assert_not_called()
    service.users().getProfile().execute.return_value = {"emailAddress": "source@example.com"}
    service.users().messages().get().execute.return_value = {"threadId": "t", "payload": {"headers": []}}
    with pytest.raises(DraftSaveError, match="threading"):
        save_draft(draft, conn=c, service=service)
    service.users().drafts.assert_not_called()


def test_already_saved_draft_is_not_created_again(workspace):
    c, draft, _ = workspace
    service = MagicMock()
    assert save_draft(replace(draft, state="saved", gmail_draft_id="existing"), conn=c, service=service) == "existing"
    service.users.assert_not_called()
