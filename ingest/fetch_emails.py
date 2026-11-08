"""Fetch supplier emails from Gmail and emit a list of EmailMessage as JSON.

Usage:
    python ingest/fetch_emails.py --since 7d --out data/emails.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schema import EmailMessage, Attachment  # noqa: E402


def fetch(since: str) -> list[EmailMessage]:
    # TODO(P1): Gmail OAuth + list/get messages + MIME parse + attachment text
    raise NotImplementedError("P1: implement Gmail fetch")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="7d", help="e.g. 7d, 24h")
    ap.add_argument("--out", default="data/emails.json")
    args = ap.parse_args()

    msgs = fetch(args.since)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump([json.loads(m.to_json()) for m in msgs], f, ensure_ascii=False, indent=2)
    print(f"wrote {len(msgs)} emails to {args.out}")


if __name__ == "__main__":
    main()
