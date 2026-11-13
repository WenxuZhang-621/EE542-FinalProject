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
          "confirmed_date", "quantity_ordered", "quantity_confirmed", "unit_price", "currency"]
M1_SAMPLE_COUNT = 6  # samples 001-006 were the whole M1 test set
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


def score(samples: list[dict]) -> dict:
    """Score samples shaped like {"gold": [...], "pred": [...]} on every field in FIELDS."""
    hits = {f: 0 for f in FIELDS}
    total = missed = extra = 0
    for s in samples:
        pairs, n_extra = match(s["gold"], s["pred"])
        extra += n_extra
        for g, pr in pairs:
            total += 1
            if pr is None:
                missed += 1
                continue
            for f in FIELDS:
                if g.get(f) == pr.get(f):
                    hits[f] += 1
    return {
        "n_emails": len(samples),
        "n_gold_pos": total,
        "missed": missed,
        "extra": extra,
        "overall": sum(hits.values()) / max(total * len(FIELDS), 1),
        "field_accuracy": {f: hits[f] / max(total, 1) for f in FIELDS},
    }


def _m1_overall(samples: list[dict]) -> float | None:
    """Accuracy on the original M1 emails only, so M1 and later runs compare like for like."""
    m1 = [s for s in samples
          if s["sample"][:3].isdigit() and int(s["sample"][:3]) <= M1_SAMPLE_COUNT]
    return score(m1)["overall"] if m1 else None


def rescore(run: dict, samples_dir: Path = SAMPLES_DIR) -> dict:
    """Score a stored run again with the current FIELDS and gold answers.

    Older runs were scored on fewer fields, and gold answers get corrected over time.
    The stored predictions are enough to put every run on the same scale without
    calling the model again.
    """
    samples = []
    for s in run["samples"]:
        gold_path = samples_dir / f"{s['sample']}.gold.json"
        gold = json.loads(gold_path.read_text(encoding="utf-8")) if gold_path.exists() else s["gold"]
        samples.append({**s, "gold": gold})
    return {**run, **score(samples), "m1_overall": _m1_overall(samples), "samples": samples}


def run_eval(label: str, samples_dir: Path = SAMPLES_DIR) -> dict:
    """Run extraction on every sample, score it, append the run to RUNS_PATH, return it."""
    seconds = []
    per_sample = []
    for p in sorted(samples_dir.glob("*.email.json")):
        gold = json.loads(p.with_suffix("").with_suffix(".gold.json").read_text(encoding="utf-8"))
        msg = EmailMessage.from_dict(json.loads(p.read_text(encoding="utf-8")))
        exts, sec = extract_timed(msg)
        seconds.append(sec)
        per_sample.append({"sample": p.name.removesuffix(".email.json"), "email_id": msg.email_id,
                           "gold": gold, "pred": [e.to_dict() for e in exts],
                           "seconds": round(sec, 2)})

    run = {
        "label": label,
        "time": datetime.now().isoformat(timespec="seconds"),
        "model": model_name(),
        **score(per_sample),
        "m1_overall": _m1_overall(per_sample),
        "avg_seconds": sum(seconds) / max(len(seconds), 1),
        "samples": per_sample,
    }
    RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RUNS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(run, ensure_ascii=False) + "\n")
    return run


def load_runs() -> list[dict]:
    """Every stored run, scored again so runs from different milestones are comparable."""
    if not RUNS_PATH.exists():
        return []
    return [rescore(json.loads(line))
            for line in RUNS_PATH.read_text(encoding="utf-8").splitlines() if line]


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
    if run["m1_overall"] is not None and run["n_emails"] > M1_SAMPLE_COUNT:
        print(f"{'on the M1 emails':20s} {run['m1_overall']:.0%}  (samples 001-006 only)")


if __name__ == "__main__":
    main()
