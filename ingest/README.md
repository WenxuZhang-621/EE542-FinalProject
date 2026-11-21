# M2/M3 data ingestion (A)

This module reads supplier Gmail messages, imports original purchase-order terms, and
saves approved follow-up drafts in the source mailbox. `EmailMessage` and `POExtraction`
remain compatible with B's extraction code. See [the M3 handoff](../docs/m3-a-handoff.md)
for the draft interface and C's remaining approval UI integration.

## Setup

Use Python 3.11 or newer from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

On macOS/Linux, activate `.venv/bin/activate` and use `python` for the commands below.
Keep `.env`, `credentials.json`, `token.json`, real emails and SQLite databases local.
All are ignored by Git. Never share the OAuth client file or refresh token with a teammate.
Each teammate should authorize their own account.

### Google Cloud and Gmail

1. Create a Google Cloud project and enable **Gmail API**. This workflow does not need
   a Compute Engine VM, a GPU or a paid Cloud trial.
2. In **Google Auth Platform**, configure an app name, support email and contact email.
   Use **External / Testing** and add your Gmail address under **Audience / Test users**.
3. Under **Clients**, create a **Desktop app** OAuth client. Download its JSON as
   `credentials.json` in the repository root.
4. Set `GMAIL_TEST_ACCOUNT` in `.env` to the exact Gmail account to authorize.
5. Run the following and approve Gmail read and compose access in the browser:

```powershell
.\.venv\Scripts\python.exe ingest/fetch_emails.py --auth-only
```

The local callback writes `token.json`. Account mismatch stops before reading messages.
Testing-mode refresh tokens can expire; if Google rejects an expired/revoked token,
run `--auth-only` again to reauthorize, keeping tokens out of Git.
M2 used only `gmail.readonly`. M3 adds `gmail.compose` to create drafts; reconnect old
read-only accounts. Google's compose permission also includes sending, but this
application's draft module only calls `drafts.create` and has no sending endpoint.

Official references:
- https://developers.google.com/workspace/gmail/api/quickstart/python
- https://developers.google.com/workspace/gmail/api/guides/filtering
- https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages

## Import order baselines

```powershell
.\.venv\Scripts\python.exe ingest/po_import.py tests/samples/po_list_40.csv --preview
.\.venv\Scripts\python.exe ingest/po_import.py tests/samples/po_list_40.csv
```

CSV is UTF-8 (BOM accepted). Excel `.xlsx` and `.xlsm` use the first worksheet;
macros are not executed. Legacy `.xls` is not supported. Dates accept real calendar
dates in `YYYY-MM-DD` or `M/D/YYYY`, including native Excel date cells. Quantity must
be finite and positive; unit price must be finite and nonnegative. Missing or duplicate
headers prevent the entire import. Other invalid rows are reported and skipped.
Already imported PO numbers are reported as `tracked` and never overwritten.
Email-created POs are reported as `completed`: the import fills their original terms
and sets `in_po_list=1`, preserving supplier-confirmed values and source history.

Column names and aliases match `frontend/src/modules/po/import.ts`. `supplier` is
optional, as in the frontend, and falls back to the email domain. Note that backend
validation rejects impossible dates and non-finite numbers that the current frontend
preview does not reject; C should display the backend result as authoritative.

For C's synchronous FastAPI endpoint (or an async endpoint via `run_in_threadpool`):

```python
from ingest.po_import import import_po_list

result = import_po_list(upload_file)  # path, UploadFile or binary stream
return result.to_api_dict()
```

The CLI's `to_dict()` result has `rows`, `missing`, `file_errors`, `added`, `existing`,
`completed`, `errors` and `preview`. The API adapter preserves its `new`, `tracked`,
`errors`, `missing_columns` arrays and adds `completed`. Each CLI row has `line`, `po`, `supplierName`,
`supplierEmail`, `item`, `qty`, `unitPrice`, `currency`, `sentDate`, `requestedDate`,
`kind` (`new`, `completed`, `tracked`, `error`) and an `error` reason if needed. On a preview call,
`added` means eligible new rows; no orders are written. With an explicitly supplied
SQLite `conn`, the caller owns the transaction and must commit.

CSV `requested_ship_date` maps to `PurchaseOrder.requested_date` and the database
`requested_date`; `quantity` maps to `quantity_ordered`. Original price, quantity and
requested date are stored as rule baselines. New rows use backend status `pending`;
the preview's `statusAfter` uses frontend `awaiting` / `no_reply`. Actual exceptions
are recomputed after a real import and by `run_pipeline.py` after sync, never persisted
by preview. Only imported POs can produce exceptions.

## Shared test fixture

