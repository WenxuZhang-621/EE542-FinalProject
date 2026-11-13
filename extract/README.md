# Extraction and exception rules (M2 B)

`EmailMessage` → `POExtraction` via LLM structured output.

## Evaluation

Run from the repository root after setting the model credentials in `.env`.

```sh
python extract/eval.py --label M2-api
python -m pytest tests/test_rules.py
```

The evaluator scores ten fields on the 20 sample emails and records missed and extra
POs separately. It appends each run and its individual predictions to
`data/eval_runs.jsonl`. The same 20 emails were used to tune the prompt.

Stored runs are scored again on load with the current fields and gold answers, so runs
from different milestones stay comparable. Each run also reports its accuracy on
samples 001–006 alone, the whole M1 set.

| Run | Prompt | 20 emails | Samples 001–006 |
|---|---|---|---|
| `M2-local-baseline` | M1 | 88.6% | 91.4% |
| `M2-local-v4` | M2 | 90.5% | 94.3% |

The M2 run missed one order, returned no extra orders, and took 3.42 seconds per email
on average. These figures come from scoring the stored predictions again after two
changes: `unit_price` and `currency` are now scored, and the gold answer for sample 003
no longer states an original date that the email does not give. The prompt has since
gained the words "a JSON object" for `LLM_JSON_MODE=object`, so run the evaluation once
more before quoting a final number.

These runs used local Qwen3-8B Q4_K_M served by llama.cpp.

To reproduce the local run with the [Qwen GGUF model](https://huggingface.co/Qwen/Qwen3-8B-GGUF),
start llama.cpp b12336 on the loopback address in one terminal.

```sh
llama-server --model Qwen3-8B-Q4_K_M.gguf --alias Qwen3-8B-Q4_K_M \
  --host 127.0.0.1 --port 8019 --no-webui --ctx-size 8192 --parallel 1 \
  --n-gpu-layers 99 --reasoning off --chat-template-kwargs '{"enable_thinking":false}'
```

Run the evaluation from the repository root in a second terminal.

```sh
LLM_API_KEY=local LLM_BASE_URL=http://127.0.0.1:8019/v1 \
  LLM_MODEL=Qwen3-8B-Q4_K_M LLM_DISABLE_THINKING=1 LLM_JSON_MODE=schema \
  python extract/eval.py --label M2-local-replay
```

For the team's Qwen3-8B on vLLM, set `LLM_BASE_URL=http://localhost:8001/v1`,
`LLM_MODEL=Qwen/Qwen3-8B`, `LLM_DISABLE_THINKING=1` and the service's
`LLM_API_KEY`, then run `python extract/eval.py --label M2-gpu`.

## After inbox sync

The rules in `rules.py` compare supplier updates with the original order terms and keep
one active row per PO and exception kind in the `exceptions` table. `run_pipeline.py`
already does this after every run. Any other entry point, such as the API's sync
endpoint, needs three calls.

```python
from ingest_result import save_extractions, upsert
from rules import sync_exceptions

for email in new_emails:
    extractions = extract_one(email)
    save_extractions(conn, email, extractions)   # history that the rules replay
    for extraction in extractions:
        if extraction.po_number:
            upsert(conn, extraction)
sync_exceptions(conn, emails=all_inbound_emails)
conn.commit()
```

`sync_exceptions` reads order terms from `purchase_orders` and every stored extraction
from `extractions`, so a sync that brings no new email keeps earlier exceptions. Pass
all known inbound supplier emails, not only the new ones and not the buyer's own sent
mail: any email that mentions a PO number counts as a reply for the no-reply rule.

The PO list import must fill these `purchase_orders` columns.

| Column | From the PO list |
|---|---|
| `sent_date` | `sent_date`; also marks the row as imported |
| `requested_date` | `requested_ship_date` |
| `quantity_ordered` | `quantity` |
| `unit_price`, `currency` | ordered price; later supplier prices do not overwrite it |

Known limits: an email with no PO number cannot be tied to an order, so that order can
still show as no reply. PO numbers match regardless of case and spaces, but "PO 100"
does not match "PO-100".
