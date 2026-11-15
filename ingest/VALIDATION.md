# M2 ingestion validation and handoff

Verified on 2026-11-14 against main commit `7b48a90` plus this ingestion change.
The complete commands and interface contract are in [README.md](README.md).

Before upload, this branch was rebased onto C's merged platform commit `78860d0`.
The combined suite then passed all 48 tests. The live Gmail evidence below records
the earlier 42-test ingestion run; its inputs and measured results are unchanged.

## A's acceptance results

| Check | Observed result |
| --- | --- |
| Gmail OAuth | Desktop client, test account verified, `gmail.readonly` only |
| Actual mail transport | Ten fictional messages sent from a separate authorized account; all ten fetched through Gmail API |
| Message contract | Ten unique Gmail IDs, thread IDs present, body text preserved |
| Original PO import | 40 rows, 10 fictional supplier addresses, no validation errors |
| Repeat import | 40 tracked rows, no overwrites |
| Actual model pipeline | Ten received messages produced ten PO updates |
| Exception integration | Exactly seven expected exceptions, including three no-reply orders |
| Original baselines | All imported quantities, prices and requested dates retained |
| Automated tests | `python -m pytest -q`: 42 passed |
| Fixture-only check | `python ingest/check_m2.py`: passed using gold extractions |

The seven exceptions are `PO-M2-0001` delayed by 14 days, `0002` partial,
`0003` price change (USD 2.00 to 2.20), `0004` out of stock, and `0011`-`0013`
with no reply. The reference date is 2026-11-14. Later demonstrations must regenerate
the dates or intentionally evaluate at this reference date.

Actual transport used Gmail's plain-text/HTML alternatives. PDF and XLSX attachment
parsing passed local MIME tests, including a real digital PDF, remote attachment
bodies and corrupt attachment handling; live attachment delivery was not exercised.

## Model evidence, separate from ingestion acceptance

The live run used the previously available local `Meta-Llama-3.1-8B-Instruct-Q4_K_M`
model through llama.cpp. Gold extraction JSON was not substituted into that run.

For the ten received messages, nine of the ten evaluated fields were correct for
every order (90/100 field comparisons). All ten `supplier` values were company names
instead of the actual sender domain required by B's current prompt. The ten fictional
suppliers were simulated by one authorized sender, so their email headers intentionally
differ from the checked-in fixtures. This normalization issue is a model follow-up for B.

A separate unmodified evaluation was run with:

```powershell
.\.venv\Scripts\python.exe extract/eval.py --label M2-local-smoke
```

It used the existing 20 bilingual samples and 22 gold orders: 94.09% field accuracy,
zero missed orders and one extra predicted order; mean 1.53 seconds per email. The
existing scoring method reports extra predictions separately and does not subtract
them from field accuracy. On the original six M1 samples, rescored in the same run,
accuracy was 91.43%. This is a local smoke run, not an AWS/vLLM deployment or a
historical M1 measurement. The raw local results remain in ignored `data/eval_runs.jsonl`.

## B/C integration handoff

- Use the same `tests/samples/po_list_40.csv` and `tests/samples/m2_inbox/` dataset.
- C can call `import_po_list(upload_file)` and return `result.to_dict()`; async routes
  should offload the synchronous parser. Call `fetch("7d", query="subject:M2-DEMO")`
  for this demo, then pass the returned messages through the existing pipeline.
- Import the CSV before processing email. Never pass `--reset` after baseline import.
- Credentials and refresh tokens are local and ignored. Each developer needs their
  own authorized Gmail account; no credentials are in this contribution.
- C's FastAPI and Next.js integration was merged in `78860d0`. The sync endpoint calls
  A's `fetch(since)`; the PO import endpoint still uses C's separate importer, whose
  result contract differs from A's. Next.js button-level integration and AWS/vLLM
  deployment were not verified in this run. The existing Streamlit page was used to
  inspect the real local database; its sidebar
  still describes the older M1 sample workflow. Its price summary labels the stored
  baseline as a new price; use the exception table's USD 2.00 to 2.20 result until the
  display is corrected. No-reply is an exception, while the underlying PO remains pending.
- B should check the live sender-domain normalization and the one extra prediction
  reported by the separate 20-sample evaluation.

No email was sent to a real supplier or to an instructor. No real inbox content,
Gmail IDs, account addresses, client credentials or refresh tokens are checked in.
