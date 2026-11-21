"""rag/: chunking, the self-updating index and search, with offline word-hash vectors."""

import json

import pytest

from dashboard import db
from rag.embed import HashingEmbedder
from rag.index import (
    MAX_CHUNK,
    _weight,
    chunk_email,
    ensure_index,
    search_emails,
    search_playbook,
    split_text,
    strip_quoted,
)


class CountingEmbedder(HashingEmbedder):
    """Word-hash vectors that also count how many texts were embedded."""

    def __init__(self, signature=None):
        super().__init__()
        if signature:
            self.signature = signature
        self.calls = 0

    def __call__(self, texts):
        self.calls += len(texts)
        return super().__call__(texts)


def email(email_id, sender, subject, body, date="2026-11-10T09:00:00+00:00", attachments=()):
    return {
        "email_id": email_id,
        "from_addr": sender,
        "subject": subject,
        "date": date,
        "body_text": body,
        "attachments": [{"filename": f, "text": t, "mime_type": ""} for f, t in attachments],
        "thread_id": "",
    }


INBOX = {
    "e1": email("e1", "sales@alder.example.com", "PO-1001 delay",
                "The ship date for PO-1001 moves from Dec 1 to Dec 15 because of a factory holiday."),
    "e2": email("e2", "sales@alder.example.com", "PO-0950 delayed again",
                "Sorry, PO-0950 is late again. The resin shipment did not arrive.", date="2026-09-02"),
    "e3": email("e3", "export@birch.example.com", "Price update",
                "From January our unit price for PO-1002 rises from 2.40 to 2.65 USD."),
    "e4": email("e4", "news@marketing.example.com", "Newsletter", "Our autumn catalogue is out."),
}


@pytest.fixture
def conn(tmp_path, monkeypatch):
    import run_pipeline

    monkeypatch.setattr(run_pipeline, "EMAILS_OUT", tmp_path / "missing.json")
    c = db.connect(str(tmp_path / "po.sqlite"))
    for e in INBOX.values():
        c.execute("INSERT INTO email_messages (email_id, data) VALUES (?, ?)", (e["email_id"], json.dumps(e)))
    c.executemany(
        "INSERT INTO purchase_orders (po_number, supplier, status, supplier_email) VALUES (?, ?, 'pending', ?)",
        [
            ("PO-1001", "Alder Components", "sales@alder.example.com"),
            ("PO-0950", "Alder Components", "sales@alder.example.com"),
            ("PO-1002", "Birch Fasteners", "export@birch.example.com"),
        ],
    )
    c.commit()
    yield c
    c.close()


# ------------------------------------------------------------------ chunking


def test_strip_quoted_drops_earlier_messages():
    body = "All 900 cartons ship Nov 25.\n\nOn Nov 10, 2026, I wrote:\n> PO-2026-0452 may slip."
    assert strip_quoted(body) == "All 900 cartons ship Nov 25."
    zh = "确认按原计划发货。\n\n-----原始邮件-----\n可能推迟到 12 月 7 日。"
    assert strip_quoted(zh) == "确认按原计划发货。"
    outlook = "New date is Dec 3.\nFrom: Buyer\nSent: Monday\nSubject: PO-1\nold text"
    assert strip_quoted(outlook) == "New date is Dec 3."
    assert strip_quoted("> only quoted\nkept") == "kept"


def test_gmail_two_line_quote_header():
    body = "Confirmed.\n\nOn Mon, Nov 10, 2026 at 9:00 AM Alice <\nalice@example.com> wrote:\n> old"
    assert strip_quoted(body).startswith("Confirmed.")
    assert "old" not in strip_quoted(body)


def test_long_text_is_split_within_the_limit():
    english = "\n\n".join("Paragraph %d. " % i + "word " * 150 for i in range(10))
    chinese = "供应商说交期推迟。" * 400  # one long paragraph without breaks
    for text in (english, chinese):
        pieces = split_text(text)
        assert len(pieces) > 1
        assert all(_weight(p) <= MAX_CHUNK for p in pieces)


