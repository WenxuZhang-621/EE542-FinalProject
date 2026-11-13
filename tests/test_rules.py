from datetime import date

import pytest

from dashboard import db
from rules import (
    EXCEPTIONS_SCHEMA_SQL,
    OrderTerms,
    evaluate_exceptions,
    refresh_exceptions,
)
from schema import Attachment, ChangeType, EmailMessage, POExtraction, POStatus

ORDER = OrderTerms(
    po_number="PO-100",
    requested_date="2026-11-27",
    sent_date="2026-11-06",  # Friday
    quantity=100,
    unit_price=2.4,
    currency="USD",
)
MONDAY = date(2026, 11, 9)
TUESDAY = date(2026, 11, 10)


def update(email_id="email-1", **fields):
    defaults = {
        "po_number": ORDER.po_number,
        "supplier": "parts.example.com",
        "status": POStatus.CONFIRMED,
        "change_type": ChangeType.NONE,
        "source_email_id": email_id,
    }
    return POExtraction(**{**defaults, **fields})


def reply(*, subject="Order update", body="", attachments=None):
    return EmailMessage(
        email_id="reply-1",
        from_addr="sales@parts.example.com",
        subject=subject,
        date="2026-11-10",
        body_text=body,
        attachments=attachments or [],
    )


def test_delay_uses_imported_requested_date():
    current = update(original_date="2026-12-11", confirmed_date="2026-12-11")
    (exception,) = evaluate_exceptions([ORDER], [current], as_of=TUESDAY)
    assert exception.kind == "delayed"
    assert "+14 days" in exception.detail
    assert exception.source_email_id == "email-1"
    for ship_date in ("2026-11-27", "2026-11-25", "2026-11-31", None):
        assert not evaluate_exceptions(
            [ORDER], [update(confirmed_date=ship_date)], as_of=TUESDAY
        )


def test_partial_uses_imported_quantity():
    current = update(quantity_ordered=60, quantity_confirmed=60)
    (exception,) = evaluate_exceptions([ORDER], [current], as_of=TUESDAY)
    assert exception.kind == "partial"
    assert exception.detail == "60 of 100 units confirmed"
    assert not evaluate_exceptions(
        [ORDER], [update(quantity_confirmed=100)], as_of=TUESDAY
    )


@pytest.mark.parametrize(
    "current",
    [update(status=POStatus.OUT_OF_STOCK), update(quantity_confirmed=0)],
)
def test_out_of_stock_uses_status_or_zero_quantity(current):
    (exception,) = evaluate_exceptions([ORDER], [current], as_of=TUESDAY)
    assert exception.kind == "out_of_stock"


def test_price_change_uses_imported_unit_price():
    current = update(unit_price=2.65, currency="USD")
    (exception,) = evaluate_exceptions([ORDER], [current], as_of=TUESDAY)
    assert exception.kind == "price_change"
    assert exception.detail == "Unit price 2.4 USD → 2.65 USD"
    assert not evaluate_exceptions([ORDER], [update(unit_price=2.4)], as_of=TUESDAY)
    (exception,) = evaluate_exceptions(
        [ORDER], [update(unit_price=2.4, currency="EUR")], as_of=TUESDAY
    )
    assert exception.detail == "Unit price 2.4 USD → 2.4 EUR"


def test_no_reply_requires_two_weekdays_and_an_exact_po_reference():
    other_order = reply(body="PO-1001 and PO-100-2 are on schedule.")
    assert not evaluate_exceptions([ORDER], [], as_of=MONDAY)
    (exception,) = evaluate_exceptions([ORDER], [], emails=[other_order], as_of=TUESDAY)
    assert exception.kind == "no_reply"
    assert exception.source_email_id is None
    assert "2 business days" in exception.detail
    for email in (
        reply(subject="Re: PO-100"),
        reply(body="已确认PO-100。"),
        reply(attachments=[Attachment("update.csv", "PO-100,confirmed")]),
    ):
        assert not evaluate_exceptions([ORDER], [], emails=[email], as_of=TUESDAY)


def test_latest_reported_field_keeps_its_source():
    delay = update("late-email", confirmed_date="2026-12-11", quantity_confirmed=100)
    price = update("price-email", unit_price=2.65, currency="USD")
    exceptions = evaluate_exceptions([ORDER], [delay, price], as_of=TUESDAY)
    assert {e.kind: e.source_email_id for e in exceptions} == {
        "delayed": "late-email",
        "price_change": "price-email",
    }
    recovery = update("recovery-email", confirmed_date="2026-11-27", unit_price=2.4)
    assert not evaluate_exceptions([ORDER], [delay, price, recovery], as_of=TUESDAY)


def test_repeated_sync_and_resolution(tmp_path):
    conn = db.connect(str(tmp_path / "test.sqlite"))
    conn.executescript(EXCEPTIONS_SCHEMA_SQL)
    conn.executemany(
        "INSERT INTO purchase_orders (po_number, supplier, status) VALUES (?, ?, 'pending')",
        [(ORDER.po_number, "parts"), ("PO-200", "other")],
    )
    other = OrderTerms("PO-200", "2026-11-27", "2026-11-06", 10, 1)
    refresh_exceptions(conn, [ORDER, other], [], as_of=TUESDAY)
    current = update(confirmed_date="2026-12-11", quantity_confirmed=60)
    refresh_exceptions(conn, [ORDER], [current], as_of=TUESDAY)
    first = [
        tuple(row)
        for row in conn.execute("SELECT * FROM exceptions ORDER BY po_number, kind")
    ]
    assert [(row[0], row[1]) for row in first] == [
        ("PO-100", "delayed"),
        ("PO-100", "partial"),
        ("PO-200", "no_reply"),
    ]
    refresh_exceptions(conn, [ORDER], [current], as_of=TUESDAY)
    assert [
        tuple(row)
        for row in conn.execute("SELECT * FROM exceptions ORDER BY po_number, kind")
    ] == first
    recovery = update(
        "recovery-email", confirmed_date="2026-11-27", quantity_confirmed=100
    )
    refresh_exceptions(conn, [ORDER], [current, recovery], as_of=TUESDAY)
    assert [
        tuple(row) for row in conn.execute("SELECT po_number, kind FROM exceptions")
    ] == [("PO-200", "no_reply")]
    conn.close()
