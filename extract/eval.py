"""Per-field accuracy of extract.py against gold answers in tests/samples/.

Each sample is a pair:  tests/samples/<name>.email.json  (EmailMessage)
                        tests/samples/<name>.gold.json   (list of POExtraction dicts)

Every run is appended to data/eval_runs.jsonl with a label (e.g. M1, M2-gpu), so the
dashboard can show how accuracy changes from one milestone to the next.

Usage:
    python extract/eval.py --label M1
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "extract"))
from schema import EmailMessage  # noqa: E402
from extract import extract_timed, model_name  # noqa: E402

FIELDS = ["po_number", "supplier", "status", "change_type", "original_date",
          "confirmed_date", "quantity_ordered", "quantity_confirmed"]
SAMPLES_DIR = ROOT / "tests" / "samples"
RUNS_PATH = ROOT / "data" / "eval_runs.jsonl"


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


def run_eval(label: str, samples_dir: Path = SAMPLES_DIR) -> dict:
    """Run extraction on every sample, score it, append the run to RUNS_PATH, return it."""
    hits = {f: 0 for f in FIELDS}
    total = missed = extra = 0
    seconds = []
    per_sample = []
    for p in sorted(samples_dir.glob("*.email.json")):
        gold = json.loads(p.with_suffix("").with_suffix(".gold.json").read_text(encoding="utf-8"))
        msg = EmailMessage.from_dict(json.loads(p.read_text(encoding="utf-8")))
        exts, sec = extract_timed(msg)
        seconds.append(sec)
        pred = [e.to_dict() for e in exts]
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
        per_sample.append({"sample": p.name.removesuffix(".email.json"), "email_id": msg.email_id,
                           "gold": gold, "pred": pred, "seconds": round(sec, 2)})

    field_acc = {f: hits[f] / max(total, 1) for f in FIELDS}
    run = {
        "label": label,
        "time": datetime.now().isoformat(timespec="seconds"),
        "model": model_name(),
        "n_emails": len(per_sample),
        "n_gold_pos": total,
        "missed": missed,
        "extra": extra,
        "overall": sum(hits.values()) / max(total * len(FIELDS), 1),
        "field_accuracy": field_acc,
        "avg_seconds": sum(seconds) / max(len(seconds), 1),
        "samples": per_sample,
    }
    RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RUNS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(run, ensure_ascii=False) + "\n")
    return run


def load_runs() -> list[dict]:
    if not RUNS_PATH.exists():
        return []
    return [json.loads(line) for line in RUNS_PATH.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="dev", help="run name shown on the dashboard, e.g. M1")
    args = ap.parse_args()

    run = run_eval(args.label)
    print(f"model={run['model']}  emails={run['n_emails']}  avg {run['avg_seconds']:.1f}s/email")
    print(f"{'field':20s} accuracy  (gold POs={run['n_gold_pos']}, missed={run['missed']}, "
          f"extra={run['extra']})")
    for f, acc in run["field_accuracy"].items():
        print(f"{f:20s} {acc:.0%}")
    print(f"{'overall':20s} {run['overall']:.0%}")


if __name__ == "__main__":
    main()
