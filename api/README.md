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
| `GET /api/orders` | every PO in the front end's `PurchaseOrder` shape, plus `suppliers` and `emails` | `purchase_orders`, `events`, `exceptions`, `extractions`, `data/emails.json` |
| `GET /api/orders/{po}` | one PO with timeline, exceptions, related emails and the latest extraction | same |
| `POST /api/po-list` | multipart CSV/xlsx → `new` / `tracked` / `errors` rows; new POs are inserted, then the rules run so "no reply" shows at once | `api/po_list.py`, `rules.sync_exceptions` |
| `POST /api/sync` | `{source: auto\|gmail\|samples\|gold}`: fetch emails not seen before → extract → upsert → rules; returns counts and the POs whose status changed | `ingest/fetch_emails.fetch`, `run_pipeline.run`, `rules` |
| `GET /api/eval-runs` | accuracy runs from `data/eval_runs.jsonl` | `extract/eval.load_runs` |
| `POST /api/reset` | empty the demo database and the cached email JSON | `db.reset` |

**Status shown in the UI.** The `exceptions` table (rules.py) decides the status when it has a row
for the PO (`delayed` > `out_of_stock` > `partial` > `price_change` > `no_reply`); otherwise the
extraction status is used, with `pending` shown as `awaiting`. Rules only fire for imported POs,
because they compare against the PO list's requested date, quantity and price.

**Sync sources.** `auto` tries Gmail (needs `credentials.json` and A's `fetch()`), else the sample
inbox `tests/samples/`. `gold` processes the sample inbox with the reference answers instead of
the LLM; it exists for UI demos on machines without an API key, and the response and the toast say
"reference answers". The front end picks `gold` only when `/api/health` reports no LLM key.

**PO list import.** `api/po_list.py` uses the same column names and aliases as the browser preview
(`frontend/src/modules/po/import.ts`). `purchase_orders.supplier` is the supplier's email domain,
the same key extract/ uses, so an imported PO and its later emails land on one supplier.
