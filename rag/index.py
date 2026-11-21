"""Vector index over the stored supplier emails and the buyer playbook.

Vectors live in two tables of the same SQLite database (data/po.sqlite):
    rag_chunks   one row per email chunk: sender, date, subject, text, vector
    rag_rules    one vector per playbook rule

The index updates itself: every search first embeds emails that are new or changed and
drops chunks of emails that no longer exist, so the inbox sync needs no extra call.
Changing EMBED_MODEL or EMBED_BASE_URL re-embeds everything.

Usage:
    python rag/index.py build
    python rag/index.py search "late shipment" --supplier sales@x.example.com --po PO-1001
    python rag/index.py playbook "supplier raised the price" --kind price_change
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.playbook import PlaybookRule, load_playbook, rules_for  # noqa: E402
from rag.embed import Embedder, get_embedder  # noqa: E402

# About 500 tokens. A Chinese character counts 2.5, so a chunk holds ~2000 English
# characters or ~800 Chinese characters.
MAX_CHUNK = 2000
SNIPPET_CHARS = 320
PO_MATCH_BONUS = 0.1  # added to the score when the query and the email name the same PO

SCHEMA = """
CREATE TABLE IF NOT EXISTS rag_chunks (
    email_id     TEXT NOT NULL,
    chunk_no     INTEGER NOT NULL,
    from_addr    TEXT,
    date         TEXT,
    subject      TEXT,
    text         TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    model        TEXT NOT NULL,
    vector       BLOB NOT NULL,
    PRIMARY KEY (email_id, chunk_no)
);
CREATE TABLE IF NOT EXISTS rag_rules (
    rule_id      TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    model        TEXT NOT NULL,
    vector       BLOB NOT NULL
);
"""

_CJK = re.compile(r"[　-〿一-鿿＀-￯]")
# Where a quoted earlier message starts (same markers as the extraction prompt).
_QUOTE_MARKERS = re.compile(
    r"^(on\b.+\bwrote:|-{2,}\s*(original message|原始邮件)\s*-{2,}|在.+写道[:：])$", re.IGNORECASE
)
_HEADER_FROM = re.compile(r"^(from|发件人)\s*[:：]", re.IGNORECASE)
_HEADER_NEXT = re.compile(r"^(sent|date|to|发送时间|时间|收件人)\s*[:：]", re.IGNORECASE)


# ------------------------------------------------------------------------ chunking


def _weight(text: str) -> int:
    return len(text) + int(1.5 * len(_CJK.findall(text)))


def strip_quoted(body: str) -> str:
    """Drop the quoted earlier messages of a reply, keep only what the sender wrote now."""
    lines = (body or "").splitlines()
    kept = []
    for i, line in enumerate(lines):
        s = line.strip()
        joined = f"{s} {lines[i + 1].strip()}" if i + 1 < len(lines) else s
        if _QUOTE_MARKERS.match(s) or (s.lower().startswith("on ") and _QUOTE_MARKERS.match(joined)):
            break
        if _HEADER_FROM.match(s) and any(_HEADER_NEXT.match(n.strip()) for n in lines[i + 1:i + 4]):
            break  # Outlook-style "From: / Sent:" block of the previous message
        if s.startswith(">"):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _hard_split(paragraph: str, limit: int) -> list[str]:
    if _weight(paragraph) <= limit:
        return [paragraph]
    pieces, current = [], ""
    for sentence in re.split(r"(?<=[.!?。！？；;])\s*", paragraph):
        if not sentence:
            continue
        if _weight(sentence) > limit:
            window = max(1, int(limit / 2.5))  # fits even if every character is Chinese
            parts = [sentence[i:i + window] for i in range(0, len(sentence), window)]
        else:
            parts = [sentence]
        for part in parts:
            candidate = f"{current} {part}".strip()
            if current and _weight(candidate) > limit:
                pieces.append(current)
                current = part
            else:
                current = candidate
    if current:
        pieces.append(current)
    return pieces


def split_text(text: str, limit: int = MAX_CHUNK) -> list[str]:
    """Pack paragraphs into pieces of at most `limit` weight; split long paragraphs."""
    pieces, current = [], ""
    for paragraph in re.split(r"\n\s*\n", text or ""):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for part in _hard_split(paragraph, limit):
            candidate = f"{current}\n\n{part}" if current else part
            if current and _weight(candidate) > limit:
                pieces.append(current)
                current = part
            else:
                current = candidate
    if current:
        pieces.append(current)
    return pieces


def chunk_email(email: dict) -> list[str]:
    """Texts to embed for one stored email: the new body, then each attachment.

    Every chunk starts with From / Date / Subject, so a chunk alone says which supplier
    and which message it came from.
    """
    header = (
        f"From: {email.get('from_addr', '')}\n"
        f"Date: {(email.get('date') or '')[:10]}\n"
        f"Subject: {email.get('subject', '')}"
    )
    budget = max(400, MAX_CHUNK - _weight(header) - 2)
    chunks = [f"{header}\n\n{p}" for p in split_text(strip_quoted(email.get("body_text", "")), budget)]
    for attachment in email.get("attachments") or []:
        text = (attachment.get("text") or "").strip()
        if not text:
            continue
        head = f"{header}\nAttachment: {attachment.get('filename', '')}"
        budget = max(400, MAX_CHUNK - _weight(head) - 2)
        chunks += [f"{head}\n\n{p}" for p in split_text(text, budget)]
    return chunks or [header]


# --------------------------------------------------------------------- indexing


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _stored_emails(conn: sqlite3.Connection) -> dict[str, dict]:
    import run_pipeline  # the same source the API uses: email_messages + legacy JSON

    return run_pipeline.stored_emails(conn)


def about_tracked_orders(conn: sqlite3.Connection) -> Callable[[dict], bool]:
    """Whether a stored email is about the buyer's orders.

    True when it comes from a supplier address in the PO list or mentions a tracked PO.
    Everything else (newsletters, personal mail that reached the inbox) is never indexed,
    so it is never sent to the embedding service. With an empty PO list nothing is.
    """
    orders = _known_orders(conn)
    pattern = _po_pattern(o[0] for o in orders)
    senders = {(o[2] or "").lower() for o in orders if o[2]}

    def check(email: dict) -> bool:
        if (email.get("from_addr") or "").lower() in senders:
            return True
        text = " ".join([email.get("subject") or "", email.get("body_text") or "",
                         *((a.get("text") or "") for a in email.get("attachments") or [])])
        return bool(_mentions(text, pattern))

    return check


def ensure_index(
    conn: sqlite3.Connection,
    *,
    emails: dict[str, dict] | None = None,
    embed: Embedder | None = None,
) -> dict:
    """Embed new or changed chunks of emails about tracked orders; drop chunks of the rest.

    Only emails that pass `about_tracked_orders` are indexed. Returns counts:
    {"embedded": ..., "removed": ..., "chunks": ...}.
    """
    conn.executescript(SCHEMA)
    embed = embed or get_embedder()
    if emails is None:
        emails = _stored_emails(conn)
    relevant = about_tracked_orders(conn)
    wanted: dict[tuple[str, int], tuple[str, str, dict]] = {}
    for email_id, email in emails.items():
        if not relevant(email):
            continue
        for no, text in enumerate(chunk_email(email)):
            wanted[(email_id, no)] = (text, _hash(text), email)
    have = {
        (row[0], row[1]): (row[2], row[3])
        for row in conn.execute("SELECT email_id, chunk_no, content_hash, model FROM rag_chunks")
    }
    outdated = {
        key for key, (digest, model) in have.items()
        if key not in wanted or wanted[key][1] != digest or model != embed.signature
    }
    todo = [key for key in wanted if key not in have or key in outdated]
    vectors = embed([wanted[key][0] for key in todo]) if todo else None  # network first, then write
    # Compare under the write lock: another request may have indexed a newer snapshot.
    with conn:
        if todo or outdated:
            conn.execute("BEGIN IMMEDIATE")
            current = {
                (r[0], r[1]): (r[2], r[3])
                for r in conn.execute("SELECT email_id, chunk_no, content_hash, model FROM rag_chunks")
            }
        else:
            current = have
        conn.executemany(
            "DELETE FROM rag_chunks WHERE email_id = ? AND chunk_no = ?", [key for key in outdated if current.get(key) == have[key]]
        )
        conn.executemany(
            "INSERT OR REPLACE INTO rag_chunks (email_id, chunk_no, from_addr, date, subject, text, "
            "content_hash, model, vector) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    key[0], key[1],
                    (wanted[key][2].get("from_addr") or "").lower(),
                    wanted[key][2].get("date") or "",
                    wanted[key][2].get("subject") or "",
                    wanted[key][0], wanted[key][1], embed.signature,
                    np.asarray(vectors[i], dtype=np.float32).tobytes(),
                )
                for i, key in enumerate(todo) if current.get(key) == have.get(key)
            ],
        )
    return {
        "embedded": len(todo),
        "removed": sum(1 for key in outdated if key not in wanted),
        "chunks": len(wanted),
    }


# ----------------------------------------------------------- orders and suppliers


def _po_key(po_number: str) -> str:
    return re.sub(r"\s+", "", po_number).upper()


def _known_orders(conn: sqlite3.Connection) -> list[sqlite3.Row | tuple]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'purchase_orders'"
    ).fetchone()
    if not exists:
        return []
    return conn.execute(
        "SELECT po_number, supplier, supplier_email FROM purchase_orders"
    ).fetchall()


def _po_pattern(po_numbers: Iterable[str]) -> re.Pattern | None:
    numbers = sorted({p for p in po_numbers if p}, key=len, reverse=True)
    if not numbers:
        return None
    alternatives = "|".join(re.escape(p) for p in numbers)
    # A reference to PO-1001 is not a mention of PO-100 (same rule as rules.py).
    return re.compile(rf"(?<![A-Za-z0-9_-])(?:{alternatives})(?![A-Za-z0-9_-])", re.IGNORECASE)


def _mentions(text: str, pattern: re.Pattern | None) -> set[str]:
    return {_po_key(m) for m in pattern.findall(text)} if pattern else set()


def email_text(email: dict) -> str:
    """Subject, body and attachment text of a stored email, for PO-number matching."""
    return " ".join([email.get("subject") or "", email.get("body_text") or "",
                     *((a.get("text") or "") for a in email.get("attachments") or [])])


def mentions_po(email: dict, po_number: str) -> bool:
    """Whether an email names this exact PO (PO-1001 is not PO-100)."""
    return _po_key(po_number) in _mentions(email_text(email), _po_pattern([po_number]))


def company_name(supplier: str, supplier_email: str) -> str:
    """The supplier's company name, or "" when only a domain or an address is stored.

    The current PO import stores the email domain as the supplier.
    """
    name = (supplier or "").strip()
    domain = (supplier_email or "").rpartition("@")[2].lower()
    if not name or "@" in name or name.lower() == domain or (" " not in name and "." in name):
        return ""
    return name


def order_scope(conn: sqlite3.Connection, po_number: str) -> tuple[set[str], set[str]]:
    """Sender addresses and PO numbers that surely belong to this order's supplier.

    A supplier is its company name in the PO list, or its email address when only a domain
    is stored; orders with the same identity belong to the same supplier. Its address
    counts only when no other supplier uses it (one test account playing several
    suppliers); otherwise only mentions of the supplier's own POs count.
    """
    orders = _known_orders(conn)

    def identity(o) -> str:
        return company_name(o[1] or "", o[2] or "").lower() or (o[2] or "").lower() or _po_key(o[0])

    target = next((o for o in orders if _po_key(o[0]) == _po_key(po_number)), None)
    if target is None:
        return set(), {_po_key(po_number)}
    address = (target[2] or "").lower()
    if not company_name(target[1], address) and sum((o[2] or "").lower() == address for o in orders) > 1:
        # The legacy importer keeps only the domain. A reused address cannot identify a company.
        return set(), {_po_key(target[0])}
    key = identity(target)
    po_numbers = {_po_key(o[0]) for o in orders if identity(o) == key}
    address = (target[2] or "").lower()
    users = {identity(o) for o in orders if (o[2] or "").lower() == address}
    return ({address} if address and users == {key} else set()), po_numbers


class AmbiguousSupplier(ValueError):
    """More than one supplier could own the requested history."""


def supplier_filter(
    conn: sqlite3.Connection, supplier: str
) -> Callable[[str, set[str]], bool]:
    """Decide whether an email belongs to a supplier given by address, domain or name.

    An email belongs to the supplier if it comes from the supplier's address in the PO
    list or mentions one of the supplier's POs. An address shared by several suppliers
    (for example one test account playing every supplier) only counts through the POs.
    """
    value = supplier.strip().lower()
    orders = _known_orders(conn)

    matched = [o for o in orders if value == (o[1] or "").lower()]
    if not matched:
        matched = [o for o in orders if value == (o[2] or "").lower()
                   or (o[2] or "").lower().endswith("@" + value)]
    if not matched:
        matched = [o for o in orders if value and value in (o[1] or "").lower()]
    if len({(o[1] or "").lower() for o in matched}) > 1:
        raise AmbiguousSupplier("Multiple suppliers match. Specify a company name or search by PO number.")
    if len(matched) > 1 and any(not company_name(o[1], o[2]) for o in matched):
        raise AmbiguousSupplier("Supplier identity is ambiguous. Search by PO number.")
    po_numbers = {_po_key(o[0]) for o in matched}
    owners: dict[str, set[str]] = {}
    for o in orders:
        owners.setdefault((o[2] or "").lower(), set()).add((o[1] or o[2] or "").lower())
    addresses = {
        (o[2] or "").lower() for o in matched if len(owners.get((o[2] or "").lower(), ())) == 1
    }
    if not matched:
        # Not in the PO list: fall back to the sender's address or domain.
        return lambda sender, _pos: sender == value or ("@" not in value and sender.endswith("@" + value))
    return lambda sender, pos: sender in addresses or bool(pos & po_numbers)


# ---------------------------------------------------------------------- search


def _vectors(blobs: list[bytes]) -> np.ndarray:
    return np.vstack([np.frombuffer(b, dtype=np.float32) for b in blobs])


def _snippet(chunk: str) -> str:
    body = chunk.split("\n\n", 1)[1] if "\n\n" in chunk else chunk
    body = re.sub(r"\s+", " ", body).strip()
    return body if len(body) <= SNIPPET_CHARS else body[:SNIPPET_CHARS].rstrip() + "…"


def search_emails(
    conn: sqlite3.Connection,
    query: str,
    *,
    supplier: str | None = None,
    scope: tuple[set[str], set[str]] | None = None,
    po_number: str | None = None,
    k: int = 5,
    exclude: Iterable[str] = (),
    embed: Embedder | None = None,
) -> list[dict]:
    """The emails most similar to `query`, best chunk per email, highest score first.

    supplier:  address, domain or name; keeps that supplier's emails (see supplier_filter)
    scope:     (sender addresses, PO numbers) from order_scope(); keeps exactly that supplier's
               emails and takes precedence over `supplier`
    po_number: keeps only emails that mention this PO
    exclude:   email ids to leave out (for example the ones a draft already quotes)
    """
    embed = embed or get_embedder()
    ensure_index(conn, embed=embed)
    rows = conn.execute(
        "SELECT email_id, from_addr, date, subject, text, vector FROM rag_chunks WHERE model = ?",
        (embed.signature,),
    ).fetchall()
    if not rows:
        return []
    known = {o[0] for o in _known_orders(conn)}
    pattern = _po_pattern(known | ({po_number} if po_number else set()))
    target = _po_key(po_number) if po_number else None
    if scope is not None:
        senders, scope_pos = scope
        belongs = lambda sender, pos: sender in senders or bool(pos & scope_pos)  # noqa: E731
    else:
        belongs = supplier_filter(conn, supplier) if supplier else None
    skip = set(exclude)
    scores = _vectors([r[5] for r in rows]) @ embed([query])[0]
    query_pos = _mentions(query, pattern)
    best: dict[str, dict] = {}
    for row, score in zip(rows, scores):
        email_id, sender, date, subject, text = row[0], row[1] or "", row[2], row[3], row[4]
        if email_id in skip:
            continue
        pos = _mentions(text, pattern)
        if target and target not in pos:
            continue
        if belongs and not belongs(sender, pos):
            continue
        score = float(score) + (PO_MATCH_BONUS if query_pos & pos else 0.0)
        if email_id not in best or score > best[email_id]["score"]:
            best[email_id] = {
                "email_id": email_id,
                "date": date,
                "from": sender,
                "subject": subject,
                "po_numbers": sorted(pos),
                "snippet": _snippet(text),
                "score": round(score, 4),
            }
    return sorted(best.values(), key=lambda r: r["score"], reverse=True)[:k]


def _rule_text(rule: PlaybookRule) -> str:
    return f"{rule.title}\n{rule.text}\nApplies to: {', '.join(rule.kinds)}"


def _rule_vectors(
    conn: sqlite3.Connection, rules: list[PlaybookRule], embed: Embedder
) -> np.ndarray:
    conn.executescript(SCHEMA)
    have = {
        row[0]: (row[1], row[2], row[3])
        for row in conn.execute("SELECT rule_id, content_hash, model, vector FROM rag_rules")
    }
    todo = [
        r for r in rules
        if r.id not in have or have[r.id][0] != _hash(_rule_text(r)) or have[r.id][1] != embed.signature
    ]
    if todo:
        fresh = embed([_rule_text(r) for r in todo])
        with conn:
            conn.executemany(
                "INSERT OR REPLACE INTO rag_rules (rule_id, content_hash, model, vector) "
                "VALUES (?, ?, ?, ?)",
                [
                    (r.id, _hash(_rule_text(r)), embed.signature, np.asarray(v, np.float32).tobytes())
                    for r, v in zip(todo, fresh)
                ],
            )
        for r, v in zip(todo, fresh):
            have[r.id] = (None, embed.signature, np.asarray(v, np.float32).tobytes())
    return _vectors([have[r.id][2] for r in rules])


def search_playbook(
    conn: sqlite3.Connection,
    query: str,
    *,
    kind: str | None = None,
    k: int = 3,
    rules: list[PlaybookRule] | None = None,
    embed: Embedder | None = None,
) -> list[dict]:
    """The playbook rules most similar to `query`; with `kind`, only rules for that exception."""
    embed = embed or get_embedder()
    candidates = rules_for(kind, rules if rules is not None else load_playbook(conn))
    if not candidates:
        return []
    scores = _rule_vectors(conn, candidates, embed) @ embed([query])[0]
    ranked = sorted(zip(candidates, scores), key=lambda pair: float(pair[1]), reverse=True)
    return [{**rule.to_dict(), "score": round(float(score), 4)} for rule, score in ranked[:k]]


# -------------------------------------------------------------------------- CLI


def main() -> None:
    from dashboard.db import DB_PATH, connect

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build", help="embed new emails now")
    emails = sub.add_parser("search", help="search the stored emails")
    emails.add_argument("query")
    emails.add_argument("--supplier")
    emails.add_argument("--po")
    emails.add_argument("-k", type=int, default=5)
    rules = sub.add_parser("playbook", help="search the playbook rules")
    rules.add_argument("query")
    rules.add_argument("--kind")
    rules.add_argument("-k", type=int, default=3)
    args = parser.parse_args()

    conn = connect(DB_PATH)
    try:
        if args.command == "build":
            result = ensure_index(conn)
        elif args.command == "search":
            result = search_emails(conn, args.query, supplier=args.supplier, po_number=args.po, k=args.k)
        else:
            result = search_playbook(conn, args.query, kind=args.kind, k=args.k)
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
