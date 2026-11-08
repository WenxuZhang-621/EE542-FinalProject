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

SYSTEM_PROMPT = """You are a procurement assistant. Given a supplier email (and attachment text),
extract purchase-order status information. Dates must be ISO 8601. If the email references
multiple POs, return one object per PO. If no PO is referenced, set po_number to null.
Set confidence between 0 and 1."""


def extract_one(msg: EmailMessage) -> list[POExtraction]:
    # TODO(P2): call LLM with SYSTEM_PROMPT + msg, structured output per PO_EXTRACTION_JSON_SCHEMA
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
