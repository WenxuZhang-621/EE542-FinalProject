"""Generate the shared M2 fixture: 40 orders, 10 suppliers, 10 inbound messages."""

from __future__ import annotations
import argparse
import csv
from datetime import date, timedelta
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from schema import EmailMessage, POExtraction, POStatus, ChangeType

SUPPLIERS = [
    "Alder Components",
    "Birch Fasteners",
    "Cedar Textiles",
    "Dune Packaging",
    "Elm Sensors",
    "Fern Plastics",
    "Grove Cables",
    "Harbor Fixtures",
    "Iris Hardware",
    "Juniper Parts",
]


def generate(out: Path, as_of: date):
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    # Old unanswered orders have >=2 business days; recent ones are not overdue.
    recent = as_of
    while recent.weekday() >= 5:
        recent -= timedelta(days=1)
    for index in range(40):
        supplier = index % 10
        rows.append(
            dict(
                po_number=f"PO-M2-{index + 1:04d}",
                supplier=SUPPLIERS[supplier],
                supplier_email=f"supplier{supplier + 1:02d}@example.com",
                item=f"Test component {index + 1:02d}",
                quantity=(index % 4 + 1) * 100,
                unit_price=round(1.5 + supplier * 0.25, 2),
                currency="USD",
                sent_date=(
                    as_of - timedelta(days=7) if index < 13 else recent
                ).isoformat(),
                requested_ship_date=(as_of + timedelta(days=17)).isoformat(),
            )
        )
    with (out / "po_list_40.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    mail_dir = out / "m2_inbox"
    mail_dir.mkdir(exist_ok=True)
    all_messages, expected = [], []
    for index, row in enumerate(rows[:10]):
        po, quantity = row["po_number"], row["quantity"]
        requested = row["requested_ship_date"]
        status, change = POStatus.CONFIRMED, ChangeType.NONE
        confirmed, supplied, price = requested, quantity, row["unit_price"]
        detail = "We confirm the order as requested."
        kind = None
        if index == 0:
            status, change, kind = POStatus.DELAYED, ChangeType.DATE_CHANGE, "delayed"
            confirmed = (date.fromisoformat(requested) + timedelta(days=14)).isoformat()
            detail = f"The ship date is delayed by two weeks, from {requested} to {confirmed}."
        elif index == 1:
            status, change, kind = (
                POStatus.PARTIAL,
                ChangeType.QUANTITY_CHANGE,
                "partial",
            )
            supplied = quantity // 2
            detail = f"We can only ship {supplied} of the {quantity} units; the rest has no confirmed date."
        elif index == 2:
            status, change, kind = (
                POStatus.PRICE_CHANGE,
                ChangeType.PRICE_CHANGE,
                "price_change",
            )
            price = round(price * 1.1, 2)
            detail = f"The unit price changes from USD {row['unit_price']:.2f} to USD {price:.2f}. Please approve."
        elif index == 3:
            status, change, kind = (
                POStatus.OUT_OF_STOCK,
                ChangeType.QUANTITY_CHANGE,
                "out_of_stock",
            )
            supplied, confirmed = 0, None
            detail = "The item is out of stock. We cannot ship any units and have no new ship date."
        body = (
            f"Hello buyer,\n\nPurchase order: {po}\nSupplier: {row['supplier']}\n"
            f"Item: {row['item']}\nOrdered quantity: {quantity}\nOriginal ship date: {requested}\n"
            f"{detail}\nConfirmed quantity: {supplied}\n"
            f"Confirmed ship date: {confirmed or 'not confirmed'}\nUnit price: USD {price:.2f}\n\n"
            "This is fictional M2 test data.\n"
        )
        msg = EmailMessage(
            email_id=f"m2-sample-{index + 1:02d}",
            thread_id=f"m2-thread-{index + 1:02d}",
            from_addr=row["supplier_email"],
            subject=f"[M2-DEMO] {po} supplier update",
            date=f"{as_of.isoformat()}T12:{index:02d}:00+00:00",
            body_text=body,
        )
        gold = POExtraction(
            po_number=po,
            supplier=row["supplier_email"].split("@")[1],
            status=status,
            change_type=change,
            source_email_id=msg.email_id,
            original_date=requested,
            confirmed_date=confirmed,
            quantity_ordered=quantity,
            quantity_confirmed=supplied,
            unit_price=price,
            currency="USD",
            confidence=1.0,
            notes=detail,
        )
        stem = f"{index + 1:03d}_{status.value}"
        (mail_dir / f"{stem}.email.json").write_text(msg.to_json(), encoding="utf-8")
        (mail_dir / f"{stem}.gold.json").write_text(
            json.dumps([gold.to_dict()], indent=2), encoding="utf-8"
        )
        (mail_dir / f"{stem}.txt").write_text(
            f"Subject: {msg.subject}\n\n{body}", encoding="utf-8"
        )
        all_messages.append(json.loads(msg.to_json()))
        if kind:
            expected.append({"po_number": po, "kind": kind})
    expected.extend(
        {"po_number": row["po_number"], "kind": "no_reply"} for row in rows[10:13]
    )
    (out / "m2_emails.json").write_text(
        json.dumps(all_messages, indent=2), encoding="utf-8"
    )
    (out / "m2_expected.json").write_text(
        json.dumps(
            {
                "as_of": as_of.isoformat(),
                "orders": 40,
                "suppliers": 10,
                "emails": 10,
                "exceptions": expected,
                "silent_orders": [row["po_number"] for row in rows[10:13]],
                "note": "Deterministic fixture expectations, not measured model accuracy.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "tests/samples")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 11, 14))
    args = parser.parse_args()
    generate(args.out, args.as_of)
    print(f"Generated 40 orders and 10 messages for {args.as_of} in {args.out}")