def test_chunks_carry_the_header_and_attachments():
    e = email("x", "a@b.example.com", "PO-1 update", "See attached.",
              attachments=[("update.xlsx", "PO-1 | 2026-12-02"), ("empty.pdf", "")])
    chunks = chunk_email(e)
    assert len(chunks) == 2  # body + the attachment with text
    assert chunks[0].startswith("From: a@b.example.com\nDate: 2026-11-10\nSubject: PO-1 update")
    assert "Attachment: update.xlsx" in chunks[1]


# ------------------------------------------------------------------- indexing


def test_index_embeds_only_new_or_changed_emails(conn):
    embed = CountingEmbedder()
    first = ensure_index(conn, embed=embed)
    assert first == {"embedded": 3, "removed": 0, "chunks": 3}  # e4 (newsletter) is not about an order
    assert ensure_index(conn, embed=embed)["embedded"] == 0

    new = email("e5", "sales@alder.example.com", "PO-1001 update", "Now Dec 12.")
    conn.execute("INSERT INTO email_messages (email_id, data) VALUES (?, ?)", ("e5", json.dumps(new)))
    conn.execute("DELETE FROM email_messages WHERE email_id = 'e3'")
    conn.commit()
    assert ensure_index(conn, embed=embed) == {"embedded": 1, "removed": 1, "chunks": 3}


def test_only_mail_about_tracked_orders_is_embedded(conn):
    embed = CountingEmbedder()
    ensure_index(conn, embed=embed)
    indexed = {r[0] for r in conn.execute("SELECT email_id FROM rag_chunks")}
    assert indexed == {"e1", "e2", "e3"}
    # A supplier address in the PO list makes its mail relevant, even without a PO number
    conn.execute("INSERT INTO purchase_orders (po_number, supplier, status, supplier_email) "
                 "VALUES ('PO-2000', 'Marketing', 'pending', 'news@marketing.example.com')")
    conn.commit()
    ensure_index(conn, embed=embed)
    assert "e4" in {r[0] for r in conn.execute("SELECT email_id FROM rag_chunks")}
    # With no PO list at all, nothing is sent to the embedding service
    conn.execute("DELETE FROM purchase_orders")
    conn.commit()
    assert ensure_index(conn, embed=embed) == {"embedded": 0, "removed": 4, "chunks": 0}


def test_switching_the_model_rebuilds_everything(conn):
    ensure_index(conn, embed=CountingEmbedder())
    other = CountingEmbedder(signature="bge-m3@http://localhost:8002/v1")
    assert ensure_index(conn, embed=other)["embedded"] == 3
    models = {r[0] for r in conn.execute("SELECT model FROM rag_chunks")}
    assert models == {other.signature}


# --------------------------------------------------------------------- search


def test_search_ranks_the_relevant_email_first(conn):
    hits = search_emails(conn, "unit price rises", embed=HashingEmbedder())
    assert hits[0]["email_id"] == "e3"
    assert hits[0]["po_numbers"] == ["PO-1002"]
    assert hits[0]["snippet"].startswith("From January")


def test_supplier_filter_by_name_address_or_domain(conn):
    embed = HashingEmbedder()
    for supplier in ("Alder Components", "alder", "sales@alder.example.com", "alder.example.com"):
        ids = {h["email_id"] for h in search_emails(conn, "delay", supplier=supplier, embed=embed)}
        assert ids == {"e1", "e2"}, supplier
    assert search_emails(conn, "delay", supplier="nobody@else.example.com", embed=embed) == []


def test_shared_sender_counts_only_through_po_mentions(conn):
    # One test account plays every supplier: its address must not pull in other suppliers' mail.
    conn.execute("UPDATE purchase_orders SET supplier_email = 'tester@gmail.example.com'")
    for e in INBOX.values():
        e = {**e, "from_addr": "tester@gmail.example.com"}
        conn.execute("UPDATE email_messages SET data = ? WHERE email_id = ?", (json.dumps(e), e["email_id"]))
    conn.commit()
    ids = {h["email_id"] for h in search_emails(conn, "delay", supplier="Alder Components", embed=HashingEmbedder())}
    assert ids == {"e1", "e2"}


