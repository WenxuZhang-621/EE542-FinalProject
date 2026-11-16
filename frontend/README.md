# frontend/

Web UI for the PO follow-up assistant: TypeScript, Next.js 16, React 19, MUI 6.

**Status: orders connected to the Python backend.** With the backend running, orders,
CSV imports and Gmail sync use SQLite and the real extraction pipeline. Without it,
the UI displays labelled sample data. Follow-up drafts, playbook and chat remain scripted
demos. Sign-in stores a demo profile in the browser; it does not authorize a Gmail account.

## Run

Needs Node.js 20+ and pnpm.

```bash
cd frontend
pnpm install
pnpm dev          # http://localhost:3100
```

`pnpm typecheck`, `pnpm lint` and `pnpm build` should all pass before a commit.

## Pages

| Route | What it shows |
|---|---|
| `/login`, `/signup` | Sign-in and sign-up. Front-end only for now: any email and password work, nothing is sent or stored except the profile in the browser. Every other page redirects here when signed out. |
| `/orders` | Counts, exceptions and every PO. **Import PO list** loads a CSV; **Sync inbox** opens the real Gmail connection, time-range and search-filter dialog. |
| `/orders/[po]` | One PO: key facts, timeline, the latest email, and the fields the LLM extracted from it. |
| `/settings/mailboxes` | Connect/reconnect Gmail, choose a default, sync one or all accounts, inspect last sync/errors, and disconnect. |
| `/follow-ups` | Follow-up emails drafted by the expediter clone, with the playbook rules and emails they cite. Approve, edit or reject; nothing is sent. |
| `/playbook` | What the clone copies from a senior expediter: rules (from interviews), memory (supplier emails, RAG) and writing style. |
| `/evaluation` | Accuracy, recall, draft rating and speed per milestone (placeholder numbers for now). |
| chat (every page) | "Ask the expediter": answers show the tools used and cite their sources. |

## PO list import

CSV with these columns (common header spellings such as `PO Number` or `Qty` are mapped):

`po_number, supplier, supplier_email, item, quantity, unit_price, currency, sent_date, requested_ship_date`

Dates may be `YYYY-MM-DD` or `M/D/YYYY`. The preview marks each row as new, already tracked,
or skipped with the reason. A new PO with no supplier reply 2 or more business days after
`sent_date` is flagged **No reply**. Try it with `public/samples/po_list_sample.csv`; a blank
template is in `public/samples/po_list_template.csv`. Excel files are left to the Python
side (`ingest/po_import.py`, openpyxl).

## Python backend

`next.config.ts` forwards `/api/*` to the FastAPI app (`uvicorn api.main:app --port 8000`, see
`api/README.md`). On load `store.tsx` calls `GET /api/orders`; if that fails the pages fall back to
the bundled sample data and show a banner saying so.

| Live (backend running) | Still sample data |
|---|---|
| Orders, order detail, **Import PO list** (`POST /api/po-list`), **Sync inbox** (`POST /api/sync`), Evaluation (`GET /api/eval-runs`) | Follow-up drafts, Playbook, chat (M3) |

**Sync inbox → Read Gmail** always uses the configured Gmail account and model. It never
switches to sample answers when either service fails. Authorization, connection and extraction
errors appear in the dialog. Successful syncs show matching emails, newly processed messages,
changed orders and a completion time. Repeated syncs skip messages already processed.

Open the profile menu **Settings > Mailboxes**, or **Manage mailboxes** in the sync dialog.
Select **Connect Gmail**, continue to Google in a new tab, and grant read-only access.
The page polls for completion and restores a pending connection after refresh. You can
cancel a pending request, reconnect an account, change the default, or sync all accounts
sequentially. Sync results and original emails identify the mailbox. Disconnect preserves
existing orders and email history, and prevents further sync until the account is reconnected.

Set `GMAIL_QUERY=subject:M2-DEMO` in `.env` to default to the M2 test messages, or edit the
filter in the dialog. Connected accounts belong to one shared local workspace; changing
the demo login profile does not isolate accounts. Browser OAuth requires the backend on the
same computer. Requests run synchronously with a five-minute proxy timeout per mailbox.

## Layout

```
src/app/(po)/           pages (orders, follow-ups, playbook, evaluation) and the shared layout
src/modules/po/data/    sample data and display helpers
src/modules/po/import.ts  CSV parsing, row checks, the no-reply rule
src/modules/po/store.tsx  live API state with a labelled offline sample fallback
src/modules/po/components/  nav bar, chat panel, import dialog, small shared pieces
public/samples/         sample and template PO lists
```
