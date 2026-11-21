import base64
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from openpyxl import Workbook
from ingest.fetch_emails import attachment_text, fetch, parse_message, since_query


def test_digital_pdf_attachment_is_extracted():
    raw = (Path(__file__).parent / "samples/mime/po_confirmation.pdf").read_bytes()
    parsed = parse_message(
        message(
            {
                "mimeType": "multipart/mixed",
                "parts": [
                    part("text/plain", "See attached confirmation."),
                    part("application/pdf", raw, filename="confirmation.pdf"),
                ],
            }
        ),
        MagicMock(),
    )
    assert parsed.body_text == "See attached confirmation."
    assert "PO-PDF-01" in parsed.attachments[0].text
    assert "Confirmed ship date: 2026-12-15" in parsed.attachments[0].text


def part(kind, text, **extra):
    raw = text.encode() if isinstance(text, str) else text
    return {
        "mimeType": kind,
        "body": {"data": base64.urlsafe_b64encode(raw).decode().rstrip("=")},
        **extra,
    }


def message(payload, id="m1"):
    payload["headers"] = payload.get("headers", []) + [
        {"name": "From", "value": "Test Supplier <supplier@example.com>"},
        {"name": "Subject", "value": "Order update"},
        {"name": "Date", "value": "Fri, 13 Nov 2026 12:00:00 +0000"},
    ]
    return {
        "id": id,
        "threadId": "thread-1",
        "internalDate": "1794571200000",
        "payload": payload,
    }


def test_nested_mime_plain_preferred_and_attachment():
    excel = Workbook()
    excel.active.append(["PO Number", "Quantity"])
    excel.active.append(["PO-10", 500])
    stream = BytesIO()
    excel.save(stream)
    excel.close()
    service = MagicMock()
    service.users().messages().attachments().get().execute.return_value = {
        "data": base64.urlsafe_b64encode(stream.getvalue()).decode()
    }
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    part("text/plain", "Plain supplier reply"),
                    part("text/html", "<p>Duplicate HTML reply</p>"),
                ],
            },
            {
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "filename": "../../orders.xlsx",
                "body": {"attachmentId": "a1"},
            },
        ],
    }
    parsed = parse_message(message(payload), service)
    assert parsed.body_text == "Plain supplier reply"
    assert parsed.email_id == "m1" and parsed.thread_id == "thread-1"
    assert parsed.from_addr == "supplier@example.com"
    assert "PO-10\t500" in parsed.attachments[0].text
    service.users().messages().attachments().get.assert_called_with(
        userId="me", messageId="m1", id="a1"
    )


def test_html_only_and_remote_body():
    service = MagicMock()
    service.users().messages().attachments().get().execute.return_value = {
        "data": base64.urlsafe_b64encode(
            b"<style>hidden</style><p>PO-1 delayed</p>"
        ).decode()
    }
    parsed = parse_message(
        message({"mimeType": "text/html", "body": {"attachmentId": "body1"}}), service
    )
    assert parsed.body_text == "PO-1 delayed"


def test_attachment_failure_keeps_message(caplog):
    parsed = parse_message(
        message(
            {
                "mimeType": "multipart/mixed",
                "parts": [
                    part("text/plain", "Reply"),
                    part("application/pdf", b"not a PDF", filename="broken.pdf"),
                ],
            }
        ),
        None,
    )
    assert parsed.body_text == "Reply" and parsed.attachments[0].text == ""
    assert "Attachment text unavailable" in caplog.text


def test_character_set_and_date_fallback():
    payload = part(
        "text/plain",
        "caf\u00e9".encode("iso-8859-1"),
        headers=[{"name": "Content-Type", "value": "text/plain; charset=iso-8859-1"}],
    )
    msg = message(payload)
    del msg["internalDate"]
    parsed = parse_message(msg, None)
    assert (
        parsed.body_text == "caf\u00e9" and parsed.date == "2026-11-13T12:00:00+00:00"
    )


def test_since_hours_and_validation():
    now = datetime(2026, 11, 14, tzinfo=timezone.utc)
    assert since_query("7d") == "newer_than:7d"
    assert since_query("24h", now=now) == "after:1794528000"
    assert since_query("2026-11-13") == "after:1794528000"
    with pytest.raises(ValueError):
        since_query("0d")


def test_fetch_pages_filters_and_order():
    service = MagicMock()
    service.users().getProfile().execute.return_value = {
        "emailAddress": "test@example.com"
    }
    service.users().messages().list().execute.side_effect = [
        {"messages": [{"id": "m2"}], "nextPageToken": "p2"},
        {"messages": [{"id": "m1"}]},
    ]
    service.users().messages().get().execute.side_effect = [
        message(part("text/plain", "Second"), "m2"),
        message(part("text/plain", "First"), "m1"),
    ]
    messages = fetch("7d", service=service, expected_account="test@example.com",
                     supplier_emails=["supplier@example.com"])
    assert [m.email_id for m in messages] == ["m1", "m2"]
    args = service.users().messages().list.call_args.kwargs
    assert args["pageToken"] == "p2" and "-in:sent -in:drafts" in args["q"]


def test_account_mismatch_reads_no_mail():
    service = MagicMock()
    service.users().getProfile().execute.return_value = {
        "emailAddress": "wrong@example.com"
    }
    with pytest.raises(RuntimeError, match="does not match"):
        fetch("7d", service=service, expected_account="test@example.com",
              supplier_emails=["supplier@example.com"])
    service.users().messages.assert_not_called()


def test_sent_messages_are_not_supplier_replies():
    service = MagicMock()
    service.users().getProfile().execute.return_value = {
        "emailAddress": "test@example.com"
    }
    service.users().messages().list().execute.return_value = {
        "messages": [{"id": "m1"}]
    }
    sent = message(part("text/plain", "My outgoing PO"))
    sent["labelIds"] = ["SENT"]
    service.users().messages().get().execute.return_value = sent
    assert fetch("7d", service=service, expected_account="test@example.com",
                 supplier_emails=["supplier@example.com"]) == []