def test_po_filter_and_exclusion(conn):
    embed = HashingEmbedder()
    assert [h["email_id"] for h in search_emails(conn, "ship date", po_number="PO-1001", embed=embed)] == ["e1"]
    assert search_emails(conn, "ship date", po_number="po-1001", exclude=["e1"], embed=embed) == []
    # PO-100 is not PO-1001
    assert search_emails(conn, "ship date", po_number="PO-100", embed=embed) == []


def test_query_naming_a_po_prefers_emails_about_it(conn):
    hits = search_emails(conn, "what happened with PO-0950", embed=HashingEmbedder())
    assert hits[0]["email_id"] == "e2"


def test_empty_inbox_returns_nothing(tmp_path, monkeypatch):
    import run_pipeline

    monkeypatch.setattr(run_pipeline, "EMAILS_OUT", tmp_path / "missing.json")
    c = db.connect(str(tmp_path / "empty.sqlite"))
    assert search_emails(c, "anything", embed=HashingEmbedder()) == []
    c.close()


def test_playbook_search_and_kind_filter(conn):
    embed = CountingEmbedder()
    hits = search_playbook(conn, "the supplier raised the unit price on an accepted order", embed=embed)
    assert hits[0]["id"] == "6"
    assert set(hits[0]) >= {"id", "title", "text", "kinds", "source", "score"}
    embedded = embed.calls
    search_playbook(conn, "price", embed=embed)
    assert embed.calls == embedded + 1  # rule vectors are cached; only the query is embedded
    kinds = {k for h in search_playbook(conn, "late", kind="out_of_stock", k=8, embed=embed) for k in h["kinds"]}
    assert kinds <= {"out_of_stock", "all"}


def test_two_connections_building_the_index_at_once(tmp_path, monkeypatch):
    # Request A embeds; while it waits for the embedding service, request B builds the
    # same chunks and commits first. A's write must not fail on the existing rows.
    import run_pipeline

    monkeypatch.setattr(run_pipeline, "EMAILS_OUT", tmp_path / "missing.json")
    path = str(tmp_path / "shared.sqlite")
    setup = db.connect(path)
    for e in INBOX.values():
        setup.execute("INSERT INTO email_messages (email_id, data) VALUES (?, ?)", (e["email_id"], json.dumps(e)))
    setup.execute("INSERT INTO purchase_orders (po_number, supplier, status, supplier_email) "
                  "VALUES ('PO-1001', 'Alder Components', 'pending', 'sales@alder.example.com')")
    setup.commit()
    setup.close()
    conn_a, conn_b = db.connect(path), db.connect(path)

    class SlowEmbedder(HashingEmbedder):
        def __call__(self, texts):
            updated = {**INBOX["e1"], "subject": "Latest confirmed date"}
            conn_b.execute("UPDATE email_messages SET data = ? WHERE email_id = 'e1'", (json.dumps(updated),))
            conn_b.commit()
            ensure_index(conn_b, embed=HashingEmbedder())
            return super().__call__(texts)

    result = ensure_index(conn_a, embed=SlowEmbedder())
    assert result["chunks"] == 2  # e1 and e2 are about PO-1001's supplier
    count = conn_a.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0]
    assert conn_a.execute("SELECT subject FROM rag_chunks WHERE email_id = 'e1'").fetchone()[0] == "Latest confirmed date"
    assert count == 2
    conn_a.close()
    conn_b.close()

def test_legacy_import_with_reused_address_scopes_draft_to_one_po(conn):
    from rag.index import order_scope
    conn.execute("UPDATE purchase_orders SET supplier='example.com', supplier_email='demo@example.com'")
    assert order_scope(conn, "PO-1001") == (set(), {"PO-1001"})


def test_exact_company_wins_over_longer_company_name(conn):
    conn.execute("UPDATE purchase_orders SET supplier='Alder Components Europe' WHERE po_number='PO-1002'")
    hits = search_emails(conn, "delay", supplier="Alder Components", embed=HashingEmbedder())
    assert {hit["email_id"] for hit in hits} == {"e1", "e2"}
