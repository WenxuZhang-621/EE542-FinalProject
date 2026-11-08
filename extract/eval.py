"""Per-field accuracy of extract.py against gold answers in tests/samples/.

Each sample is a pair:  tests/samples/<name>.email.json  (EmailMessage)
                        tests/samples/<name>.gold.json   (list of POExtraction dicts)

Usage:
    python extract/eval.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schema import EmailMessage  # noqa: E402
from extract import extract_one  # noqa: E402

FIELDS = ["po_number", "supplier", "status", "change_type", "original_date",
          "confirmed_date", "quantity_ordered", "quantity_confirmed"]


def match(gold: list[dict], pred: list[dict]) -> tuple[list[tuple[dict, dict | None]], int]:
    """Pair each gold PO with the predicted PO that has the same po_number.

    Matching by PO number (not by list position) means a PO the model missed counts as
    wrong on every field, and the model's order of answers does not matter.
    Returns the pairs and the number of extra predicted POs that match no gold PO.
    """
    remaining = list(pred)
    pairs = []
    for g in gold:
        hit = next((p for p in remaining if p.get("po_number") == g.get("po_number")), None)
        if hit is not None:
            remaining.remove(hit)
        pairs.append((g, hit))
    return pairs, len(remaining)


def main() -> None:
    samples = sorted(Path("tests/samples").glob("*.email.json"))
    hits = {f: 0 for f in FIELDS}
    total = missed = extra = 0
    for p in samples:
        gold = json.loads(p.with_suffix("").with_suffix(".gold.json").read_text(encoding="utf-8"))
        msg = EmailMessage.from_dict(json.loads(p.read_text(encoding="utf-8")))
        pred = [e.to_dict() for e in extract_one(msg)]
        pairs, n_extra = match(gold, pred)
        extra += n_extra
        for g, pr in pairs:
            total += 1
            if pr is None:
                missed += 1
                continue
            for f in FIELDS:
                if g.get(f) == pr.get(f):
                    hits[f] += 1
    print(f"{'field':20s} accuracy  (gold POs={total}, missed={missed}, extra={extra})")
    for f in FIELDS:
        print(f"{f:20s} {hits[f] / max(total, 1):.0%}")


if __name__ == "__main__":
    main()
