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

In the sidebar, **Process sample inbox** sends the 6 sample emails in `tests/samples/` through
the LLM into SQLite, and **Run accuracy test** scores the extraction against the gold answers.
Without `LLM_API_KEY` the page still opens, but both buttons are disabled.

The same steps from the command line:

```bash
python run_pipeline.py --offline tests/samples --reset   # sample emails -> LLM -> data/po.sqlite
python extract/eval.py --label M1                        # per-field accuracy -> data/eval_runs.jsonl
```

Gmail fetching (`ingest/fetch_emails.py`) is not implemented yet; until it is, use `--offline`.

### 2. Web UI (`frontend/`)

Needs Node.js 20 or newer and pnpm (`npm install -g pnpm`).

```bash
cd frontend
pnpm install
pnpm dev                         # http://localhost:3100
```

It runs on sample data and does not need the Python side or an API key yet.

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
