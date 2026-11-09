"""Run LLM extraction over EmailMessage JSON and emit POExtraction JSON.

Usage:
    python extract/extract.py --in data/emails.json --out data/extractions.json

The model is reached through an OpenAI-compatible API, configured in .env:
    LLM_API_KEY, LLM_MODEL, LLM_BASE_URL (empty = OpenAI)
Moving to our own model on the cloud GPU (vLLM) only changes LLM_BASE_URL and LLM_MODEL.
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schema import EmailMessage, POExtraction, PO_EXTRACTION_JSON_SCHEMA  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
log = logging.getLogger("extract")

MAX_ATTACHMENT_CHARS = 8000  # per attachment; long PDFs/sheets are cut to keep the prompt small

SYSTEM_PROMPT = """You are an experienced procurement buyer at a small importer. You read one
supplier email (and the text of its attachments) and record the status of every purchase
order (PO) it mentions. The email may be in English or Chinese.

Use only the newest message. Ignore earlier messages quoted below it (lines starting with
">", or text after "On ... wrote:" or "-----原始邮件-----"), because they hold old dates.

Answer with a JSON object {"orders": [...]}, one item per PO mentioned in the email.
Rules for each item:
- po_number: copy exactly as written, e.g. "PO-2026-0412". If no PO number is given, use null.
- supplier: the domain of the sender's email address, e.g. "shenzhen-parts.example.com".
- Dates use ISO 8601 (YYYY-MM-DD). If the year is missing, use the year of the email date;
  if that would put the date before the email date, use the next year.
- original_date: the ship date agreed before this email. confirmed_date: the ship date the
  supplier now commits to. Use null for any date the email does not give.
- status: pick the first that applies, in this order:
  out_of_stock  the supplier cannot supply at all (quantity_confirmed = 0)
  partial       the supplier can ship only part of the quantity
  delayed       confirmed_date is later than original_date
  price_change  the supplier changed the unit price
  confirmed     date and quantity as ordered
  pending       nothing is confirmed yet
- change_type: the main change this email makes: none, date_change, quantity_change,
  price_change, cancellation or other.
- quantity_ordered, quantity_confirmed: numbers only, no units.
- unit_price, currency: only if the email states a price; currency as an ISO code, e.g. "USD".
- notes: the supplier's reason in a few English words, e.g. "factory holiday"; "" if none.
- confidence: 0 to 1, how sure you are about this item.
Never guess a value the email does not support; use null instead."""

# One email can mention several POs, so the model returns a list wrapped in an object.
# schema.py stays unchanged; this only wraps its per-PO schema. Strict structured output
# needs every property listed as required (the optional ones are already nullable).
_PO_ITEM_SCHEMA = {**PO_EXTRACTION_JSON_SCHEMA,
                   "required": list(PO_EXTRACTION_JSON_SCHEMA["properties"])}
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"orders": {"type": "array", "items": _PO_ITEM_SCHEMA}},
    "required": ["orders"],
    "additionalProperties": False,
}

_client = None


def model_name() -> str:
    return os.getenv("LLM_MODEL", "gpt-4o-mini")


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        key = os.getenv("LLM_API_KEY")
        if not key:
            raise RuntimeError("LLM_API_KEY is not set. Copy .env.example to .env and fill it in.")
        _client = OpenAI(api_key=key, base_url=os.getenv("LLM_BASE_URL") or None)
    return _client


def _user_message(msg: EmailMessage) -> str:
    parts = [f"From: {msg.from_addr}", f"Subject: {msg.subject}", f"Date: {msg.date}", "",
             msg.body_text]
    for a in msg.attachments:
        text = a.text[:MAX_ATTACHMENT_CHARS]
        cut = " (truncated)" if len(a.text) > MAX_ATTACHMENT_CHARS else ""
        parts += ["", f"--- Attachment: {a.filename}{cut} ---", text]
    return "\n".join(parts)


def _call_llm(msg: EmailMessage) -> dict:
    # LLM_JSON_MODE=object for providers without json_schema support (e.g. some Qwen APIs).
    if os.getenv("LLM_JSON_MODE", "schema") == "object":
        fmt = {"type": "json_object"}
    else:
        fmt = {"type": "json_schema",
               "json_schema": {"name": "po_extraction", "schema": RESPONSE_SCHEMA, "strict": True}}
    resp = _get_client().chat.completions.create(
        model=model_name(),
        temperature=0,
        response_format=fmt,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": _user_message(msg)}],
    )
    return json.loads(resp.choices[0].message.content)


def extract_one(msg: EmailMessage) -> list[POExtraction]:
    """Extract every PO mentioned in one email. Retries once on a bad answer, then skips."""
    for attempt in (1, 2):
        try:
            orders = _call_llm(msg)["orders"]
            return [POExtraction.from_dict({**o, "source_email_id": msg.email_id}) for o in orders]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            log.warning("email %s: unusable answer (attempt %d): %s", msg.email_id, attempt, e)
    log.error("email %s: skipped after 2 attempts", msg.email_id)
    return []


def extract_timed(msg: EmailMessage) -> tuple[list[POExtraction], float]:
    """extract_one plus wall-clock seconds, used for the speed comparison later (API vs GPU)."""
    t0 = time.perf_counter()
    out = extract_one(msg)
    return out, time.perf_counter() - t0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/emails.json")
    ap.add_argument("--out", default="data/extractions.json")
    args = ap.parse_args()

    with open(args.inp, encoding="utf-8") as f:
        msgs = [EmailMessage.from_dict(d) for d in json.load(f)]

    results: list[dict] = []
    for m in msgs:
        for ext in extract_one(m):
            results.append(ext.to_dict())

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"wrote {len(results)} extractions to {args.out}")


if __name__ == "__main__":
    main()
