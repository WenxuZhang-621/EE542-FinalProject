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

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in API keys

# end-to-end (once all three modules are wired up)
python ingest/fetch_emails.py --since 7d --out data/emails.json
python extract/extract.py --in data/emails.json --out data/extractions.json
python dashboard/ingest_result.py --in data/extractions.json
python dashboard/app.py
```

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
