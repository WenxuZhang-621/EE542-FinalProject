"""Run the whole pipeline with one command: emails -> LLM extraction -> SQLite -> rules.

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
from contextlib import closing
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "extract", ROOT / "dashboard"):
    sys.path.insert(0, str(p))
from schema import EmailMessage  # noqa: E402
from extract import extract_timed  # noqa: E402
import db  # noqa: E402
from ingest_result import save_extractions, upsert  # noqa: E402
from rules import sync_exceptions  # noqa: E402

EMAILS_OUT = ROOT / "data" / "emails.json"
EXTRACTIONS_OUT = ROOT / "data" / "extractions.json"


def load_offline(folder: Path) -> list[EmailMessage]:
    return [EmailMessage.from_dict(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(folder.glob("*.email.json"))]


def load_json(path: Path) -> list[EmailMessage]:
    return [EmailMessage.from_dict(d) for d in json.loads(path.read_text(encoding="utf-8"))]


def stored_emails(conn) -> dict[str, dict]:
    """Read legacy JSON and the transactionally stored messages from newer syncs."""
    known = {d["email_id"]: d for d in (
        json.loads(EMAILS_OUT.read_text(encoding="utf-8")) if EMAILS_OUT.exists() else []
    )}
    known.update({r["email_id"]: json.loads(r["data"])
                  for r in conn.execute("SELECT email_id, data FROM email_messages")})
    return known


def run(msgs: list[EmailMessage], reset: bool = False, on_email=None,
        *, extractor=None, skip_processed: bool = False) -> dict:
    """Extract every email (oldest first) and store the results. Returns a short summary."""
    msgs = sorted(msgs, key=lambda m: m.date)
    extract = extractor or extract_timed
    results, seconds = [], []
    with closing(db.connect()) as conn:
        if reset:
            db.reset(conn)
        known = {} if reset else stored_emails(conn)
        for i, m in enumerate(msgs):
            if skip_processed and m.email_id in known:
                continue
            if on_email:
                on_email(i, len(msgs), m)
            exts, sec = extract(m)
            payload = json.loads(m.to_json())
            with conn:
                # Check again under a write lock for overlapping syncs in other workers.
                conn.execute("BEGIN IMMEDIATE")
                exists = conn.execute(
                    "SELECT 1 FROM email_messages WHERE email_id = ?", (m.email_id,)
                ).fetchone()
                if skip_processed and exists:
                    continue
                save_extractions(conn, m, exts)
                for e in exts:
                    if e.po_number:
                        newer = conn.execute(
                            "SELECT 1 FROM extractions WHERE po_number = ? "
                            "AND julianday(email_date) > julianday(?) LIMIT 1",
                            (e.po_number, m.date),
                        ).fetchone()
                        # Backfilled mail stays available as evidence, but must not
                        # roll the current PO or its change events back in time.
                        if not newer:
                            upsert(conn, e)
                conn.execute(
                    "INSERT OR REPLACE INTO email_messages (email_id, data) VALUES (?, ?)",
                    (m.email_id, json.dumps(payload, ensure_ascii=False)),
                )
                current = stored_emails(conn) if not reset else {**known, m.email_id: payload}
                sync_exceptions(conn, emails=[EmailMessage.from_dict(d) for d in current.values()])
            known[m.email_id] = payload
            results.extend(e.to_dict() for e in exts)
            seconds.append(sec)

        # The database keeps successful messages even if a later extraction fails.
        known.update({r["email_id"]: json.loads(r["data"])
                      for r in conn.execute("SELECT email_id, data FROM email_messages")})
        found = sync_exceptions(conn, emails=[EmailMessage.from_dict(d) for d in known.values()])
        conn.commit()

    EMAILS_OUT.parent.mkdir(parents=True, exist_ok=True)
    for path, data in ((EMAILS_OUT, list(known.values())), (EXTRACTIONS_OUT, results)):
        with NamedTemporaryFile(mode="w", dir=path.parent, suffix=".tmp",
                                encoding="utf-8", delete=False) as output:
            json.dump(data, output, ensure_ascii=False, indent=2)
            temporary = Path(output.name)
        temporary.replace(path)
    return {"emails": len(seconds), "pos": len(results), "exceptions": len(found),
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
          f"{s['exceptions']} open exceptions, "
          f"avg {s['avg_seconds']:.1f}s per email")


if __name__ == "__main__":
    main()
