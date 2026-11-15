"""PO list import (CSV or Excel) into purchase_orders.

Column names and aliases match frontend/src/modules/po/import.ts so the browser preview and
the server agree on every row. A's ingest/po_import.py replaces this when it lands; the API
calls that module first when it exists (see api/main.py).
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime

REQUIRED = [
    "po_number",
    "supplier_email",
    "item",
    "quantity",
    "unit_price",
    "currency",
    "sent_date",
    "requested_ship_date",
]
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
    "requested_date": "requested_ship_date",
}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class ImportedRow:
    line: int
    po_number: str
    supplier: str
    supplier_email: str
    item: str
    quantity: float | None
    unit_price: float | None
    currency: str
    sent_date: str | None
    requested_date: str | None
    kind: str = "new"  # new | tracked | error
    error: str = ""


@dataclass
class ImportResult:
    new: list[ImportedRow] = field(default_factory=list)
    tracked: list[ImportedRow] = field(default_factory=list)
    errors: list[ImportedRow] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "new": [asdict(r) for r in self.new],
            "tracked": [asdict(r) for r in self.tracked],
            "errors": [asdict(r) for r in self.errors],
            "missing_columns": self.missing_columns,
        }


def _iso(value: str) -> str | None:
    s = (value or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            datetime.strptime(s, "%Y-%m-%d")
            return s
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        try:
            return datetime(int(m[3]), int(m[1]), int(m[2])).date().isoformat()
        except ValueError:
            return None
    if isinstance(value, datetime):  # openpyxl gives real dates
        return value.date().isoformat()
    return None


def _number(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def read_table(filename: str, data: bytes) -> list[list]:
    """Rows (first row = header) from a CSV or an .xlsx file."""
    if filename.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = [
                ("" if v is None else (v.date().isoformat() if isinstance(v, datetime) else v)) for v in row
            ]
            if any(str(c).strip() for c in cells):
                rows.append(cells)
        return rows
    text = data.decode("utf-8-sig", errors="replace")
    return [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]


def parse_rows(table: list[list]) -> tuple[list[ImportedRow], list[str]]:
    if not table:
        return [], list(REQUIRED)
    header = []
    for h in table[0]:
        k = str(h).strip().lower().replace("_", " ")
        header.append(ALIASES.get(k, k.replace(" ", "_")))
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        return [], missing

    def col(r, name):
        i = header.index(name) if name in header else -1
        return str(r[i]).strip() if 0 <= i < len(r) else ""

    seen: set[str] = set()
    rows = []
    for i, r in enumerate(table[1:], start=2):
        po = col(r, "po_number")
        email = col(r, "supplier_email").lower()
        qty, price = _number(col(r, "quantity")), _number(col(r, "unit_price"))
        sent, requested = _iso(col(r, "sent_date")), _iso(col(r, "requested_ship_date"))
        # purchase_orders.supplier is the email domain everywhere (extract/ uses the domain too),
        # so an imported PO and the supplier's later email land on the same supplier.
        row = ImportedRow(
            i,
            po,
            email.split("@")[-1] if "@" in email else col(r, "supplier"),
            email,
            col(r, "item"),
            qty,
            price,
            col(r, "currency").upper() or "USD",
            sent,
            requested,
        )
        problems = []
        if not po:
            problems.append("missing po_number")
        elif po in seen:
            problems.append("duplicate po_number in file")
        if not _EMAIL.match(email):
            problems.append("missing or invalid supplier_email")
        if not (qty and qty > 0):
            problems.append("quantity must be a positive number")
        if price is None or price < 0:
            problems.append("unit_price must be a number")
        if not sent:
            problems.append("sent_date must be YYYY-MM-DD or M/D/YYYY")
        if not requested:
            problems.append("requested_ship_date must be YYYY-MM-DD or M/D/YYYY")
        seen.add(po)
        if problems:
            row.kind, row.error = "error", "; ".join(problems)
        rows.append(row)
    return rows, []


def import_po_list(conn: sqlite3.Connection, filename: str, data: bytes) -> ImportResult:
    """Validate every row, insert the new POs, leave existing ones untouched. Caller commits."""
    rows, missing = parse_rows(read_table(filename, data))
    result = ImportResult(missing_columns=missing)
    existing = {r["po_number"] for r in conn.execute("SELECT po_number FROM purchase_orders")}
    for row in rows:
        if row.kind == "error":
            result.errors.append(row)
        elif row.po_number in existing:
            row.kind = "tracked"
            result.tracked.append(row)
        else:
            conn.execute(
                "INSERT INTO purchase_orders (po_number, supplier, status, quantity_ordered, unit_price, currency, "
                "supplier_email, item, sent_date, requested_date) VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)",
                (
                    row.po_number,
                    row.supplier,
                    row.quantity,
                    row.unit_price,
                    row.currency,
                    row.supplier_email,
                    row.item,
                    row.sent_date,
                    row.requested_date,
                ),
            )
            existing.add(row.po_number)
            result.new.append(row)
    return result