- `tests/samples/po_list_40.csv`: 40 orders, 10 fictional suppliers; all emails use example.com.
- `tests/samples/m2_inbox/`: 10 English synthetic emails, extraction gold JSON and copyable text.
- `tests/samples/m2_emails.json`: the same 10 messages as a fetch-compatible JSON list.
- `tests/samples/m2_expected.json`: expected exceptions at the fixed reference date.

The reference date is **2026-11-14**. Expected results after applying all ten gold
extractions: one delay (`PO-M2-0001`, +14 days), one partial (`0002`), one price change
(`0003`), one out-of-stock (`0004`), and exactly three no-reply orders (`0011`-`0013`).
Orders `0014`-`0040` are recent and not overdue at that reference date. Before a later
live demo, regenerate into ignored `data/m2/` with that day's date and share that exact
CSV/messages set with B and C. Otherwise the no-reply count changes as time passes.

```powershell
.\.venv\Scripts\python.exe ingest/make_m2_samples.py --as-of 2026-11-16 --out data/m2
```

Use the same dates in the orders and email bodies. Ten ready-to-copy `.txt` messages
can be sent from a **different test account** into the authorized inbox. They have no
real suppliers or customer data. Do not send any message mentioning `0011`-`0013`.
The Gmail reader excludes Sent and Drafts, so self-sent messages are intentionally
excluded and must not be used for this demo. Sending test email is a separate action;
this module has no send endpoint. The M3 compose scope includes sending capability,
but the application only uses it to save drafts after approval.

## Fetch and integrate

For browser account management, open **Settings > Mailboxes** in the local frontend.
Each account gets its own Google read and compose authorization. Choose a default mailbox or
select an account when syncing; the previous `.env` account is adopted once automatically.
New token files live under the database directory's ignored `mailbox_tokens/` folder.
Disconnect disables an account without removing its history or revoking Google's grant.
The current app is one shared team workspace, not a multi-tenant service.

The browser authorization flow uses the existing **Desktop app** client and a temporary
`127.0.0.1` callback with state validation and PKCE. It requires browser and backend on the
same computer. A remotely deployed website needs a Web OAuth client, HTTPS callback,
authenticated sessions and tenant isolation before enabling account management.
See [Google's desktop OAuth guide](https://developers.google.com/identity/protocols/oauth2/native-app)
and [loopback flow guidance](https://developers.google.com/identity/protocols/oauth2/resources/loopback-migration).

```powershell
.\.venv\Scripts\python.exe ingest/fetch_emails.py --since 7d --query "subject:M2-DEMO" --out data/gmail_m2.json
.\.venv\Scripts\python.exe run_pipeline.py --in data/gmail_m2.json
```

The second command needs B's configured LLM endpoint/key. It uses the real model;
it does not substitute gold answers. **Do not add `--reset` after importing orders**:
that flag deletes the baselines. C can call `fetch("7d")` directly and pass the returned
messages to the existing pipeline. Fetch defaults to 50 messages, follows pagination,
keeps Gmail message/thread IDs, prefers plain text over HTML alternatives, and extracts
digital PDF and Excel attachment text. An unreadable/unsupported attachment remains
in the output with empty text; parse failures are logged. Scanned PDF OCR is not included.
Fetching only the last seven days does not establish a complete historical inbox; for
older imported orders, backfill from their sent dates before interpreting no-reply.
Only sender addresses in the imported PO list are fetched. An empty allowlist returns
no messages without contacting Gmail; the live HTTP endpoint returns 409 with an
import-first instruction. Optional Gmail queries cannot bypass the sender allowlist.

C's initial API and frontend integration landed on main at `78860d0`. M3 consolidates
`/api/po-list` on this module's `import_po_list` and removes `api/po_list.py`.
The web integration provides **Orders → Sync inbox → Read Gmail**. The dialog shows
the configured account, accepts a time range and Gmail search filter, and refreshes the
orders after extraction. Use `GMAIL_QUERY=subject:M2-DEMO` for a default test-only filter.
The API uses noninteractive OAuth refresh and returns instructions if reauthorization is
needed. It does not open a browser or silently fall back to sample mail during HTTP sync.

## Verification without a Gmail account or model key

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe ingest/check_m2.py
```

`check_m2.py` uses a fresh temporary SQLite database and **gold extractions**, verifies
import repeatability and the seven expected exceptions, and writes `data/m2_check.json`.
It is a deterministic integration check, not live Gmail proof or model accuracy.

For M3, `tests/samples/m3_history/` provides 15 fictional messages, six POs and labelled
extractions covering resolved historical incidents and current delay, price increase
and stock shortage. See its README for regeneration and controlled-inbox setup.
