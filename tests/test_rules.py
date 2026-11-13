from datetime import date

import pytest

from dashboard import db
from dashboard.ingest_result import save_extractions, upsert
from rules import (
    OrderTerms,
    evaluate_exceptions,
    refresh_exceptions,
    sync_exceptions,
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


def test_delay_without_a_new_date_is_still_flagged():
    vague = update(status=POStatus.DELAYED, change_type=ChangeType.DATE_CHANGE)
    (exception,) = evaluate_exceptions([ORDER], [vague], as_of=TUESDAY)
    assert exception.kind == "delayed"
    assert "not confirmed" in exception.detail
    on_time = update("recovery-email", confirmed_date="2026-11-27")
    assert not evaluate_exceptions([ORDER], [vague, on_time], as_of=TUESDAY)


def test_partial_without_a_quantity_is_still_flagged():
    (exception,) = evaluate_exceptions(
        [ORDER], [update(status=POStatus.PARTIAL)], as_of=TUESDAY
    )
    assert exception.kind == "partial"
    # A full quantity wins over a wrong "partial" label from the model.
    full = update(status=POStatus.PARTIAL, quantity_confirmed=100)
    assert not evaluate_exceptions([ORDER], [full], as_of=TUESDAY)


def test_po_numbers_match_ignoring_case_and_spaces():
    late = update(po_number=" po-100", confirmed_date="2026-12-11")
    (exception,) = evaluate_exceptions([ORDER], [late], as_of=TUESDAY)
    assert (exception.po_number, exception.kind) == ("PO-100", "delayed")
    assert not evaluate_exceptions(
        [ORDER], [], emails=[reply(body="po-100 received")], as_of=TUESDAY
    )


def test_price_ignores_rounding_noise_and_currency_aliases():
    assert not evaluate_exceptions(
        [ORDER], [update(unit_price=2.4000001, currency="usd")], as_of=TUESDAY
    )
    yuan = OrderTerms("PO-100", None, None, 100, 31.5, "CNY")
    assert not evaluate_exceptions(
        [yuan], [update(unit_price=31.5, currency="RMB")], as_of=TUESDAY
    )
    (exception,) = evaluate_exceptions(
        [ORDER], [update(unit_price=2.41, currency="USD")], as_of=TUESDAY
    )
    assert exception.kind == "price_change"


def test_sync_replays_stored_history_and_reset_clears_it(tmp_path):
    conn = db.connect(str(tmp_path / "test.sqlite"))
    conn.execute(
        "INSERT INTO purchase_orders (po_number, supplier, status, quantity_ordered,"
        " unit_price, currency, sent_date, requested_date)"
        " VALUES ('PO-100', 'parts', 'pending', 100, 2.4, 'USD', '2026-11-06', '2026-11-27')"
    )
    email = reply(subject="Re: PO-100")
    late = update(email.email_id, confirmed_date="2026-12-11", unit_price=2.65, currency="USD")
    save_extractions(conn, email, [late])
    upsert(conn, late)
    first = {e.kind for e in sync_exceptions(conn, emails=[email], as_of=TUESDAY)}
    assert first == {"delayed", "price_change"}
    # The imported price stays as the baseline, and a sync with no new email changes nothing.
    assert conn.execute("SELECT unit_price FROM purchase_orders").fetchone()[0] == 2.4
    again = {e.kind for e in sync_exceptions(conn, emails=[email], as_of=TUESDAY)}
    assert again == first
    assert conn.execute("SELECT COUNT(*) FROM exceptions").fetchone()[0] == 2
    # Processing the same email twice does not duplicate its history.
    save_extractions(conn, email, [late])
    assert conn.execute("SELECT COUNT(*) FROM extractions").fetchone()[0] == 1
    db.reset(conn)
    for table in ("purchase_orders", "events", "extractions", "exceptions"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    conn.close()
