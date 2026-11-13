import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "extract"))
from eval import FIELDS, rescore, score  # noqa: E402
from extract import SYSTEM_PROMPT  # noqa: E402


def po(number, **fields):
    return {"po_number": number, **{f: None for f in FIELDS[1:]}, **fields}


def test_score_counts_missed_and_extra_orders():
    samples = [
        {"sample": "001_a", "gold": [po("PO-1", unit_price=2.4)], "pred": [po("PO-1", unit_price=2.5)]},
        {"sample": "007_b", "gold": [po("PO-2")], "pred": [po("PO-9")]},
    ]
    result = score(samples)
    assert (result["n_gold_pos"], result["missed"], result["extra"]) == (2, 1, 1)
    assert result["field_accuracy"]["po_number"] == 0.5
    assert result["field_accuracy"]["unit_price"] == 0.0  # one wrong, one missed
    assert result["overall"] == (len(FIELDS) - 1) / (2 * len(FIELDS))


def test_rescore_uses_current_gold_and_reports_the_m1_subset(tmp_path):
    (tmp_path / "001_a.gold.json").write_text(json.dumps([po("PO-1")]))
    old = {"label": "old", "overall": 0.0, "samples": [
        {"sample": "001_a", "gold": [po("PO-1", status="delayed")], "pred": [po("PO-1")]},
        {"sample": "007_b", "gold": [po("PO-2")], "pred": []},
    ]}
    run = rescore(old, tmp_path)
    assert run["m1_overall"] == 1.0
    assert run["overall"] == 0.5


def test_prompt_names_json_for_json_object_mode():
    # OpenAI-compatible APIs reject response_format=json_object unless a message says "JSON".
    assert "json" in SYSTEM_PROMPT.lower()
