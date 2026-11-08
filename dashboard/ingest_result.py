"""Upsert POExtraction JSON into SQLite and record change events.

Usage:
    python dashboard/ingest_result.py --in data/extractions.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schema import POExtraction  # noqa: E402
from db import connect  # noqa: E402


def upsert(conn, ext: POExtraction) -> None:
    # TODO(P3): upsert into purchase_orders; if confirmed_date moved later than the stored
    #           original_date, insert a 'date_change' event with old/new values.
    raise NotImplementedError("P3: implement upsert + event logging")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/extractions.json")
    args = ap.parse_args()

    with open(args.inp, encoding="utf-8") as f:
        exts = [POExtraction.from_dict(d) for d in json.load(f)]

    conn = connect()
    for e in exts:
        if e.po_number:
            upsert(conn, e)
    conn.commit()
    print(f"ingested {len(exts)} extractions")


if __name__ == "__main__":
    main()
