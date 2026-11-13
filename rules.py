"""Evaluate imported purchase orders against supplier updates after an inbox sync."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import math
import re
import sqlite3

from schema import EmailMessage, POException, POExtraction, POStatus


@dataclass(frozen=True)
class OrderTerms:
    """The original terms from the order import."""

    po_number: str
    requested_date: str | None
    sent_date: str | None
    quantity: float | None
    unit_price: float | None
    currency: str | None = None


RULE_KINDS = ("delayed", "partial", "out_of_stock", "price_change", "no_reply")

# Suppliers and models write the same currency in different ways.
_CURRENCY_ALIASES = {"RMB": "CNY", "CNH": "CNY", "US$": "USD"}

_UPSERT_EXCEPTION = """
INSERT INTO exceptions (po_number, kind, detail, detected_at, source_email_id)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT (po_number, kind) DO UPDATE SET
    detail = excluded.detail,
    source_email_id = excluded.source_email_id
WHERE exceptions.detail <> excluded.detail
   OR exceptions.source_email_id IS NOT excluded.source_email_id
"""


def _iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _po_key(po_number: str) -> str:
    """Match PO numbers regardless of case and stray spaces ("po-100 " is PO-100)."""
    return re.sub(r"\s+", "", po_number).upper()


def _currency(value: str | None) -> str:
    code = (value or "").strip().upper()
    return _CURRENCY_ALIASES.get(code, code)


def _business_days_between(start: date, end: date) -> int:
    """Count weekdays after start, through end, as in the PO import preview."""
    weeks, days = divmod(max((end - start).days, 0), 7)
    return weeks * 5 + sum(
        (start.weekday() + offset) % 7 < 5 for offset in range(1, days + 1)
    )


def _reply_mentions(
    orders: list[OrderTerms], emails: Iterable[EmailMessage]
) -> set[str]:
    if not orders:
        return set()
    numbers = "|".join(re.escape(order.po_number) for order in orders)
    # A reference to PO-1001 is not a reply to PO-100.
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_-])(?:{numbers})(?![A-Za-z0-9_-])", re.IGNORECASE
    )
    mentioned = set()
    for email in emails:
        texts = [
            email.subject,
            email.body_text,
            *(part.text for part in email.attachments),
        ]
        for text in texts:
            mentioned.update(_po_key(found) for found in pattern.findall(text))
    return mentioned


def evaluate_exceptions(
    orders: Iterable[OrderTerms],
    extractions: Iterable[POExtraction],
    *,
    emails: Iterable[EmailMessage] = (),
    as_of: date | None = None,
) -> list[POException]:
    """Return active exceptions for imported orders.

    Supply known extractions oldest first, along with known inbound emails if available.
    New emails that omit a field leave the last stated value for that field in effect.
    """
    orders = list(orders)
    updates_by_po = defaultdict(list)
    for update in extractions:
        if update.po_number:
            updates_by_po[_po_key(update.po_number)].append(update)
    mentioned = _reply_mentions(orders, emails)
    today = as_of or date.today()
    detected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    found = []

    for order in orders:
        po = order.po_number
        updates = updates_by_po.get(_po_key(po), ())
        required = _iso_date(order.requested_date)
        for update in reversed(updates):
            confirmed = _iso_date(update.confirmed_date)
            if confirmed is None and update.status != POStatus.DELAYED:
                continue
            if confirmed is None:
                # "Pushed to mid-December, exact day not set yet" is still a delay.
                detail = "Supplier reported a delay; new ship date not confirmed"
            elif required is not None and confirmed > required:
                detail = f"{required} → {confirmed} (+{(confirmed - required).days} days)"
            else:
                break
            found.append(
                POException(po, "delayed", detail, detected_at, update.source_email_id)
            )
            break

        quantity_update = next(
            (
                e
                for e in reversed(updates)
                if e.quantity_confirmed is not None
                or e.status in (POStatus.OUT_OF_STOCK, POStatus.PARTIAL)
            ),
            None,
        )
        if quantity_update is not None:
            qty = quantity_update.quantity_confirmed
            if quantity_update.status == POStatus.OUT_OF_STOCK or qty == 0:
                found.append(
                    POException(
                        po,
                        "out_of_stock",
                        "Supplier cannot ship any units",
                        detected_at,
                        quantity_update.source_email_id,
                    )
                )
            elif (
                qty is not None
                and order.quantity is not None
                and 0 < qty < order.quantity
            ):
                found.append(
                    POException(
                        po,
                        "partial",
                        f"{qty:g} of {order.quantity:g} units confirmed",
                        detected_at,
                        quantity_update.source_email_id,
                    )
                )
            elif qty is None and quantity_update.status == POStatus.PARTIAL:
                found.append(
                    POException(
                        po,
                        "partial",
                        "Supplier can ship only part of the order; quantity not confirmed",
                        detected_at,
                        quantity_update.source_email_id,
                    )
                )

        price_update = next(
            (e for e in reversed(updates) if e.unit_price is not None), None
        )
        if order.unit_price is not None and price_update is not None:
            old_currency = _currency(order.currency or price_update.currency)
            new_currency = _currency(price_update.currency or order.currency)
            same_price = math.isclose(
                order.unit_price, price_update.unit_price, rel_tol=1e-6, abs_tol=1e-9
            )
            if not same_price or old_currency != new_currency:
                old_price = f"{order.unit_price:g} {old_currency}".rstrip()
                new_price = f"{price_update.unit_price:g} {new_currency}".rstrip()
                found.append(
                    POException(
                        po,
                        "price_change",
                        f"Unit price {old_price} → {new_price}",
                        detected_at,
                        price_update.source_email_id,
                    )
                )

        sent = _iso_date(order.sent_date)
        if not updates and _po_key(po) not in mentioned and sent is not None:
            elapsed = _business_days_between(sent, today)
            if elapsed >= 2:
                found.append(
                    POException(
                        po,
                        "no_reply",
                        f"No supplier reply after {elapsed} business days",
                        detected_at,
                    )
                )

    return found


def refresh_exceptions(
    conn: sqlite3.Connection,
    orders: Iterable[OrderTerms],
    extractions: Iterable[POExtraction],
    *,
    emails: Iterable[EmailMessage] = (),
    as_of: date | None = None,
) -> list[POException]:
    """Reconcile exceptions for the supplied orders in the caller's transaction.

    Pass every known extraction for these orders, not just the ones from the latest
    sync: an exception that the supplied history no longer supports is removed.
    """
    orders = list(orders)
    found = evaluate_exceptions(orders, extractions, emails=emails, as_of=as_of)
    conn.executemany(
        _UPSERT_EXCEPTION,
        [
            (e.po_number, e.kind, e.detail, e.detected_at, e.source_email_id)
            for e in found
        ],
    )
    active = {(e.po_number, e.kind) for e in found}
    conn.executemany(
        "DELETE FROM exceptions WHERE po_number = ? AND kind = ?",
        [
            (order.po_number, kind)
            for order in orders
            for kind in RULE_KINDS
            if (order.po_number, kind) not in active
        ],
    )
    return found


def sync_exceptions(
    conn: sqlite3.Connection,
    *,
    emails: Iterable[EmailMessage] = (),
    as_of: date | None = None,
) -> list[POException]:
    """Recompute exceptions for every stored order. Call this after each inbox sync.

    Order terms come from `purchase_orders` and supplier updates from the full history
    in `extractions`, so a sync with no new email keeps the exceptions found earlier.
    The caller commits.
    """
    orders = [
        OrderTerms(
            po_number=row["po_number"],
            requested_date=row["requested_date"],
            sent_date=row["sent_date"],
            quantity=row["quantity_ordered"],
            unit_price=row["unit_price"],
            currency=row["currency"],
        )
        for row in conn.execute("SELECT * FROM purchase_orders")
    ]
    history = [
        POExtraction.from_dict(json.loads(row["data"]))
        for row in conn.execute("SELECT data FROM extractions ORDER BY email_date, id")
    ]
    return refresh_exceptions(conn, orders, history, emails=emails, as_of=as_of)
