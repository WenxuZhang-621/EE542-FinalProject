"""Connected Gmail accounts for one local team workspace.

Tokens never leave the backend. Gmail message IDs are scoped to their mailbox while
the shared EmailMessage contract and existing order baselines stay unchanged.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from dashboard.db import connect
from ingest.fetch_emails import ROOT, has_required_scopes


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def account_id(address: str) -> str:
    return hashlib.sha256(address.strip().lower().encode()).hexdigest()[:32]


def token_available(path: str | None) -> bool:
    if not path:
        return False
    from google.oauth2.credentials import Credentials

    try:
        creds = Credentials.from_authorized_user_file(path)
        return has_required_scopes(creds) and bool(creds.valid or creds.refresh_token)
    except (OSError, ValueError, KeyError, TypeError):
        return False


class MailboxStore:
    def __init__(self, db_path, emails_path: Path):
        path = Path(db_path)
        self.db_path = path if path.is_absolute() else ROOT / path
        self.emails_path = emails_path
        self.token_dir = self.db_path.parent / "mailbox_tokens"

    def connection(self):
        return closing(connect(str(self.db_path)))

    def bootstrap(self):
        """Adopt the previous single-account setup once, preserving its message IDs."""
        with self.connection() as c:
            with c:
                c.execute("BEGIN IMMEDIATE")
                if c.execute("SELECT 1 FROM mailbox_settings WHERE key='initialized'").fetchone():
                    return
                address = os.getenv("GMAIL_TEST_ACCOUNT", "").strip().lower()
                token_path = ROOT / os.getenv("GMAIL_TOKEN_PATH", "token.json")
                if not address or not token_path.is_file():
                    return
                mid = account_id(address)
                c.execute("INSERT OR IGNORE INTO mailboxes (id, address, token_path) VALUES (?, ?, ?)",
                          (mid, address, str(token_path.resolve())))
                c.execute("INSERT OR REPLACE INTO mailbox_settings VALUES ('default', ?)", (mid,))
                c.execute("INSERT INTO mailbox_settings VALUES ('initialized', '1')")
                ids = {r[0] for r in c.execute("SELECT email_id FROM email_messages")}
                ids.update(r[0] for r in c.execute("SELECT DISTINCT source_email_id FROM extractions"))
                if self.emails_path.exists():
                    ids.update(e["email_id"] for e in json.loads(self.emails_path.read_text(encoding="utf-8")))
                # Gmail message IDs are hexadecimal. Sample IDs do not belong to an account.
                import re
                c.executemany(
                    "INSERT OR IGNORE INTO mailbox_messages VALUES (?, ?, ?)",
                    [(eid, mid, eid) for eid in ids if eid and re.fullmatch(r"[0-9a-fA-F]+", eid)],
                )

    def list(self):
        self.bootstrap()
        with self.connection() as c:
            default = c.execute("SELECT value FROM mailbox_settings WHERE key='default'").fetchone()
            rows = c.execute("SELECT * FROM mailboxes ORDER BY created_at, address").fetchall()
        return {
            "defaultMailboxId": default[0] if default else None,
            "query": os.getenv("GMAIL_QUERY", ""),
            "mailboxes": [self.public(r) for r in rows],
        }

    @staticmethod
    def public(row):
        authorized = bool(row["connected"] and token_available(row["token_path"]))
        return {"id": row["id"], "address": row["address"],
                "connected": bool(row["connected"]), "authorized": authorized,
                "lastSyncAt": row["last_sync_at"], "lastError": row["last_error"]}

    def get(self, mid=None):
        self.bootstrap()
        with self.connection() as c:
            if mid is None:
                default = c.execute("SELECT value FROM mailbox_settings WHERE key='default'").fetchone()
                mid = default[0] if default else None
            row = c.execute("SELECT * FROM mailboxes WHERE id=?", (mid,)).fetchone()
        if row is None or not row["connected"]:
            raise ValueError("Connect a Gmail account in Settings > Mailboxes before syncing.")
        return dict(row)

    def add(self, address, credentials):
        """The address must come from Google's authenticated profile, never from the UI."""
        if not has_required_scopes(credentials) or not credentials.refresh_token:
            raise ValueError("Gmail read/compose access and offline authorization are required. Please reconnect.")
        address = address.strip().lower()
        mid = account_id(address)
        self.token_dir.mkdir(parents=True, exist_ok=True)
        path = self.token_dir / f"{mid}.json"
        with NamedTemporaryFile(mode="w", dir=self.token_dir, encoding="utf-8", delete=False) as f:
            f.write(credentials.to_json())
            temporary = Path(f.name)
        if os.name != "nt":
            temporary.chmod(0o600)
        temporary.replace(path)
        self.bootstrap()
        with self.connection() as c:
            with c:
                c.execute(
                    "INSERT INTO mailboxes (id, address, token_path) VALUES (?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET token_path=excluded.token_path, connected=1, last_error=NULL",
                    (mid, address, str(path)),
                )
                c.execute("INSERT OR IGNORE INTO mailbox_settings VALUES ('initialized', '1')")
                c.execute("INSERT OR IGNORE INTO mailbox_settings VALUES ('default', ?)", (mid,))
        return mid

    def set_default(self, mid):
        self.get(mid)
        with self.connection() as c:
            with c:
                c.execute("INSERT OR REPLACE INTO mailbox_settings VALUES ('default', ?)", (mid,))

    def disconnect(self, mid):
        self.get(mid)
        with self.connection() as c:
            with c:
                c.execute("UPDATE mailboxes SET connected=0, last_error=NULL WHERE id=?", (mid,))
                default = c.execute("SELECT value FROM mailbox_settings WHERE key='default'").fetchone()
                if default and default[0] == mid:
                    c.execute("DELETE FROM mailbox_settings WHERE key='default'")
                    other = c.execute("SELECT id FROM mailboxes WHERE connected=1 ORDER BY created_at, address LIMIT 1").fetchone()
                    if other:
                        c.execute("INSERT INTO mailbox_settings VALUES ('default', ?)", (other[0],))
        # Disconnect is reversible locally. Re-enabling still requires Google's consent;
        # background and manual sync both reject this account while disconnected.

    def record_sync(self, mid, error=None):
        with self.connection() as c:
            with c:
                if error:
                    c.execute("UPDATE mailboxes SET last_error=? WHERE id=?", (error, mid))
                else:
                    c.execute("UPDATE mailboxes SET last_error=NULL, last_sync_at=? WHERE id=?", (utc_now(), mid))

    def namespace(self, mid, messages):
        out = []
        with self.connection() as c:
            with c:
                for msg in messages:
                    existing = c.execute(
                        "SELECT email_id FROM mailbox_messages WHERE mailbox_id=? AND gmail_message_id=?",
                        (mid, msg.email_id),
                    ).fetchone()
                    eid = existing[0] if existing else f"gmail:{mid}:{msg.email_id}"
                    c.execute("INSERT OR IGNORE INTO mailbox_messages VALUES (?, ?, ?)", (eid, mid, msg.email_id))
                    out.append(replace(msg, email_id=eid))
        return out

    def sources(self):
        self.bootstrap()
        with self.connection() as c:
            return {r[0]: r[1] for r in c.execute(
                "SELECT m.email_id, b.address FROM mailbox_messages m JOIN mailboxes b ON b.id=m.mailbox_id"
            )}
