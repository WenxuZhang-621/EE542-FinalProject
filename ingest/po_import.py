"""Validate CSV/XLSX purchase orders and insert new rows without overwriting orders."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from io import BytesIO, StringIO
import json
import math
import os
from pathlib import Path
import re
import sys
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dashboard.db import connect
from schema import PurchaseOrder

REQUIRED_COLUMNS = (
    "po_number",
    "supplier_email",
    "item",
    "quantity",
    "unit_price",
    "currency",
    "sent_date",
    "requested_ship_date",
)
# Same spellings as frontend/src/modules/po/import.ts, plus the backend date name.
ALIASES = {
    "po": "po_number",
    "po number": "po_number",
    "po no": "po_number",
    "po #": "po_number",
    "vendor": "supplier",
    "supplier name": "supplier",
    "vendor email": "supplier_email",
    "email": "supplier_email",
    "description": "item",
    "qty": "quantity",
    "price": "unit_price",
    "unit price": "unit_price",
    "po date": "sent_date",
    "order date": "sent_date",
    "ship date": "requested_ship_date",
    "requested date": "requested_ship_date",
    "need by": "requested_ship_date",
}


@dataclass
class ImportResult:
    rows: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    file_errors: list[str] = field(default_factory=list)
    preview: bool = False

    @property
    def added(self):
        return sum(row["kind"] == "new" for row in self.rows)

    @property
    def existing(self):
        return sum(row["kind"] == "tracked" for row in self.rows)

    @property
    def errors(self):
        return sum(row["kind"] == "error" for row in self.rows) + len(self.file_errors)

    def to_dict(self):
        return {
            **asdict(self),
            "added": self.added,
            "existing": self.existing,
            "errors": self.errors,
        }


def _string(value):
    return "" if value is None else str(value).strip()


def _date(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _string(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return date.fromisoformat(text).isoformat()
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", text):
        month, day, year = map(int, text.split("/"))
        return date(year, month, day).isoformat()
    raise ValueError("must be YYYY-MM-DD or M/D/YYYY")


def _number(value, *, positive):
    text = _string(value)
    if not text:
        raise ValueError("must be a number")
    if "," in text and not re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?", text):
        raise ValueError("has invalid thousands separators")
    number = float(text.replace(",", ""))
    if not math.isfinite(number) or (number <= 0 if positive else number < 0):
        raise ValueError(
            "must be a finite positive number"
            if positive
            else "must be a finite nonnegative number"
        )
    return number


def _read_table(file, filename=None):
    """Accept a path, an open stream, or FastAPI UploadFile (use from a sync route)."""
    if isinstance(file, (str, Path)):
        path = Path(file)
        raw, filename = path.read_bytes(), path.name
    else:
        filename = (
            filename or getattr(file, "filename", None) or getattr(file, "name", None)
        )
        stream = getattr(file, "file", file)
        raw = stream.read()
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
    suffix = Path(filename or "upload.csv").suffix.lower()
    if suffix == ".csv":
        return list(csv.reader(StringIO(raw.decode("utf-8-sig")), strict=True))
    if suffix in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook

        from openpyxl.utils.exceptions import InvalidFileException

        try:
            book = load_workbook(BytesIO(raw), read_only=True, data_only=True)
        except (BadZipFile, InvalidFileException, KeyError, ParseError) as exc:
            raise ValueError(
                "Cannot read Excel file: the workbook is invalid or damaged"
            ) from exc
        try:
            return list(book.worksheets[0].iter_rows(values_only=True))
        finally:
            book.close()
    raise ValueError("Use UTF-8 CSV or .xlsx/.xlsm; legacy .xls is not supported")


def _days_between(start, end):
    weeks, days = divmod(max((end - start).days, 0), 7)
    return weeks * 5 + sum(
        (start.weekday() + day) % 7 < 5 for day in range(1, days + 1)
    )


def import_po_list(
    file,
    *,
    db_path=None,
    conn=None,
    preview=False,
    as_of: date | None = None,
    filename=None,
) -> ImportResult:
    """Return preview-compatible rows; valid new rows commit only on non-preview calls.

    With a supplied connection the caller owns its transaction and must commit.
    Supplier is optional, matching the frontend, and falls back to the email domain.
    """
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    result = ImportResult(preview=preview)
    try:
        table = _read_table(file, filename)
    except (ValueError, UnicodeError, csv.Error, OSError) as exc:
        result.file_errors.append(str(exc))
        return result
    if not table:
        result.missing = list(REQUIRED_COLUMNS)
        result.file_errors.append("File is empty")
        return result
    headers = []
    for value in table[0]:
        key = _string(value).lower().replace("_", " ")
        headers.append(ALIASES.get(key, key.replace(" ", "_")))
    result.missing = [name for name in REQUIRED_COLUMNS if name not in headers]
    duplicate_headers = sorted(
        {name for name in headers if name and headers.count(name) > 1}
    )
    if result.missing:
        result.file_errors.append("Missing columns: " + ", ".join(result.missing))
    if duplicate_headers:
        result.file_errors.append("Duplicate columns: " + ", ".join(duplicate_headers))
    if result.file_errors:
        return result
    own_connection = conn is None
    if own_connection:
        conn = connect(db_path or os.getenv("DB_PATH", "data/po.sqlite"))
    today = as_of or date.today()
    seen = set()
    try:
        existing = {
            row[0] for row in conn.execute("SELECT po_number FROM purchase_orders")
        }
        suppliers = {
            row[0] for row in conn.execute("SELECT supplier_email FROM purchase_orders")
        }
        for line, cells in enumerate(table[1:], start=2):
            if not any(_string(value) for value in cells):
                continue
            values = dict(zip(headers, cells))
            po = _string(values.get("po_number"))
            email = _string(values.get("supplier_email")).lower()
            row = {
                "line": line,
                "po": po,
                "supplierName": _string(values.get("supplier")),
                "supplierEmail": email,
                "item": _string(values.get("item")),
                "currency": _string(values.get("currency")).upper() or "USD",
                "kind": "new",
                "qty": None,
                "unitPrice": None,
                "sentDate": "",
                "requestedDate": "",
            }
            problems = []
            if len(cells) != len(headers):
                problems.append("row has a different number of cells than the header")
            if not po:
                problems.append("missing po_number")
            elif po in seen:
                problems.append("duplicate po_number in file")
            seen.add(po)
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                problems.append("missing or invalid supplier_email")
            for column, target in (("quantity", "qty"), ("unit_price", "unitPrice")):
                try:
                    row[target] = _number(
                        values.get(column), positive=column == "quantity"
                    )
                except (TypeError, ValueError) as exc:
                    problems.append(f"{column} {exc}")
            for column, target in (
                ("sent_date", "sentDate"),
                ("requested_ship_date", "requestedDate"),
            ):
                try:
                    row[target] = _date(values.get(column))
                except (TypeError, ValueError):
                    problems.append(
                        f"{column} must be a real date in YYYY-MM-DD or M/D/YYYY"
                    )
            if problems:
                row.update(kind="error", error="; ".join(problems))
            elif po in existing:
                row["kind"] = "tracked"
            else:
                order = PurchaseOrder(
                    po,
                    row["supplierName"] or email.split("@")[1],
                    email,
                    row["item"],
                    row["qty"],
                    row["unitPrice"],
                    row["currency"],
                    row["sentDate"],
                    row["requestedDate"],
                )
                row["statusAfter"] = (
                    "no_reply"
                    if _days_between(date.fromisoformat(order.sent_date), today) >= 2
                    else "awaiting"
                )
                row["newSupplier"] = email not in suppliers
                if not preview:
                    inserted = conn.execute(
                        "INSERT INTO purchase_orders (po_number, supplier, supplier_email, item, "
                        "quantity_ordered, unit_price, currency, sent_date, requested_date, original_date, status) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending') ON CONFLICT(po_number) DO NOTHING",
                        (
                            order.po_number,
                            order.supplier,
                            order.supplier_email,
                            order.item,
                            order.quantity,
                            order.unit_price,
                            order.currency,
                            order.sent_date,
                            order.requested_date,
                            order.requested_date,
                        ),
                    )
                    if not inserted.rowcount:
                        row["kind"] = "tracked"
                existing.add(po)
                suppliers.add(email)
            result.rows.append(row)
        if own_connection:
            conn.commit()
        return result
    except Exception:
        if own_connection:
            conn.rollback()
        raise
    finally:
        if own_connection:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--db", default=None)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    args = parser.parse_args()
    result = import_po_list(
        args.file, db_path=args.db, preview=args.preview, as_of=args.as_of
    )
    print(json.dumps(result.to_dict(), indent=2))
    if result.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
