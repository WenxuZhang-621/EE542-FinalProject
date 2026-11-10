# frontend/

Web UI for the PO follow-up assistant: TypeScript, Next.js 16, React 19, MUI 6.

**Status: front-end demo.** Every page runs on sample data in `src/modules/po/data/sample.ts`
(fictional companies on `example.com` domains). Nothing calls the Python pipeline yet, and
the chat answers are scripted. Refreshing the page (or **Reset sample data** in the user
menu) resets the demo; you stay signed in.

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
| `/orders` | Counts, the "needs attention" list, and every PO. **Import PO list** loads a CSV; **Sync inbox** simulates a new supplier email that turns PO-2026-0441 red. |
| `/orders/[po]` | One PO: key facts, timeline, the latest email, and the fields the LLM extracted from it. |
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

## Connecting to the Python backend (next step)

The plan is a small FastAPI app that reads the SQLite database the pipeline writes, with
Next.js forwarding `/api/*` to it in development:

| Endpoint | Replaces |
|---|---|
| `GET /api/orders`, `GET /api/orders/{po}` | `ORDERS` in `sample.ts` |
| `POST /api/po-list` | `importOrders` in `store.tsx` |
| `POST /api/sync` | `sync` in `store.tsx` (fetch emails, extract, flag) |
| `GET /api/drafts`, `POST /api/drafts/{id}/approve` | `DRAFTS`, `approve` |
| `POST /api/chat` | `answer()` in `PoChatLauncher.tsx` |

Pages can be switched one at a time; all data access already goes through `store.tsx`.

## Layout

```
src/app/(po)/           pages (orders, follow-ups, playbook, evaluation) and the shared layout
src/modules/po/data/    sample data and display helpers
src/modules/po/import.ts  CSV parsing, row checks, the no-reply rule
src/modules/po/store.tsx  in-memory demo state; the place to plug in API calls
src/modules/po/components/  nav bar, chat panel, import dialog, small shared pieces
public/samples/         sample and template PO lists
```
