# api/ — FastAPI layer (owner: C)

The front end talks only to this app; it reads the SQLite database the Python pipeline writes and
calls the other modules in process. Next.js forwards `/api/*` here in development
(`frontend/next.config.ts`), so the browser never needs CORS or a second origin.

```sh
.venv/bin/uvicorn api.main:app --port 8000 --reload     # http://localhost:8000/docs
.venv/bin/python -m pytest tests/test_api.py
```

| Endpoint | Does | Calls |
|---|---|---|
| `GET /api/health` | what is configured: LLM key and model, Gmail credentials, database, order count | — |
| `GET /api/gmail/status` | default account, saved authorization availability, default search filter; no credentials | mailbox registry |
| `GET /api/mailboxes` | connected/disconnected accounts, default account, sync timestamps and errors | `ingest/mailboxes.py` |
| `POST /api/mailboxes/connect` | start a short-lived Google read/compose authorization; optional `mailboxId` reconnects that same account | `ingest/mailbox_oauth.py` |
| `GET /api/mailboxes/connections/{id}` | poll authorization status without credentials | OAuth session manager |
| `POST /api/mailboxes/connections/{id}/cancel` | cancel a pending connection | OAuth session manager |
| `POST /api/mailboxes/{id}/default` | select the default connected account | mailbox registry |
| `POST /api/mailboxes/{id}/disconnect` | disable future sync; preserve existing orders and message sources | mailbox registry |
| `GET /api/orders` | every PO in the front end's `PurchaseOrder` shape, plus `suppliers` and `emails` | `purchase_orders`, `events`, `exceptions`, `extractions`, `data/emails.json` |
| `GET /api/orders/{po}` | one PO with timeline, exceptions, related emails and the latest extraction | same |
| `POST /api/po-list` | multipart CSV/xlsx → `new` / `completed` / `tracked` / `errors` rows; inserts POs or completes email-created baselines, then recomputes rules | `ingest.po_import`, `rules.sync_exceptions` |
| `POST /api/sync` | `{source: auto\|gmail\|samples\|gold, since: "7d", query?: "subject:M2-DEMO"}`: fetch unseen emails → extract → upsert → rules; returns matching/processed counts, changed POs and completion time | `ingest/fetch_emails.fetch`, `run_pipeline.run`, `rules` |
| `GET /api/eval-runs` | accuracy runs from `data/eval_runs.jsonl` | `extract/eval.load_runs` |
| `POST /api/reset` | empty the demo database and the cached email JSON | `db.reset` |

**Status shown in the UI.** The `exceptions` table (rules.py) decides the status when it has a row
for the PO (`delayed` > `out_of_stock` > `partial` > `price_change` > `no_reply`); otherwise
imported POs are `awaiting` if still pending or `confirmed` after a supplier update.
Email-created POs without an imported baseline have `status: "unmatched"` and `inPoList: false`.
Rules only fire for imported POs,
because they compare against the PO list's requested date, quantity and price.

**Sync sources.** `auto` and `gmail` read the configured Gmail account. They return a clear
error if authorization or model extraction fails; they never substitute sample emails.
`samples` explicitly runs the model on `tests/samples/`; `gold` explicitly uses reference
answers without the model and labels the response accordingly. The web **Sync inbox**
dialog always requests `gmail`. Omitted `query` uses `GMAIL_QUERY`; an empty string removes
that optional filter. Sent and draft messages remain excluded. Gmail reads are limited
to imported supplier addresses; without them the endpoint returns 409, "Import your
PO list first", before contacting Gmail.

Connect accounts through **Settings > Mailboxes** on the backend computer, or authorize the
legacy CLI account with `python ingest/fetch_emails.py --auth-only`. Pass `mailboxId` to
`POST /api/sync` to select an account; omission uses the persisted default. The UI syncs
all accounts as separate sequential requests and reports partial failures.
HTTP sync itself does not launch OAuth. A revoked token returns 401 with reconnect instructions;
missing setup/model errors return 503, Gmail network errors return 502, and overlapping syncs
return 409. The saved authorization indicator does not guarantee the token is still accepted;
the real sync validates it with Google.

Each completed message, its extractions, order changes and exceptions commit together.
Retrying a partially failed batch skips completed messages, including non-order mail.
The `email_messages` table retains original text even if the JSON export was interrupted.
Backfilled older messages remain available as evidence without replacing a newer PO state.
Next.js allows up to five minutes for the synchronous request; very large or slow workloads
should eventually use a background job with progress reporting.

The API is intended for a local single-team demo with multiple mailboxes. Frontend sign-in
does not secure it or isolate tenants. Keep it bound to localhost until server authentication
and per-tenant storage are implemented. Account-management writes validate the browser origin.

**OAuth and storage.** A Google Desktop OAuth client uses a temporary loopback listener,
PKCE, one-time state and a ten-minute expiry. The browser receives an authorization URL
and opaque polling ID, never a token. Tokens remain in local ignored storage. Disconnect
disables the account in the registry and preserves its local authorization file and imported
history; it does not revoke Google's grant. Reconnecting requires Google authorization.
Mailbox IDs namespace new message IDs, while legacy message IDs are mapped to their original
account to avoid reprocessing them. All connected accounts share this workspace's POs.

**PO list import.** `ingest/po_import.py` is the sole importer and uses the same column
names and aliases as the browser preview (`frontend/src/modules/po/import.ts`). It
preserves an optional supplier name and otherwise uses the email domain. Original
price, quantity and requested date remain immutable once imported. A later import
can complete an email-only PO while retaining its supplier updates and history.

**Draft handoff.** `ingest.gmail_drafts.save_draft` saves a reviewed draft in its source
mailbox/thread. Draft persistence and approval routes still need C's integration;
see [M3 A handoff](../docs/m3-a-handoff.md). Google's compose scope includes sending,
but the application does not call a sending endpoint.

## Follow-up drafts (M3)

| Endpoint | Does | Calls |
|---|---|---|
| `POST /api/orders/{po}/draft` | the clone writes a follow-up for a PO with an open exception; replaces that PO's draft still in review | `agent.draft.draft_followup` |
| `GET /api/drafts` | every draft, newest first, with `state` (`review` / `saved` / `rejected`) | `api/drafts.py` |
| `POST /api/drafts/{id}/approve` | optional `{body}` with the buyer's edit; saves to the Gmail drafts folder of the mailbox that received the supplier's email, in that thread. **Never sends.** | `ingest.gmail_drafts.save_draft` |
| `POST /api/drafts/{id}/reject` | marks the draft rejected | `api/drafts.py` |

Drafts live in the `drafts` table (`api/drafts.py`, created on first use; one JSON `FollowUpDraft` per row).
Drafts the clone writes inside the chat are stored the same way (`chat(..., on_draft=...)`), so they show up on
the Follow-ups page. `POST /api/reset` clears them.

Errors the page shows as they are: 503 no model key, 409 the PO has no open exception / is not in the PO list /
the mailbox must be reconnected / the draft has no source email, 401 Gmail authorization lacks draft permission,
502 the model or Gmail failed. When Gmail refuses, the buyer's edit is already saved and the draft stays in review.
