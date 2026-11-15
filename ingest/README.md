# M2 data ingestion (A)

This module reads Gmail with `gmail.readonly` and imports the original purchase-order
terms. `EmailMessage` and `POExtraction` remain compatible with B's extraction code.

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
5. Run the following and approve read-only access in the browser:

```powershell
.\.venv\Scripts\python.exe ingest/fetch_emails.py --auth-only
```

The local callback writes `token.json`. Account mismatch stops before reading messages.
Testing-mode refresh tokens can expire; if Google rejects an expired/revoked token,
reauthorize using a new local `GMAIL_TOKEN_PATH`, keeping old tokens out of Git.
Do not widen the scope to send or modify messages for M2.

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
Existing PO numbers are reported as `tracked` and never overwritten.

Column names and aliases match `frontend/src/modules/po/import.ts`. `supplier` is
optional, as in the frontend, and falls back to the email domain. Note that backend
validation rejects impossible dates and non-finite numbers that the current frontend
preview does not reject; C should display the backend result as authoritative.

For C's synchronous FastAPI endpoint (or an async endpoint via `run_in_threadpool`):

```python
from ingest.po_import import import_po_list

result = import_po_list(upload_file)  # path, UploadFile or binary stream
return result.to_dict()
```

The result has `rows`, `missing`, `file_errors`, `added`, `existing`, `errors` and
`preview`. Each row has the frontend fields `line`, `po`, `supplierName`,
`supplierEmail`, `item`, `qty`, `unitPrice`, `currency`, `sentDate`, `requestedDate`,
`kind` (`new`, `tracked`, `error`) and an `error` reason if needed. On a preview call,
`added` means eligible new rows; no orders are written. With an explicitly supplied
SQLite `conn`, the caller owns the transaction and must commit.

CSV `requested_ship_date` maps to `PurchaseOrder.requested_date` and the database
`requested_date`; `quantity` maps to `quantity_ordered`. Original price, quantity and
requested date are stored as rule baselines. New rows use backend status `pending`;
the preview's `statusAfter` uses frontend `awaiting` / `no_reply`. Actual exceptions
are recomputed by `run_pipeline.py` after sync, not persisted by preview.

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
this module has no send endpoint and no send scope.

## Fetch and integrate

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

C's API and frontend integration landed on main at `78860d0` while this contribution
was being prepared. `/api/sync` already calls this module's `fetch(since)` function.
The current `/api/po-list` route still uses C's separate `api/po_list.py` importer;
switching it to `import_po_list` requires adapting the response contract shown above.
The live run below was verified through the Python pipeline and Streamlit viewer;
the Next.js Sync inbox button has not yet been exercised with this contribution.

## Verification without a Gmail account or model key

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe ingest/check_m2.py
```

`check_m2.py` uses a fresh temporary SQLite database and **gold extractions**, verifies
import repeatability and the seven expected exceptions, and writes `data/m2_check.json`.
It is a deterministic integration check, not live Gmail proof or model accuracy.
