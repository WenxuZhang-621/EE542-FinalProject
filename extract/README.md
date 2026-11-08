# extract/ — P2

`EmailMessage` → `POExtraction` via LLM structured output.

Week 1:
- Day 2: pick LLM SDK, wire `extract.py` to read/write the schema JSON
- Day 2–3: write 20 sample emails in `tests/samples/` with gold-answer JSON
- Day 3–5: prompt engineering; handle multi-PO emails, missing PO numbers, messy dates
- Day 5–6: `eval.py` — per-field accuracy; iterate to >80%
- Day 6–7: integration; rerun eval on real (anonymized) emails from interviews

Use the SDK's JSON / structured-output mode with `PO_EXTRACTION_JSON_SCHEMA` from
`schema.py`. Do not parse JSON out of free text with regex.
