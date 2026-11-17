# Gmail web sync: team handoff

This change connects the existing Next.js frontend to real Gmail ingestion and the
configured extraction model. It is a local, single-team application; publishing
this code to GitHub does not deploy a website.

## Included behavior

- Settings > Mailboxes: connect or reconnect Google accounts, select a default,
  disconnect, and inspect the last successful sync or error.
- Orders > Sync inbox: select one or all connected mailboxes, a time range, and
  an optional Gmail search filter. Each account reads up to 50 matching messages.
- Parse email text and supported attachments, extract order updates with the
  configured LLM, update SQLite, and display exceptions and source emails.
- Exclude sent mail and drafts. Keep each account's message IDs separate.
- Skip previously processed messages. Preserve completed messages after a partial
  failure and keep older backfilled messages from replacing newer order state.
- Display the backend's saved extraction in the order detail page, including an
  unchanged unit price when the model extracted it.
- Show actionable Gmail/model errors instead of silently substituting sample data.

## Run after pulling the changes

Use the repository root for Python commands. Activate your own virtual environment
and install the updated dependencies:

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

Open http://localhost:3100/orders. Next.js forwards API requests to the backend;
set API_URL when the backend uses a different local address.

Keep an existing .env when updating. On a fresh machine, copy .env.example and
configure the model endpoint, model name, and its required credential. An
OpenAI-compatible endpoint can be used; no specific hosted provider is required.

Place the Google Desktop OAuth client file at the configured
GMAIL_CREDENTIALS_PATH, normally credentials.json. Follow the Google project setup
in [ingest/README.md](../ingest/README.md). While the OAuth app is in Testing,
the project owner must add each intended account as a test user. Each user then
authorizes read-only access through Settings > Mailboxes.

Authorize from the same computer that runs the backend: the current OAuth callback
uses a temporary loopback listener. Tokens, .env, credentials.json, database files,
and fetched email data remain local and are excluded from this change.

Import the order baselines before syncing supplier replies. For the shared demo
emails, set GMAIL_QUERY=subject:M2-DEMO or enter that filter in the dialog. The
filter is optional and does not impose a format on the email body.

Existing single-account installations are adopted automatically. Database tables
are created on startup without resetting existing orders. Do not reset the
database as part of this update.

## Verification

The Python suite covers separate account credentials and IDs, default selection,
disconnect/reconnect behavior, OAuth state/replay/expiry, duplicate sync, partial
failure recovery, and older-email backfills. API tests use isolated temporary
databases and synthetic credentials.

A local end-to-end check on 2026-11-16 used a real incoming email with fictional
order data and ordinary English prose. The configured local Llama 3.1 8B model
identified 100 units and a ship-date change from December 1 to December 8, 2026.
The website displayed a seven-day delay; a repeat sync processed zero new emails
and added no duplicate events. This is one integration example, not an extraction
accuracy benchmark. Mailbox addresses, tokens, and raw mail are not included here.

## Current limits and online deployment

Sync runs on demand, not on a schedule. Scanned PDF/image OCR is not implemented.
Follow-up drafts and chat are still demonstrations; frontend sign-in is a demo
profile rather than backend authentication. Connected mailboxes share one order
database. Model output can still need correction; supplier normalization was one
issue observed in the integration check.

Before enabling real mailboxes on a public deployment, implement backend
authentication and workspace authorization, adapt OAuth to a Web application
client with the deployment's HTTPS callback, and configure durable private token
and database storage. Provision the backend/model service and configure the
frontend's API destination for that environment. No online deployment is included
in this change.
