"""Run LLM extraction over EmailMessage JSON and emit POExtraction JSON.

Usage:
    python extract/extract.py --in data/emails.json --out data/extractions.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schema import EmailMessage, POExtraction, PO_EXTRACTION_JSON_SCHEMA  # noqa: E402

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
# schema.py stays unchanged; this only wraps its per-PO schema.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"orders": {"type": "array", "items": PO_EXTRACTION_JSON_SCHEMA}},
    "required": ["orders"],
    "additionalProperties": False,
}


def extract_one(msg: EmailMessage) -> list[POExtraction]:
    # TODO(P2): call LLM with SYSTEM_PROMPT + msg, structured output per RESPONSE_SCHEMA;
    #           build each POExtraction from response["orders"] with source_email_id=msg.email_id
    raise NotImplementedError("P2: implement LLM extraction")


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
