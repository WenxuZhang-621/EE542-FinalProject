# dashboard/ — P3

`POExtraction` → SQLite → web dashboard.

Week 1:
- Day 2: `db.py` with `purchase_orders` and `events` tables
- Day 2–3: `ingest_result.py` — upsert; write a `delay` event when confirmed_date > original_date
- Day 3–5: Streamlit `app.py` — PO list, status filter, red rows for delays, expand to see history
- Day 5–6: "today's exceptions" summary at top (N delayed / N out of stock / N pending)
- Day 6–7: integration demo

Run: `python dashboard/ingest_result.py --in data/extractions.json && streamlit run dashboard/app.py`
