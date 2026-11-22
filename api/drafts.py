"""Follow-up drafts: storage and the shape the front end reads (owner: C).

agent/draft.py writes a FollowUpDraft, this module keeps it in SQLite while the buyer reviews
it, and ingest/gmail_drafts.py saves an approved one to Gmail. Nothing here sends email.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from schema import FollowUpDraft

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    draft_id        TEXT PRIMARY KEY,
    po_number       TEXT NOT NULL,
    state           TEXT NOT NULL CHECK (state IN ('review', 'saved', 'rejected')),
    gmail_draft_id  TEXT,
    data            TEXT NOT NULL,          -- the whole FollowUpDraft as JSON
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS drafts_po ON drafts (po_number, state);
"""


def ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save(conn: sqlite3.Connection, draft: FollowUpDraft, *, replace_open: bool = True) -> FollowUpDraft:
    """Insert or update one draft. A new draft for a PO replaces that PO's other drafts still
    in review, so the buyer never has two competing follow-ups for one order. Caller commits."""
    ensure(conn)
    now = _now()
    if not draft.created_at:
        draft.created_at = now
    if replace_open and draft.state == "review":
        conn.execute(
            "DELETE FROM drafts WHERE po_number = ? AND state = 'review' AND draft_id <> ?",
            (draft.po_number, draft.draft_id),
        )
    conn.execute(
        "INSERT INTO drafts (draft_id, po_number, state, gmail_draft_id, data, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (draft_id) DO UPDATE SET state = excluded.state, gmail_draft_id = excluded.gmail_draft_id, "
        "data = excluded.data, updated_at = excluded.updated_at",
        (
            draft.draft_id,
            draft.po_number,
            draft.state,
            draft.gmail_draft_id,
            json.dumps(draft.to_dict(), ensure_ascii=False),
            draft.created_at,
            now,
        ),
    )
    return draft


def get(conn: sqlite3.Connection, draft_id: str) -> FollowUpDraft | None:
    ensure(conn)
    row = conn.execute("SELECT data FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
    return FollowUpDraft.from_dict(json.loads(row[0])) if row else None


def all_drafts(conn: sqlite3.Connection) -> list[FollowUpDraft]:
    """Newest first."""
    ensure(conn)
    rows = conn.execute("SELECT data FROM drafts ORDER BY created_at DESC, rowid DESC").fetchall()
    return [FollowUpDraft.from_dict(json.loads(r[0])) for r in rows]


def clear(conn: sqlite3.Connection) -> None:
    ensure(conn)
    conn.execute("DELETE FROM drafts")


def view(d: FollowUpDraft) -> dict:
    """Front-end shape (frontend/src/modules/po/data/sample.ts FollowUpDraft, plus the review state)."""
    return {
        "id": d.draft_id,
        "po": d.po_number,
        "to": d.to,
        "subject": d.subject,
        "body": d.body,
        "why": d.why,
        "sources": [{"type": "rule", "ruleId": r} for r in d.rule_ids]
        + [{"type": "email", "emailId": e} for e in d.email_ids],
        "state": d.state,
        "language": d.language,
        "createdAt": d.created_at,
        "gmailDraftId": d.gmail_draft_id,
        "canSaveToGmail": bool(d.reply_to_email_id),
    }
