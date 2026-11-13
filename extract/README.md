# Extraction and exception rules (M2 B)

`EmailMessage` → `POExtraction` via LLM structured output.

## Evaluation

Run from the repository root after setting the model credentials in `.env`.

```sh
python extract/eval.py --label M2-api
python -m pytest tests/test_rules.py
```

The evaluator scores eight fields on the 20 sample emails and records missed and extra
POs separately. It appends each run and its individual predictions to
`data/eval_runs.jsonl`. The same 20 emails were used to tune the prompt.

- **M1 replay** (`M1-local-replay`): 92.9% across 6 emails with the M1 prompt.
- **M2 baseline** (`M2-local-baseline`): 88.6% across 20 emails with the M1 prompt.
- **M2 current** (`M2-local-v4`): 89.2% across 20 emails with the M2 prompt, with one
  missed order, zero extra orders, and 3.42 seconds per email on average.

These three runs used local Qwen3-8B Q4_K_M served by llama.cpp. Use the two 20-email
runs to compare prompts. The 6-email replay used a smaller set.

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

The rules in `rules.py` compare supplier updates with the original order terms. After
the team agrees on the shared database, include `EXCEPTIONS_SCHEMA_SQL` in its
initialization. Its table has one active row per PO and exception kind.

```python
from rules import OrderTerms, refresh_exceptions

orders = [
    OrderTerms(
        po_number=row["po_number"],
        requested_date=row["requested_date"],
        sent_date=row["sent_date"],
        quantity=row["quantity"],
        unit_price=row["unit_price"],
        currency=row["currency"],
    )
    for row in original_orders
]
with conn:
    refresh_exceptions(conn, orders, extractions, emails=inbound_emails)
```

Map the CSV column `requested_ship_date` to `requested_date` on import. Pass the
original order terms, all known extractions in chronological order, and inbound
emails for the orders being refreshed. This retains an earlier delay when a later
message only changes price and recognizes replies even when extraction yields no
order.
