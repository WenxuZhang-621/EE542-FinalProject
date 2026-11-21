# EE542 Final Project — AI Purchase-Order Follow-Up Assistant

An AI assistant for small and mid-sized importers / distributors that reads supplier
emails and attachments, extracts order confirmations, lead-time changes, delays and
shortages, and surfaces exceptions on a dashboard. It plugs into the existing inbox;
it does not replace the ERP.

## Pipeline

```
Gmail inbox ──▶ ingest/ ──▶ extract/ ──▶ dashboard/
               (P1)         (P2)          (P3)
            raw email →   email →       JSON →
            EmailMessage  POExtraction  SQLite + web UI
```

All three modules share the data contracts in `schema.py`. **Do not change
`schema.py` without agreement from all three owners.**

## Modules

| Dir          | Owner | Responsibility                                                     | Week-1 deliverable                                   |
|--------------|-------|--------------------------------------------------------------------|------------------------------------------------------|
| `ingest/`    | P1    | Gmail OAuth, fetch mail, parse MIME, extract PDF/Excel attachment text | `fetch_emails.py --since 7d` → list of `EmailMessage` JSON |
| `extract/`   | P2    | LLM extraction: `EmailMessage` → `POExtraction`                     | `extract.py` + `eval.py`, >80% field accuracy on 20 samples |
| `dashboard/` | P3    | SQLite storage, upsert + delay events, web dashboard               | `ingest_result.py` + dashboard with red-flagged delays |
| `frontend/`  | —     | Web UI (Next.js + MUI): orders, PO list import, follow-up drafts, chat | Demo on sample data; see `frontend/README.md` |
| `rag/`       | P2    | Vector index over stored emails and the playbook; `search_emails`, `search_playbook` | M3; see `rag/README.md` |
| `agent/`     | P2    | The expediter clone: buyer playbook, follow-up drafts, chat with tools | M3; see `agent/README.md` |

`run_pipeline.py` runs the whole Python pipeline with one command.

## Run it locally

No Docker needed. The Python pipeline and the web UI run separately.

### 1. Python: extraction pipeline and the M1 demo page

Needs Python 3.10 or newer (3.11 recommended). The `python3` that ships with macOS is 3.9;
install a newer one from python.org or with `brew install python@3.11`.

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then set LLM_API_KEY (and LLM_MODEL / LLM_BASE_URL if not OpenAI)
```

Start the demo page at http://localhost:8501:

```bash
streamlit run dashboard/app.py
```

In the sidebar, **Process sample inbox** sends the 20 sample emails in `tests/samples/` through
the LLM into SQLite, and **Run accuracy test** scores the extraction against the gold answers.
Without `LLM_API_KEY` the page still opens, but both buttons are disabled.

The same steps from the command line:

```bash
python run_pipeline.py --offline tests/samples --reset   # sample emails -> LLM -> data/po.sqlite
python extract/eval.py --label M1                        # per-field accuracy -> data/eval_runs.jsonl
```

Supplier-filtered Gmail fetching and CSV/XLSX order import are implemented. See
[`ingest/README.md`](ingest/README.md) for OAuth setup, the shared 40-order fixture,
and the M2 integration commands. Import order baselines before running the pipeline;
do not use `--reset` afterward because it removes those baselines.

### 2. Web UI (`frontend/`)

Needs Node.js 20 or newer and pnpm (`npm install -g pnpm`).

```bash
cd frontend
pnpm install
pnpm dev                         # http://localhost:3100
```

Without the backend, the UI shows clearly labelled sample data. For real Gmail sync,
authorize the test mailbox as described in `ingest/README.md`, configure the extraction
model in `.env`, and start the backend in a second terminal from the repository root:

```bash
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open **Orders → Sync inbox**, choose a time range and optional Gmail search filter,
then select **Read Gmail**. For the M2 test messages use `subject:M2-DEMO`. The dialog
reads supplier messages from the configured Gmail account, processes up to 50 matching
messages, and refreshes the orders. Import order baselines first so exception rules
can compare the supplier's response against the original terms. Duplicate syncs do
not duplicate events; completed messages survive a later extraction failure.

Use **Settings > Mailboxes** in the profile menu, or **Manage mailboxes** in the sync
dialog, to connect more Gmail accounts, choose a default account, and disconnect accounts.
Each account authorizes Gmail read and compose access on Google. Reconnect old read-only
accounts to save drafts. Google compose also permits sending, but the application only
creates drafts after buyer approval. The existing local account is adopted
automatically, preserving imported orders and email history. Select one mailbox or all
connected mailboxes when syncing; source emails show the receiving mailbox.

This is a local, single-team workspace: connected mailboxes share its order database.
The sign-in page is a demo profile, not server authentication or tenant isolation.
OAuth uses a desktop loopback callback, so authorize from the same computer running the
backend. Chat and playbook use the backend. The Gmail draft-saving service is implemented,
but the Follow-ups approval UI still needs C's persistence/API integration; see
[the M3 A handoff](docs/m3-a-handoff.md). Sync is manual, not scheduled.

For teammate setup, validation details, and online-deployment prerequisites, see
[the Gmail web sync handoff](docs/GMAIL_WEB_HANDOFF.md).

### Created locally, never committed

`.venv/`, `frontend/node_modules/`, `.env` and everything in `data/`.

## Week 1 plan

- **Day 1** — agree on `schema.py` (done, see file), set up repo and environment
- **Day 2–5** — each module built independently against the schema
- **Day 6–7** — integration: one command runs the full pipeline; a "lead-time pushed
  two weeks" email turns the PO row red on the dashboard

## Conventions

- Python 3.11+, `black` formatting
- Each module has its own `README.md` and is runnable on its own
- Test samples live in `tests/samples/` (synthetic or anonymized only — never real
  customer data in git)
- Secrets go in `.env` (git-ignored); see `.env.example`
