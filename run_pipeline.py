"""Run the whole pipeline with one command: emails -> LLM extraction -> SQLite.

Usage:
    python run_pipeline.py --offline tests/samples --reset   # read a folder of *.email.json
    python run_pipeline.py --in data/emails.json             # output of ingest/fetch_emails.py
Then:
    streamlit run dashboard/app.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "extract", ROOT / "dashboard"):
    sys.path.insert(0, str(p))
from schema import EmailMessage  # noqa: E402
from extract import extract_timed  # noqa: E402
import db  # noqa: E402
from ingest_result import upsert  # noqa: E402

EMAILS_OUT = ROOT / "data" / "emails.json"
EXTRACTIONS_OUT = ROOT / "data" / "extractions.json"


def load_offline(folder: Path) -> list[EmailMessage]:
    return [EmailMessage.from_dict(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(folder.glob("*.email.json"))]


def load_json(path: Path) -> list[EmailMessage]:
    return [EmailMessage.from_dict(d) for d in json.loads(path.read_text(encoding="utf-8"))]


def run(msgs: list[EmailMessage], reset: bool = False, on_email=None) -> dict:
    """Extract every email (oldest first) and store the results. Returns a short summary."""
    msgs = sorted(msgs, key=lambda m: m.date)
    conn = db.connect()
    if reset:
        db.reset(conn)
    results, seconds = [], []
    for i, m in enumerate(msgs):
        if on_email:
            on_email(i, len(msgs), m)
        exts, sec = extract_timed(m)
        seconds.append(sec)
        for e in exts:
            results.append(e.to_dict())
            if e.po_number:
                upsert(conn, e)
        conn.commit()

    EMAILS_OUT.parent.mkdir(parents=True, exist_ok=True)
    # Keep the emails we processed so the dashboard can show the original text.
    known = {d["email_id"]: d for d in (json.loads(EMAILS_OUT.read_text(encoding="utf-8"))
                                        if EMAILS_OUT.exists() and not reset else [])}
    known.update({m.email_id: json.loads(m.to_json()) for m in msgs})
    EMAILS_OUT.write_text(json.dumps(list(known.values()), ensure_ascii=False, indent=2),
                          encoding="utf-8")
    EXTRACTIONS_OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"emails": len(msgs), "pos": len(results),
            "avg_seconds": sum(seconds) / max(len(seconds), 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--offline", type=Path, help="folder of *.email.json files")
    src.add_argument("--in", dest="inp", type=Path, help="JSON list of EmailMessage")
    ap.add_argument("--reset", action="store_true", help="empty the database first")
    args = ap.parse_args()

    msgs = load_offline(args.offline) if args.offline else load_json(args.inp)
    s = run(msgs, reset=args.reset,
            on_email=lambda i, n, m: print(f"[{i + 1}/{n}] {m.email_id}  {m.subject}"))
    print(f"done: {s['emails']} emails -> {s['pos']} PO updates, "
          f"avg {s['avg_seconds']:.1f}s per email")


if __name__ == "__main__":
    main()
