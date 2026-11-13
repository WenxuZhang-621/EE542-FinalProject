"""Upsert POExtraction JSON into SQLite and record change events.

Usage:
    python dashboard/ingest_result.py --in data/extractions.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema import ChangeType, EmailMessage, POExtraction  # noqa: E402
from db import connect  # noqa: E402

COLUMNS = ["status", "original_date", "confirmed_date", "quantity_ordered",
           "quantity_confirmed", "unit_price", "currency"]


def _fmt(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return None if v is None else str(v)


def _event_values(ext: POExtraction, prev) -> tuple:
    """Old and new value for the history row, based on what this email changed."""
    if ext.change_type == ChangeType.DATE_CHANGE:
        old = (prev and (prev["confirmed_date"] or prev["original_date"])) or ext.original_date
        return old, ext.confirmed_date
    if ext.change_type == ChangeType.QUANTITY_CHANGE:
        old = (prev and prev["quantity_confirmed"]) or ext.quantity_ordered
        return old, ext.quantity_confirmed
    if ext.change_type == ChangeType.PRICE_CHANGE:
        return (prev and prev["unit_price"]), ext.unit_price
    return (prev and prev["status"]), ext.status.value


def upsert(conn, ext: POExtraction) -> None:
    """Insert or update one PO and record what this email changed in `events`."""
    prev = conn.execute("SELECT * FROM purchase_orders WHERE po_number = ?",
                        (ext.po_number,)).fetchone()
    new = {c: getattr(ext, c) for c in COLUMNS}
    new["status"] = ext.status.value
    if prev is None:
        conn.execute(
            "INSERT INTO purchase_orders (po_number, supplier, last_email_id, "
            + ", ".join(COLUMNS) + ") VALUES (?, ?, ?" + ", ?" * len(COLUMNS) + ")",
            (ext.po_number, ext.supplier, ext.source_email_id, *new.values()),
        )
    else:
        # A later email only updates what it states; the first known order date and
        # ordered quantity stay, so the dashboard can show "was -> now".
        merged = {c: (new[c] if new[c] is not None else prev[c]) for c in COLUMNS}
        merged["original_date"] = prev["original_date"] or new["original_date"]
        merged["quantity_ordered"] = prev["quantity_ordered"] or new["quantity_ordered"]
        if prev["sent_date"] and prev["unit_price"] is not None:
            # Imported from the PO list: keep the ordered price as the baseline that
            # rules.py compares against. The supplier's new price is in events/exceptions.
            merged["unit_price"], merged["currency"] = prev["unit_price"], prev["currency"]
        conn.execute(
            "UPDATE purchase_orders SET " + ", ".join(f"{c} = ?" for c in COLUMNS)
            + ", last_email_id = ?, updated_at = CURRENT_TIMESTAMP WHERE po_number = ?",
            (*merged.values(), ext.source_email_id, ext.po_number),
        )
    old, val = _event_values(ext, prev)
    conn.execute(
        "INSERT INTO events (po_number, change_type, old_value, new_value, source_email_id, notes)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (ext.po_number, ext.change_type.value, _fmt(old), _fmt(val), ext.source_email_id,
         ext.notes),
    )


def save_extractions(conn, msg: EmailMessage, exts: list[POExtraction]) -> None:
    """Keep every extraction from one email. Processing the same email again replaces it."""
    conn.execute("DELETE FROM extractions WHERE source_email_id = ?", (msg.email_id,))
    conn.executemany(
        "INSERT INTO extractions (source_email_id, email_date, po_number, data)"
        " VALUES (?, ?, ?, ?)",
        [(msg.email_id, msg.date, e.po_number, json.dumps(e.to_dict(), ensure_ascii=False))
         for e in exts],
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/extractions.json")
    args = ap.parse_args()

    with open(args.inp, encoding="utf-8") as f:
        exts = [POExtraction.from_dict(d) for d in json.load(f)]

    conn = connect()
    for e in exts:
        if e.po_number:
            upsert(conn, e)
    conn.commit()
    print(f"ingested {len(exts)} extractions")


if __name__ == "__main__":
    main()
