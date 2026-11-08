"""SQLite schema for the dashboard."""
import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", "data/po.sqlite")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS purchase_orders (
    po_number          TEXT PRIMARY KEY,
    supplier           TEXT NOT NULL,
    status             TEXT NOT NULL,
    original_date      TEXT,
    confirmed_date     TEXT,
    quantity_ordered   REAL,
    quantity_confirmed REAL,
    unit_price         REAL,
    currency           TEXT,
    last_email_id      TEXT,
    updated_at         TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number        TEXT NOT NULL,
    change_type      TEXT NOT NULL,
    old_value        TEXT,
    new_value        TEXT,
    source_email_id  TEXT,
    notes            TEXT,
    created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (po_number) REFERENCES purchase_orders(po_number)
);
"""


def connect(path: str = DB_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn
