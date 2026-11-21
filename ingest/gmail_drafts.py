"""Save a buyer-reviewed FollowUpDraft in its source mailbox and original thread.

The API owner calls save_draft after approval. The only Gmail mutation here is
drafts.create. No default-mailbox fallback is permitted for missing source mappings.
"""
from __future__ import annotations

import base64
from contextlib import closing
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import getaddresses, make_msgid
import os
from pathlib import Path
import re

from dashboard.db import connect
from ingest.fetch_emails import gmail_service, verify_account
from schema import FollowUpDraft


class DraftSaveError(ValueError):
    """A draft cannot be safely associated with a connected source mailbox."""


def save_draft(draft: FollowUpDraft, *, conn=None, db_path=None, service=None) -> str:
    """Return the Gmail draft ID. Caller owns persistence of state and approval.

    conn/service are injectable for API integration and offline verification. With
    no conn, DB_PATH is resolved at call time (also works in temporary workspaces).
    Reply threading uses the original Gmail headers, never model-generated IDs.
    """
    if draft.state == "saved" and draft.gmail_draft_id:
        return draft.gmail_draft_id
    if draft.state != "review":
        raise DraftSaveError("Only a draft awaiting buyer review can be approved.")
    if not draft.reply_to_email_id:
        raise DraftSaveError("This draft has no source email. Sync the supplier reply before saving to Gmail.")
    if not draft.body.strip():
        raise DraftSaveError("The draft body cannot be empty.")
    if conn is None:
        with closing(connect(db_path or os.getenv("DB_PATH", "data/po.sqlite"))) as connection:
            return save_draft(draft, conn=connection, service=service)
    source = conn.execute(
        "SELECT b.address, b.token_path, b.connected, m.gmail_message_id "
        "FROM mailbox_messages m JOIN mailboxes b ON b.id=m.mailbox_id WHERE m.email_id=?",
        (draft.reply_to_email_id,),
    ).fetchone()
    if source is None or not source["connected"] or not source["token_path"]:
        raise DraftSaveError("The source mailbox is missing or disconnected. Reconnect it in Settings > Mailboxes.")
    order = conn.execute("SELECT supplier_email, in_po_list FROM purchase_orders WHERE po_number=?",
                         (draft.po_number,)).fetchone()
    if order is None or not order["in_po_list"]:
        raise DraftSaveError("Import this PO before approving a follow-up.")
    if any(c in draft.to for c in "\r\n"):
        raise DraftSaveError("Invalid draft recipient.")
    recipients = getaddresses([draft.to])
    if (len(recipients) != 1 or not recipients[0][1]
            or recipients[0][1].casefold() != (order["supplier_email"] or "").casefold()):
        raise DraftSaveError("The draft recipient must match the imported supplier email.")
    service = service or gmail_service(interactive=False, token_file=Path(source["token_path"]))
    verify_account(service, source["address"])
    parent = service.users().messages().get(
        userId="me", id=source["gmail_message_id"], format="metadata",
        metadataHeaders=["Message-ID", "References", "Subject"],
    ).execute(num_retries=3)
    headers = {h["name"].lower(): h["value"] for h in parent.get("payload", {}).get("headers", [])}
    message_id = headers.get("message-id", "").strip()
    subject = headers.get("subject", "")
    thread = parent.get("threadId")
    if not thread or not re.fullmatch(r"<[^<>\s]+>", message_id):
        raise DraftSaveError("The source email lacks threading metadata; no Gmail draft was created.")
    # Preserve the original subject so Gmail can actually attach the reply to the thread.
    message = EmailMessage(policy=SMTP)
    message["From"] = source["address"]
    message["To"] = draft.to
    message["Subject"] = subject if re.match(r"(?i)^re\s*:", subject) else f"Re: {subject}"
    message["Message-ID"] = make_msgid()
    message["In-Reply-To"] = message_id
    refs = re.findall(r"<[^<>\s]+>", headers.get("references", ""))
    message["References"] = " ".join(dict.fromkeys([*refs, message_id]))
    message.set_content(draft.body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    # Creation is not idempotent. Do not automatically retry a lost HTTP response.
    result = service.users().drafts().create(
        userId="me", body={"message": {"raw": raw, "threadId": thread}}
    ).execute(num_retries=0)
    if not result.get("id"):
        raise DraftSaveError("Gmail did not return a draft ID. Check Drafts before retrying.")
    return result["id"]
