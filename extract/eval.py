"""Per-field accuracy of extract.py against gold answers in tests/samples/.

Each sample is a pair:  tests/samples/<name>.email.json  (EmailMessage)
                        tests/samples/<name>.gold.json   (list of POExtraction dicts)

Usage:
    python extract/eval.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schema import EmailMessage  # noqa: E402
from extract import extract_one  # noqa: E402

FIELDS = ["po_number", "supplier", "status", "change_type", "original_date",
          "confirmed_date", "quantity_ordered", "quantity_confirmed"]


def main() -> None:
    samples = sorted(Path("tests/samples").glob("*.email.json"))
    hits = {f: 0 for f in FIELDS}
    total = 0
    for p in samples:
        gold = json.loads(p.with_suffix("").with_suffix(".gold.json").read_text(encoding="utf-8"))
        msg = EmailMessage.from_dict(json.loads(p.read_text(encoding="utf-8")))
        pred = [e.to_dict() for e in extract_one(msg)]
        for g, pr in zip(gold, pred):
            total += 1
            for f in FIELDS:
                if g.get(f) == pr.get(f):
                    hits[f] += 1
    print(f"{'field':20s} accuracy  (n={total})")
    for f in FIELDS:
        print(f"{f:20s} {hits[f] / max(total, 1):.0%}")


if __name__ == "__main__":
    main()
