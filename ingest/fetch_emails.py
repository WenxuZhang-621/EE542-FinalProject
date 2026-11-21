"""Read supplier Gmail messages and attachments for imported purchase orders."""

from __future__ import annotations

import argparse
import base64
from contextlib import closing
from datetime import datetime, timedelta, timezone
from email.message import Message
from email.utils import parsedate_to_datetime, parseaddr
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from schema import Attachment, EmailMessage

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/gmail.compose"]
LOG = logging.getLogger(__name__)
SUPPLIER_BATCH_SIZE = 25


def has_required_scopes(credentials):
    """Check granted/saved scopes, never inject new scopes into an old credential."""
    granted = credentials.granted_scopes
    return set(SCOPES).issubset(granted if granted is not None else (credentials.scopes or []))


def supplier_addresses(conn=None, *, db_path=None):
    """Only imported PO contacts may enter the Gmail search allowlist."""
    if conn is None:
        from dashboard.db import connect
        with closing(connect(db_path or os.getenv("DB_PATH", "data/po.sqlite"))) as connection:
            return supplier_addresses(connection)
    return sorted({r[0].strip().lower() for r in conn.execute(
        "SELECT supplier_email FROM purchase_orders WHERE in_po_list=1"
    ) if r[0] and r[0].strip()})


def load_settings():
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)


def gmail_service(*, interactive: bool = True, token_file: Path | None = None):
    """Authorize a desktop client; keep its refresh token only on this computer."""
    from google.auth.transport.requests import Request
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    load_settings()
    client_path = ROOT / os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
    token_path = token_file or ROOT / os.getenv("GMAIL_TOKEN_PATH", "token.json")
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path))
        if not has_required_scopes(creds):
            if not interactive:
                raise RuntimeError("Reconnect this Gmail account in Settings > Mailboxes: "
                                   "M3 requires read and compose access to save approved drafts.")
            creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                if not interactive:
                    raise
                creds = None
        if not creds or not creds.valid:
            if not interactive:
                raise RuntimeError(
                    "Gmail authorization is required. On the computer running the backend, "
                    "run python ingest/fetch_emails.py --auth-only, then retry sync."
                )
            if not client_path.is_file():
                raise RuntimeError(
                    "Missing desktop OAuth credentials.json. See ingest/README.md."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)
            creds = flow.run_local_server(
                port=0,
                access_type="offline",
                prompt="consent",
                timeout_seconds=300,
                authorization_prompt_message="Authorize Gmail reading and saving approved drafts in your browser.",
                success_message="Gmail authorization complete. You can close this tab.",
            )
        if not has_required_scopes(creds):
            raise RuntimeError("Gmail read and compose permissions were not both granted. Please reconnect.")
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        if os.name != "nt":
            token_path.chmod(0o600)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def connection_status() -> dict:
    """Report local setup without contacting Google or returning token contents."""
    load_settings()
    token_path = ROOT / os.getenv("GMAIL_TOKEN_PATH", "token.json")
    account = os.getenv("GMAIL_TEST_ACCOUNT", "")
    try:
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(str(token_path))
        authorized = has_required_scopes(creds) and bool(creds.valid or creds.refresh_token)
    except (OSError, ValueError, KeyError):
        authorized = False
    return {
        "account": account,
        "authorized": bool(account and authorized),
        "query": os.getenv("GMAIL_QUERY", ""),
    }


def since_query(since: str, *, now: datetime | None = None) -> str:
    match = re.fullmatch(r"([1-9]\d*)([dh])", since)
    if match:
        count, unit = int(match[1]), match[2]
        if unit == "d":
            return f"newer_than:{count}d"
        boundary = (now or datetime.now(timezone.utc)) - timedelta(hours=count)
    else:
        try:
            boundary = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("--since must be 7d, 24h, or an ISO date/time") from exc
        if boundary.tzinfo is None:
            boundary = boundary.replace(tzinfo=timezone.utc)
    return f"after:{int(boundary.timestamp())}"


