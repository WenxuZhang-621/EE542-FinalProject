"""Verify the shared M2 fixture against import, storage and exception rules (no LLM)."""

import argparse
from datetime import date
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dashboard import db
from dashboard.ingest_result import save_extractions, upsert
from ingest.po_import import import_po_list
from rules import sync_exceptions
from schema import EmailMessage, POExtraction


def check(samples: Path):
    expected = json.loads((samples / "m2_expected.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as directory:
        conn = db.connect(str(Path(directory) / "check.sqlite"))
        try:
            first = import_po_list(samples / "po_list_40.csv", conn=conn)
            again = import_po_list(samples / "po_list_40.csv", conn=conn)
            messages = []
            for path in sorted((samples / "m2_inbox").glob("*.email.json")):
                message = EmailMessage.from_dict(
                    json.loads(path.read_text(encoding="utf-8"))
                )
                gold_path = path.with_name(
                    path.name.replace(".email.json", ".gold.json")
                )
                gold = [
                    POExtraction.from_dict(item)
                    for item in json.loads(gold_path.read_text(encoding="utf-8"))
                ]
                save_extractions(conn, message, gold)
                for extraction in gold:
                    upsert(conn, extraction)
                messages.append(message)
            found = sync_exceptions(
                conn, emails=messages, as_of=date.fromisoformat(expected["as_of"])
            )
            actual = sorted((item.po_number, item.kind) for item in found)
            want = sorted(
                (item["po_number"], item["kind"]) for item in expected["exceptions"]
            )
            suppliers = conn.execute(
                "SELECT count(DISTINCT supplier_email) FROM purchase_orders"
            ).fetchone()[0]
            passed = (
                first.added == 40
                and first.errors == 0
                and again.existing == 40
                and suppliers == 10
                and len(messages) == 10
                and actual == want
            )
            return {
                "passed": passed,
                "mode": "gold-fixture integration; no Gmail or LLM calls",
                "as_of": expected["as_of"],
                "imported": first.added,
                "duplicate_import_existing": again.existing,
                "suppliers": suppliers,
                "emails": len(messages),
                "exceptions": [{"po_number": po, "kind": kind} for po, kind in actual],
            }
        finally:
            conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=ROOT / "tests/samples")
    parser.add_argument("--out", type=Path, default=ROOT / "data/m2_check.json")
    args = parser.parse_args()
    result = check(args.samples)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
