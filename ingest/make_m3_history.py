"""Build reproducible fictional supplier histories; this command never sends mail."""
from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from email.message import EmailMessage as MimeMessage
from email.policy import SMTP
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from schema import ChangeType, EmailMessage, POExtraction, POStatus

SUPPLIERS = {
    "alder": ("Alder Components", "sales@alder.example.com", "Chair frame", 100, 20.0),
    "birch": ("Birch Fasteners", "orders@birch.example.com", "Fastener set", 500, 2.0),
    "cedar": ("Cedar Textiles", "sales@cedar.example.com", "Upholstery roll", 200, 8.0),
}


def build_history(out: Path, *, as_of=date(2026, 11, 21), senders=None, recipient=None):
    """Write 15 emails, their extraction answers, six orders and a manifest.

    Sender overrides must be real accounts controlled by the demo team. Use an
    output directory outside tests/samples when substituting personal addresses.
    Optional .eml files are for manual sending from those same accounts.
    """
    out.mkdir(parents=True, exist_ok=True)
    senders = senders or {}
    rows, ids = [], []
    for key, (supplier, address, item, qty, price) in SUPPLIERS.items():
        address = senders.get(key, address)
        if recipient and address.casefold() == recipient.casefold():
            raise ValueError("Use different sending and receiving accounts: SENT messages are excluded from sync.")
        for historic in (True, False):
            po = f"PO-M3-{key.upper()}-{'HISTORY' if historic else 'CURRENT'}"
            sent = as_of - timedelta(days=42 if historic else 12)
            requested = as_of + timedelta(days=-21 if historic else 10)
            rows.append(dict(po_number=po, supplier=supplier, supplier_email=address, item=item,
                             quantity=qty, unit_price=price, currency="USD", sent_date=sent.isoformat(),
                             requested_ship_date=requested.isoformat()))
        old_po, po = rows[-2]["po_number"], rows[-1]["po_number"]
        old_date, wanted = rows[-2]["requested_ship_date"], rows[-1]["requested_ship_date"]
        late = (date.fromisoformat(wanted) + timedelta(days=14)).isoformat()
        old_late = (date.fromisoformat(old_date) + timedelta(days=5)).isoformat()
        base = dict(status="confirmed", change_type="none", confirmed_date=wanted, quantity_confirmed=qty)
        if key == "alder":
            specs = [
                (old_po, -35, f"The shipment for {old_po} is delayed from {old_date} to {old_late} due to a machine failure. We will arrange a backup production line.",
                 dict(status="delayed", change_type="date_change", confirmed_date=old_late)),
                (old_po, -28, f"The backup line is ready for {old_po}. We have recovered the schedule and confirm all {qty} units will ship on {old_date}. We will notify you earlier of future production risks.",
                 dict(status="confirmed", change_type="date_change", confirmed_date=old_date, quantity_confirmed=qty)),
                (po, -10, f"We confirm {po}: {qty} units at USD {price:.2f} each, shipping on {wanted}.", base),
                (po, -3, f"For {po}, another machine failure means shipment must move from {wanted} to {late}. All {qty} units are affected. We are checking the backup line.",
                 dict(status="delayed", change_type="date_change", confirmed_date=late, quantity_confirmed=qty)),
                (po, -1, f"For {po}, the backup line is unavailable this time. Our confirmed ship date remains {late}. We cannot offer an earlier partial shipment. Please let us know what recovery details you need.",
                 dict(status="delayed", change_type="none", confirmed_date=late)),
            ]
        elif key == "birch":
            specs = [
                (old_po, -35, f"For {old_po}, we propose raising the unit price from USD {price:.2f} to USD 2.20 because of steel costs. Your approval is required; this is not an agreed change.",
                 dict(status="price_change", change_type="price_change", unit_price=2.2)),
                (old_po, -28, f"For {old_po}, we withdraw the increase after reviewing the confirmed quotation. We will honor USD {price:.2f} per unit for all {qty} units and ship on {old_date}.",
                 dict(status="confirmed", change_type="price_change", unit_price=price, confirmed_date=old_date, quantity_confirmed=qty)),
                (po, -10, f"We confirm {po}: {qty} units at USD {price:.2f} per unit, shipping on {wanted}. The price is fixed for this order.", {**base, "unit_price": price}),
                (po, -3, f"For {po}, we request a unit price increase from USD {price:.2f} to USD 3.00 because of material costs. The ship date remains {wanted}. Please approve the revised price before we proceed.",
                 dict(status="price_change", change_type="price_change", unit_price=3.0, confirmed_date=wanted)),
                (po, -1, f"For {po}, we can reduce our proposed price from USD 3.00 to USD 2.60 per unit. This is still above the confirmed USD {price:.2f} baseline and remains subject to your approval. Shipment is still planned for {wanted}.",
                 dict(status="price_change", change_type="price_change", unit_price=2.6, confirmed_date=wanted)),
            ]
        else:
            specs = [
                (old_po, -35, f"For {old_po}, we can initially supply only 100 of the {qty} rolls. The balance is awaiting incoming material. Can you accept a split shipment?",
                 dict(status="partial", change_type="quantity_change", quantity_confirmed=100)),
                (old_po, -28, f"Incoming material for {old_po} has arrived. All {qty} rolls are now available and confirmed for {old_date}. We will confirm available stock before accepting another order.",
                 dict(status="confirmed", change_type="quantity_change", quantity_confirmed=qty, confirmed_date=old_date)),
                (po, -10, f"We confirm {po} for {qty} rolls at USD {price:.2f} each, to ship on {wanted}.", base),
                (po, -3, f"For {po}, our inventory check found only 80 of {qty} rolls available for {wanted}. The balance has no confirmed date. We previously promised to check stock before confirmation and are investigating the discrepancy.",
                 dict(status="partial", change_type="quantity_change", quantity_confirmed=80, confirmed_date=wanted)),
                (po, -1, f"For {po}, the remaining 80 rolls failed inspection. The item is now out of stock: we can supply zero rolls. A substitute needs your approval; we have not allocated or shipped one.",
                 dict(status="out_of_stock", change_type="quantity_change", quantity_confirmed=0)),
            ]
        for n, (number, offset, body, values) in enumerate(specs, 1):
            eid = f"m3-{key}-{n:02d}"
            happened = (as_of + timedelta(days=offset)).isoformat()
            text = f"FICTIONAL CLASSROOM TEST - no real purchase or shipment.\nHistorical update dated {happened}.\n\nHello buyer,\n\n{body}\n\nBest,\n{supplier}"
            msg = EmailMessage(eid, address, f"[M3-DEMO] {number} supplier update", happened + "T09:00:00+00:00",
                               text, thread_id=f"m3-thread-{number}")
            fields = dict(status="confirmed", change_type="none", currency="USD", confidence=1.0)
            fields.update(values)
            fields["status"] = POStatus(fields["status"])
            fields["change_type"] = ChangeType(fields["change_type"])
            extraction = POExtraction(number, supplier, source_email_id=eid, **fields)
            (out / f"{eid}.email.json").write_text(msg.to_json() + "\n", encoding="utf-8")
            (out / f"{eid}.gold.json").write_text(json.dumps([extraction.to_dict()], indent=2) + "\n", encoding="utf-8")
            ids.append(eid)
            if recipient:
                mime = MimeMessage(policy=SMTP)
                mime["From"], mime["To"], mime["Subject"] = address, recipient, msg.subject
                mime.set_content(text)
                (out / f"{eid}.eml").write_bytes(mime.as_bytes())
    with (out / "po_list.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out / "manifest.json").write_text(json.dumps({
        "fictional": True, "as_of": as_of.isoformat(), "suppliers": 3, "orders": len(rows),
        "emails": ids, "expected_active_exceptions": [
            {"po_number": "PO-M3-ALDER-CURRENT", "kind": "delayed"},
            {"po_number": "PO-M3-BIRCH-CURRENT", "kind": "price_change"},
            {"po_number": "PO-M3-CEDAR-CURRENT", "kind": "out_of_stock"},
        ],
        "note": "Gold answers verify ingestion and rules, not LLM accuracy. Real Gmail IDs/timestamps are assigned on delivery; historical dates remain explicit in the body.",
    }, indent=2) + "\n", encoding="utf-8")
    return {"orders": len(rows), "emails": len(ids), "output": str(out)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "tests/samples/m3_history")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 11, 21))
    parser.add_argument("--sender", action="append", default=[], help="e.g. alder=controlled-test-account@gmail.com")
    parser.add_argument("--recipient", help="Optional receiving test mailbox for .eml export")
    args = parser.parse_args()
    senders = dict(value.split("=", 1) for value in args.sender)
    if set(senders) - set(SUPPLIERS):
        parser.error("Sender names must be alder, birch, or cedar")
    if (senders or args.recipient) and args.out.resolve().is_relative_to((ROOT / "tests").resolve()):
        parser.error("Export personal mailbox addresses outside tests/; do not commit them")
    print(json.dumps(build_history(args.out, as_of=args.as_of, senders=senders, recipient=args.recipient)))


if __name__ == "__main__":
    main()