def _headers(part):
    return {h["name"].lower(): h["value"] for h in part.get("headers", [])}


def _body_bytes(part, message_id, service):
    body = part.get("body", {})
    if body.get("attachmentId"):
        body = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=body["attachmentId"])
            .execute(num_retries=3)
        )
    data = body.get("data", "")
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _text(raw, part):
    header = Message()
    header["content-type"] = _headers(part).get(
        "content-type", "text/plain; charset=utf-8"
    )
    try:
        return raw.decode(header.get_content_charset() or "utf-8", errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def html_text(raw: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw, "html.parser")
    for element in soup(["script", "style", "head"]):
        element.decompose()
    return soup.get_text(separator="\n", strip=True)


def attachment_text(raw: bytes, filename: str, mime_type: str) -> str:
    """Extract digital PDF and Excel text; scanned PDF OCR is outside M2 scope."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" or mime_type == "application/pdf":
        import pdfplumber

        with pdfplumber.open(BytesIO(raw)) as pdf:
            return "\n\n".join(page.extract_text() or "" for page in pdf.pages).strip()
    if suffix in (".xlsx", ".xlsm") or mime_type in (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel.sheet.macroEnabled.12",
    ):
        from openpyxl import load_workbook

        book = load_workbook(BytesIO(raw), read_only=True, data_only=True)
        try:
            sections = []
            for sheet in book:
                rows = [
                    "\t".join("" if cell is None else str(cell) for cell in row)
                    for row in sheet.iter_rows(values_only=True)
                    if any(cell is not None for cell in row)
                ]
                sections.append(f"[{sheet.title}]\n" + "\n".join(rows))
            return "\n\n".join(sections)
        finally:
            book.close()
    if mime_type.startswith("text/") or suffix in (".txt", ".csv"):
        text = raw.decode("utf-8-sig", errors="replace")
        return html_text(text) if mime_type == "text/html" else text
    return ""


def parse_message(message: dict, service) -> EmailMessage:
    """Parse nested MIME without writing untrusted attachment filenames to disk."""
    payload = message.get("payload", {})
    headers = _headers(payload)
    attachments = []

    def visit(part):
        kind = part.get("mimeType", "").lower()
        filename = part.get("filename", "")
        disposition = _headers(part).get("content-disposition", "").lower()
        if filename or disposition.startswith("attachment"):
            raw = _body_bytes(part, message["id"], service)
            try:
                text = attachment_text(raw, filename, kind)
            except Exception as exc:
                LOG.warning(
                    "Attachment text unavailable for message %s (%s)",
                    message["id"],
                    type(exc).__name__,
                )
                text = ""
            attachments.append(Attachment(filename=filename, text=text, mime_type=kind))
            return ""
        parts = part.get("parts", [])
        if parts:
            values = [(child.get("mimeType", ""), visit(child)) for child in parts]
            if kind == "multipart/alternative":
                plain = [
                    text
                    for child_kind, text in values
                    if child_kind == "text/plain" and text.strip()
                ]
                return (
                    "\n".join(plain)
                    if plain
                    else next((text for _, text in values if text.strip()), "")
                )
            return "\n\n".join(text for _, text in values if text.strip())
        if kind in ("text/plain", "text/html"):
            text = _text(_body_bytes(part, message["id"], service), part)
            return html_text(text) if kind == "text/html" else text
        return ""

    body_text = visit(payload).strip()
    if message.get("internalDate"):
        timestamp = datetime.fromtimestamp(
            int(message["internalDate"]) / 1000, timezone.utc
        )
    else:
        timestamp = parsedate_to_datetime(headers["date"])
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
    return EmailMessage(
        email_id=message["id"],
        thread_id=message.get("threadId", ""),
        from_addr=parseaddr(headers.get("from", ""))[1],
        subject=headers.get("subject", ""),
        date=timestamp.isoformat(timespec="seconds"),
        body_text=body_text,
        attachments=attachments,
    )


def verify_account(service, expected_account):
    actual = (
        service.users().getProfile(userId="me").execute(num_retries=3)["emailAddress"]
    )
    if actual.casefold() != expected_account.strip().casefold():
        raise RuntimeError(
            "Authorized Gmail does not match GMAIL_TEST_ACCOUNT. No messages were read."
        )
    return actual


def fetch(
    since: str,
    *,
    service=None,
    max_messages: int = 50,
    query: str = "",
    expected_account: str | None = None,
    supplier_emails: list[str] | None = None,
    db_path=None,
) -> list[EmailMessage]:
    load_settings()
    allowed = set(supplier_addresses(db_path=db_path) if supplier_emails is None else
                  (address.strip().lower() for address in supplier_emails))
    if not allowed:
        return []  # Do not authorize, list or read Gmail before importing a PO list.
    if any(not re.fullmatch(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", address)
           for address in allowed):
        raise ValueError("Imported supplier emails contain an invalid search address.")
    expected_account = expected_account or os.getenv("GMAIL_TEST_ACCOUNT", "")
    if not expected_account:
        raise ValueError("Set GMAIL_TEST_ACCOUNT in .env before connecting Gmail.")
    if max_messages < 1:
        raise ValueError("max_messages must be positive")
    # Outbound POs and drafts must not suppress the no-reply exception.
    search = f"{since_query(since)} -in:sent -in:drafts"
    if query.strip():
        search += f" ({query.strip()})"
    service = service or gmail_service()
    verify_account(service, expected_account)
    emails, seen = [], set()
    addresses = sorted(allowed)
    for start in range(0, len(addresses), SUPPLIER_BATCH_SIZE):
        batch = addresses[start:start + SUPPLIER_BATCH_SIZE]
        filtered_search = search + " from:(" + " OR ".join(batch) + ")"
        page_token, count = None, 0
        while count < max_messages:
            options = dict(userId="me", q=filtered_search, maxResults=min(500, max_messages-count))
            if page_token:
                options["pageToken"] = page_token
            page = service.users().messages().list(**options).execute(num_retries=3)
            for item in page.get("messages", []):
                if item["id"] in seen:
                    continue
                seen.add(item["id"])
                message = service.users().messages().get(
                    userId="me", id=item["id"], format="full"
                ).execute(num_retries=3)
                if set(message.get("labelIds", [])) & {"SENT", "DRAFT"}:
                    continue
                # Gmail search is not an exact address comparison (display names/aliases).
                sender = parseaddr(_headers(message.get("payload", {})).get("from", ""))[1].lower()
                if sender not in allowed:
                    continue
                emails.append(parse_message(message, service))
                count += 1
                if count >= max_messages:
                    break
            page_token = page.get("nextPageToken")
            if not page_token:
                break
    return sorted(emails, key=lambda email: (email.date, email.email_id))[-max_messages:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", default="7d")
    parser.add_argument("--out", type=Path, default=ROOT / "data/emails.json")
    parser.add_argument("--max-messages", type=int, default=50)
    parser.add_argument("--db", default=None, help="Database containing the imported PO list")
    parser.add_argument(
        "--query", default="", help="Additional Gmail search, e.g. subject:M2-DEMO"
    )
    parser.add_argument("--auth-only", action="store_true")
    args = parser.parse_args()
    load_settings()
    try:
        if args.auth_only:
            account = os.getenv("GMAIL_TEST_ACCOUNT", "")
            if not account:
                raise ValueError("Set GMAIL_TEST_ACCOUNT in .env first.")
            verify_account(gmail_service(), account)
            print("Gmail read/compose authorization and account check passed.")
            return
        messages = fetch(args.since, max_messages=args.max_messages, query=args.query, db_path=args.db)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                [json.loads(m.to_json()) for m in messages],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Wrote {len(messages)} emails to {args.out}")
    except Exception as exc:
        parser.exit(1, f"Gmail fetch failed: {exc}\n")


if __name__ == "__main__":
    main()
