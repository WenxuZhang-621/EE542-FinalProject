from datetime import date, datetime
from io import BytesIO, StringIO
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import Workbook
from dashboard import db
from dashboard.ingest_result import save_extractions, upsert
from ingest.po_import import import_po_list
from rules import sync_exceptions
from schema import EmailMessage, POExtraction

HEADER = "po_number,supplier,supplier_email,item,quantity,unit_price,currency,sent_date,requested_ship_date"
ROW = [
    "PO-1",
    "Test Supplier",
    "sales@example.com",
    "Test item",
    "100",
    "2.50",
    "USD",
    "11/9/2026",
    "2026-12-01",
]
SAMPLES = Path(__file__).parent / "samples"


def csv_file(rows, header=HEADER):
    stream = StringIO()
    stream.write(header + "\n")
    csv.writer(stream).writerows(rows)
    stream.seek(0)
    return stream


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(str(tmp_path / "orders.sqlite"))
    yield connection
    connection.close()


def test_import_preview_and_idempotence(conn):
    result = import_po_list(
        csv_file([ROW]), conn=conn, preview=True, as_of=date(2026, 11, 14)
    )
    assert result.added == 1 and result.rows[0]["statusAfter"] == "no_reply"
    assert conn.execute("SELECT count(*) FROM purchase_orders").fetchone()[0] == 0
    assert import_po_list(csv_file([ROW]), conn=conn).added == 1
    changed = ROW.copy()
    changed[4], changed[5] = "999", "99.99"
    assert import_po_list(csv_file([changed]), conn=conn).existing == 1
    row = conn.execute("SELECT * FROM purchase_orders").fetchone()
    assert row["quantity_ordered"] == 100 and row["unit_price"] == 2.5
    assert row["sent_date"] == "2026-11-09" and row["requested_date"] == "2026-12-01"


@pytest.mark.parametrize(
    "index,value,reason",
    [
        (0, "", "missing po_number"),
        (2, "bad-address", "supplier_email"),
        (4, "0", "quantity"),
        (4, "-1", "quantity"),
        (4, "NaN", "quantity"),
        (4, "Infinity", "quantity"),
        (4, "10,00", "quantity"),
        (5, "", "unit_price"),
        (5, "-1", "unit_price"),
        (7, "2026-02-30", "sent_date"),
        (8, "2/30/2026", "requested_ship_date"),
    ],
)
def test_invalid_rows_do_not_write(conn, index, value, reason):
    row = ROW.copy()
    row[index] = value
    result = import_po_list(csv_file([row]), conn=conn)
    assert result.errors == 1 and reason in result.rows[0]["error"]
    assert conn.execute("SELECT count(*) FROM purchase_orders").fetchone()[0] == 0


def test_aliases_duplicates_and_missing(conn):
    aliases = "PO Number,Vendor,Vendor Email,Description,Qty,Unit Price,currency,PO Date,Need By"
    result = import_po_list(csv_file([ROW, ROW], aliases), conn=conn)
    assert result.added == 1 and result.errors == 1
    assert "duplicate po_number" in result.rows[1]["error"]
    missing = import_po_list(csv_file([["PO-2"]], "po_number"), conn=conn)
    assert "quantity" in missing.missing and missing.errors == 1
    duplicate = import_po_list(csv_file([], HEADER + ",Qty"), conn=conn)
    assert "Duplicate columns" in duplicate.file_errors[0]


def test_excel_and_uploadfile(conn):
    book = Workbook()
    sheet = book.active
    sheet.append(HEADER.split(","))
    row = ROW.copy()
    row[4], row[7] = 1000, datetime(2026, 11, 9)
    sheet.append(row)
    stream = BytesIO()
    book.save(stream)
    book.close()
    stream.seek(0)
    upload = SimpleNamespace(filename="orders.xlsx", file=stream)
    result = import_po_list(upload, conn=conn)
    assert result.added == 1 and result.errors == 0
    assert result.rows[0]["qty"] == 1000


def test_invalid_excel_returns_file_error_without_writes(conn):
    result = import_po_list(
        BytesIO(b"not an Excel workbook"), filename="bad.xlsx", conn=conn
    )
    assert result.errors == 1 and "invalid or damaged" in result.file_errors[0]
    assert conn.execute("SELECT count(*) FROM purchase_orders").fetchone()[0] == 0


def test_mixed_rows_and_utf8_bom(conn):
    row = ROW.copy()
    row[4] = "3,000"
    broken = ROW.copy()
    broken[0], broken[2] = "PO-2", ""
    content = csv_file([row, broken]).read()
    result = import_po_list(
        BytesIO(content.encode("utf-8-sig")), conn=conn, filename="orders.csv"
    )
    assert (result.added, result.errors) == (1, 1)
    assert result.rows[0]["qty"] == 3000


def test_fixture_import_to_rules(conn):
    expected = json.loads((SAMPLES / "m2_expected.json").read_text())
    result = import_po_list(SAMPLES / "po_list_40.csv", conn=conn)
    assert (result.added, result.errors) == (40, 0)
    assert (
        conn.execute(
            "SELECT count(DISTINCT supplier_email) FROM purchase_orders"
        ).fetchone()[0]
        == 10
    )
    assert import_po_list(SAMPLES / "po_list_40.csv", conn=conn).existing == 40
    messages = []
    for path in sorted((SAMPLES / "m2_inbox").glob("*.email.json")):
        message = EmailMessage.from_dict(json.loads(path.read_text()))
        gold = path.with_name(path.name.replace(".email.json", ".gold.json"))
        extractions = [
            POExtraction.from_dict(item) for item in json.loads(gold.read_text())
        ]
        save_extractions(conn, message, extractions)
        for extraction in extractions:
            upsert(conn, extraction)
        messages.append(message)
    found = sync_exceptions(
        conn, emails=messages, as_of=date.fromisoformat(expected["as_of"])
    )
    assert {(item.po_number, item.kind) for item in found} == {
        (item["po_number"], item["kind"]) for item in expected["exceptions"]
    }
    sync_exceptions(conn, emails=messages, as_of=date.fromisoformat(expected["as_of"]))
    assert conn.execute("SELECT count(*) FROM exceptions").fetchone()[0] == 7
    assert (
        conn.execute(
            "SELECT unit_price FROM purchase_orders WHERE po_number='PO-M2-0003'"
        ).fetchone()[0]
        == 2.0
    )
