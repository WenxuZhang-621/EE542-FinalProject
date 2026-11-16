"""Short-lived desktop OAuth sessions initiated by the local web UI.

Uses Google's desktop loopback flow with PKCE and one-time state validation.
The callback listens only on 127.0.0.1; codes and tokens are never logged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import secrets
from threading import Event, Lock, Thread
import time
from urllib.parse import parse_qs, urlparse

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from ingest.fetch_emails import ROOT, SCOPES

SESSION_SECONDS = 600


def make_flow():
    path = ROOT / os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
    if not path.is_file():
        raise ValueError("Gmail setup is missing. Add the desktop OAuth client file on the backend computer.")
    flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES, autogenerate_code_verifier=True)
    if flow.client_type != "installed":
        raise ValueError("This local app requires a Google Desktop OAuth client. See ingest/README.md.")
    return flow


def authorized_address(credentials):
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    return service.users().getProfile(userId="me").execute(num_retries=2)["emailAddress"]


@dataclass
class Session:
    id: str
    store: object
    flow: object
    expires: float
    expected_address: str | None = None
    state: str = ""
    url: str = ""
    status: str = "pending"
    error: str | None = None
    mailbox_id: str | None = None
    stop: Event = field(default_factory=Event)
    lock: Lock = field(default_factory=Lock)


class OAuthSessions:
    def __init__(self):
        self.sessions = {}
        self.lock = Lock()

    def start(self, store, reconnect_id=None):
        expected = None
        if reconnect_id:
            row = next((m for m in store.list()["mailboxes"] if m["id"] == reconnect_id), None)
            if row is None:
                raise ValueError("Mailbox not found.")
            expected = row["address"]
        with self.lock:
            now = time.monotonic()
            self.sessions = {k: v for k, v in self.sessions.items() if now < v.expires + SESSION_SECONDS}
            if any(s.status in ("pending", "processing") and now < s.expires for s in self.sessions.values()):
                raise ValueError("A Gmail connection is already waiting. Finish or cancel it before starting another.")
            flow = make_flow()
            session = Session(secrets.token_urlsafe(32), store, flow, now + SESSION_SECONDS,
                              expected_address=expected)
            manager = self

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_GET(self):
                    parsed = urlparse(self.path)
                    if parsed.path != "/":
                        self.send_error(404)
                        return
                    result = manager.callback(session, parse_qs(parsed.query))
                    message, status = result
                    content = ("<!doctype html><html lang='en'><meta charset='utf-8'>"
                               "<meta name='referrer' content='no-referrer'><title>PO Assistant</title>"
                               "<body style='font:18px system-ui;padding:48px;max-width:680px'>"
                               "<h1>PO Assistant</h1><p>" + message + "</p>"
                               "<p>You can close this tab and return to Settings &gt; Mailboxes.</p></body></html>").encode()
                    self.send_response(status)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)

            server = HTTPServer(("127.0.0.1", 0), Handler)
            server.timeout = 0.5
            try:
                flow.redirect_uri = f"http://127.0.0.1:{server.server_port}/"
                options = {"access_type": "offline", "prompt": "consent select_account"}
                if expected:
                    options["login_hint"] = expected
                session.url, session.state = flow.authorization_url(**options)
            except Exception:
                server.server_close()
                raise
            self.sessions[session.id] = session

        def listen():
            try:
                while not session.stop.is_set() and time.monotonic() < session.expires:
                    server.handle_request()
                with session.lock:
                    if session.status == "pending":
                        session.status = "expired"
                        session.error = "Authorization timed out. Select Connect Gmail to try again."
            finally:
                server.server_close()

        Thread(target=listen, daemon=True, name="gmail-oauth-callback").start()
        return {"sessionId": session.id, "authorizationUrl": session.url, "expiresIn": SESSION_SECONDS}

    def callback(self, session, params):
        with session.lock:
            if session.status != "pending" or time.monotonic() >= session.expires:
                return "This connection request has ended. Start again from PO Assistant.", 410
            state = params.get("state", [""])[0]
            if not state or not secrets.compare_digest(state, session.state):
                return "Authorization could not be verified. Return to PO Assistant and try again.", 400
            if params.get("error"):
                session.status = "cancelled"
                session.error = "Google authorization was not granted. No mailbox was connected."
                session.stop.set()
                return session.error, 200
            code = params.get("code", [""])[0]
            if not code:
                return "Missing authorization code. Please try again.", 400
            session.status = "processing"
        try:
            session.flow.fetch_token(code=code, timeout=30)
            credentials = session.flow.credentials
            address = authorized_address(credentials)
            if session.expected_address and address.casefold() != session.expected_address.casefold():
                raise ValueError("The authorized account does not match the mailbox being reconnected.")
            mid = session.store.add(address, credentials)
            with session.lock:
                session.mailbox_id = mid
                session.status = "connected"
            return "Gmail connected successfully. Read-only access is ready.", 200
        except Exception:
            with session.lock:
                session.status = "error"
                session.error = ("Gmail could not be connected. Confirm the selected account and read-only "
                                 "permission, check the connection, and try again.")
            return session.error, 400
        finally:
            session.stop.set()

    def get(self, sid):
        with self.lock:
            session = self.sessions.get(sid)
        if session is None:
            raise ValueError("Connection session not found. Start a new Gmail connection.")
        return session

    def status(self, sid):
        session = self.get(sid)
        with session.lock:
            if session.status == "pending" and time.monotonic() >= session.expires:
                session.status = "expired"
                session.error = "Authorization timed out. Please try again."
                session.stop.set()
            return {"status": session.status, "mailboxId": session.mailbox_id, "error": session.error}

    def cancel(self, sid):
        session = self.get(sid)
        with session.lock:
            if session.status == "processing":
                raise ValueError("Google authorization is finishing. Please wait for the result.")
            if session.status == "pending":
                session.status = "cancelled"
                session.error = "Connection cancelled. No mailbox was connected."
                session.stop.set()
        return self.status(sid)


sessions = OAuthSessions()
