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
    updated_at         TEXT DEFAULT CURRENT_TIMESTAMP,
    supplier_email     TEXT,
    item               TEXT,
    sent_date          TEXT,
    requested_date     TEXT
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

-- Every POExtraction ever produced, oldest first. rules.py replays this history after
-- each sync, so an earlier delay is still known when a later sync brings no new email.
CREATE TABLE IF NOT EXISTS extractions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_email_id  TEXT NOT NULL,
    email_date       TEXT,
    po_number        TEXT,
    data             TEXT NOT NULL
);

-- One active row per PO and exception kind (schema.POException), written by rules.py.
CREATE TABLE IF NOT EXISTS exceptions (
    po_number       TEXT NOT NULL REFERENCES purchase_orders(po_number) ON DELETE CASCADE,
    kind            TEXT NOT NULL,
    detail          TEXT NOT NULL,
    detected_at     TEXT NOT NULL,
    source_email_id TEXT,
    PRIMARY KEY (po_number, kind)
);
"""

# Columns added after M1; databases created before then get them on connect.
_PO_LIST_COLUMNS = ("supplier_email", "item", "sent_date", "requested_date")


def reset(conn: sqlite3.Connection) -> None:
    """Empty every table (used by the demo's reset button)."""
    conn.executescript("DELETE FROM exceptions; DELETE FROM extractions; "
                       "DELETE FROM events; DELETE FROM purchase_orders;")
    conn.commit()


def connect(path: str = DB_PATH) -> sqlite3.Connection:
    p = Path(path)
    if not p.is_absolute():  # relative to the repo root, wherever the command runs from
        p = Path(__file__).resolve().parents[1] / p
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite ignores foreign keys without this
    conn.executescript(SCHEMA_SQL)
    have = {row["name"] for row in conn.execute("PRAGMA table_info(purchase_orders)")}
    for column in _PO_LIST_COLUMNS:
        if column not in have:
            conn.execute(f"ALTER TABLE purchase_orders ADD COLUMN {column} TEXT")
    return conn
