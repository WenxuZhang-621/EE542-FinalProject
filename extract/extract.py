"""Run LLM extraction over EmailMessage JSON and emit POExtraction JSON.

Usage:
    python extract/extract.py --in data/emails.json --out data/extractions.json

The model is reached through an OpenAI-compatible API, configured in .env:
    LLM_API_KEY, LLM_MODEL, LLM_BASE_URL (empty = OpenAI)
Set LLM_DISABLE_THINKING=1 for Qwen3 served by vLLM.
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

SYSTEM_PROMPT = """Extract purchase-order (PO) updates from one English or Chinese supplier email.
Read the subject, the latest message body, and the attached text. Ignore quoted earlier
messages (lines starting with ">", or replies after "On ... wrote:" or "-----原始邮件-----").
Attachments can contain the entire update even if the body just says to see the attachment.

Return {"orders": [...]} with one item per order that has an update. For unrelated mail,
return {"orders": []}. For each order, copy its PO number verbatim from the input, or set
po_number to null if it has no explicit PO number. Never build a PO number from other text.

- supplier: everything after the @ in From, including all subdomains.
- original_date: the previously agreed ship date if stated. A newly stated date alone is
  not the original date. If a date is explicitly unchanged, use it in both date fields.
- confirmed_date: the exact committed date for quantity_confirmed. For a partial
  shipment, use the date of the first confirmed batch and ignore estimates for the
  remaining units. A date without a specific day is null. Use YYYY-MM-DD for exact dates.
  For an exact month/day without a year, use the email year, rolling into the next year
  if that date would already have passed. Never use the email date as a ship date by default.
- quantity_ordered: the quantity the buyer ordered. quantity_confirmed: the quantity the
  supplier can ship now or in the confirmed shipment. "All" or "quantity unchanged" means
  the full ordered quantity if known. Use 0 when the supplier cannot ship any units.
- unit_price: the current per-unit price. When a price changes, use the new price, not the
  old one or the total. Use an ISO currency code when stated or unambiguous.
- status: choose the first that applies: out_of_stock (cannot supply any), partial (can
  supply only some), delayed (ships later or explicitly postponed), price_change (new unit
  price), confirmed (the shipment is confirmed, even if earlier), pending (still awaiting
  confirmation). An earlier date is not a delay.
- change_type: the main update: quantity_change for shortages including zero units,
  date_change for a moved ship date, price_change for a new price, cancellation only when
  the order is explicitly cancelled, none for unchanged or pending terms, or other.
- notes: a short reason in English, or an empty string. confidence: a number from 0 to 1.
Use null for any unsupported dates, quantities, prices, or currency.

Example: "Production is still being scheduled for the 120 units you ordered." This is
one pending order with po_number null, quantity_ordered 120, and quantity_confirmed null."""

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
    options = {}
    if os.getenv("LLM_DISABLE_THINKING") == "1":
        options["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    resp = _get_client().chat.completions.create(
        model=model_name(),
        temperature=0,
        response_format=fmt,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": _user_message(msg)}],
        **options,
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
