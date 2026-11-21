"""agent/draft.py: what goes into the prompt, and how the model's answer is checked.

A fake model stands in for the LLM and word-hash vectors stand in for embeddings,
so these tests run offline.
"""

import json
from datetime import date

import pytest

from agent.draft import (
    DraftError,
    NoExceptionError,
    add_business_days,
    detect_language,
    draft_followup,
    load_style_samples,
)
from dashboard import db
from rag.embed import EmbeddingError, HashingEmbedder

FRIDAY = date(2026, 11, 20)


def email(email_id, sender, subject, body, date_, thread):
    return {"email_id": email_id, "from_addr": sender, "subject": subject, "date": date_,
            "body_text": body, "attachments": [], "thread_id": thread}


EMAILS = [
    email("e0", "sales@alder.example.com", "PO-1001 received", "We received PO-1001 and will confirm soon.",
          "2026-11-03T08:00:00+00:00", "t1"),
    email("e1", "sales@alder.example.com", "Re: PO-1001 ship date",
          "PO-1001 now ships on Dec 15 instead of Dec 1 because of a factory holiday.\n\n"
          "On Nov 3, 2026, Buyer wrote:\n> Please confirm PO-1001.", "2026-11-12T08:00:00+00:00", "t1"),
    email("e2", "sales@alder.example.com", "PO-0950 delayed",
          "Sorry, PO-0950 is late again; the resin shipment did not arrive.", "2026-09-02T08:00:00+00:00", "t0"),
    email("e3", "export@birch.example.com", "PO-1002 价格调整通知",
          "您好，因原材料价格上涨，订单 PO-1002 的单价需从 2.40 美元调整为 2.65 美元。数量和交期不变。请确认是否接受新价格。",
          "2026-11-13T08:00:00+00:00", "t3"),
]


class FakeModel:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, messages, schema):
        self.calls.append(messages)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def answer(**overrides):
    base = {"subject": "New ship date", "body": "Hi Li,\n\nCould you ship part of PO-1001 on Dec 1?\n\nAlex",
            "why": "Delay of 14 days; asked for a partial shipment.", "rule_ids": ["4", "8"], "email_refs": ["E1"]}
    return {**base, **overrides}


@pytest.fixture
def conn(tmp_path, monkeypatch):
    import run_pipeline

    monkeypatch.setattr(run_pipeline, "EMAILS_OUT", tmp_path / "missing.json")
    c = db.connect(str(tmp_path / "po.sqlite"))
    for e in EMAILS:
        c.execute("INSERT INTO email_messages (email_id, data) VALUES (?, ?)",
                  (e["email_id"], json.dumps(e, ensure_ascii=False)))
    orders = [
        ("PO-1001", "Alder Components", "sales@alder.example.com", "delayed", "2026-12-15", "e1"),
        ("PO-0950", "Alder Components", "sales@alder.example.com", "confirmed", None, "e2"),
        ("PO-1002", "Birch Fasteners", "export@birch.example.com", "price_change", None, "e3"),
        ("PO-1003", "Alder Components", "sales@alder.example.com", "pending", None, None),
        ("PO-1004", "Birch Fasteners", "export@birch.example.com", "confirmed", None, None),
    ]
    c.executemany(
        "INSERT INTO purchase_orders (po_number, supplier, supplier_email, status, confirmed_date, "
        "last_email_id, item, quantity_ordered, unit_price, currency, sent_date, requested_date) "
        "VALUES (?, ?, ?, ?, ?, ?, 'Bracket', 500, 2.4, 'USD', '2026-11-02', '2026-12-01')",
        orders,
    )
    c.executemany(
        "INSERT INTO exceptions (po_number, kind, detail, detected_at, source_email_id) VALUES (?, ?, ?, ?, ?)",
        [
            ("PO-1001", "delayed", "2026-12-01 → 2026-12-15 (+14 days)", "2026-11-12T09:00:00+00:00", "e1"),
            ("PO-1002", "price_change", "Unit price 2.4 USD → 2.65 USD", "2026-11-13T09:00:00+00:00", "e3"),
            ("PO-1003", "no_reply", "No supplier reply after 14 business days", "2026-11-20T09:00:00+00:00", None),
        ],
    )
    c.commit()
    yield c
    c.close()


def draft(conn, po, model, **kw):
    return draft_followup(conn, po, buyer_name="Alex", today=FRIDAY, llm=model,
                          embed=kw.pop("embed", HashingEmbedder()), **kw)


def prompt(model, call=0):
    return model.calls[call][1]["content"]


# ------------------------------------------------------------------ the draft


def test_delay_draft_replies_in_the_thread_and_keeps_valid_citations(conn):
    model = FakeModel(answer(rule_ids=["4", "§8", "99"], email_refs=["E1", "E3", "E9"]))
    d = draft(conn, "po-1001", model)
    assert d.po_number == "PO-1001"
    assert d.to == "sales@alder.example.com"
    assert d.reply_to_email_id == "e1" and d.thread_id == "t1"
    assert d.subject == "Re: PO-1001: New ship date"
    assert d.rule_ids == ["4", "8"]          # "99" is not a rule we gave the model
    assert d.email_ids == ["e1", "e2"]       # E1 = latest PO email, E3 = supplier history; E9 unknown
    assert d.language == "en" and d.state == "review" and d.draft_id.startswith("d-")


def test_prompt_has_the_order_rules_history_and_reply_by_date(conn):
    model = FakeModel(answer())
    draft(conn, "PO-1001", model)
    text = prompt(model)
    assert "Ask for a reply by 2026-11-24" in text    # Friday + 2 business days
    assert "sign with this name): Alex" in text
    assert "delayed: 2026-12-01 → 2026-12-15 (+14 days)" in text
    # Emails about this PO, latest first, quoted text removed
    assert text.index("[E1] 2026-11-12") < text.index("[E2] 2026-11-03")
    assert "> Please confirm" not in text
    # The supplier's earlier delay is found by search; the other supplier's mail is not
    history = text.split("## This supplier's earlier emails")[1].split("## Playbook rules")[0]
    assert "PO-0950" in history and "PO-1002" not in history
    # Rules for delays and the general writing rule
    rules = text.split("## Playbook rules")[1]
    for rid in ("[2]", "[3]", "[4]", "[5]", "[8]"):
        assert rid in rules
    assert "## Tone example (a made-up order" in text


def test_chinese_supplier_gets_a_chinese_draft(conn):
    model = FakeModel(answer(subject="PO-1002 调价", body="张华您好，……", rule_ids=["6"], email_refs=["E1"]))
    d = draft(conn, "PO-1002", model)
    assert "Write the email in Chinese." in prompt(model)
    assert d.language == "zh"
    assert d.email_ids == ["e3"]


def test_no_reply_starts_a_new_thread(conn):
    model = FakeModel(answer(subject="Confirmation needed", rule_ids=["1"], email_refs=[]))
    d = draft(conn, "PO-1003", model)
    assert d.reply_to_email_id is None and d.thread_id is None
    assert d.to == "sales@alder.example.com"
    assert d.subject == "PO-1003: Confirmation needed"
    assert "(none: the supplier has not replied about this PO)" in prompt(model)


def test_nothing_to_draft(conn):
    with pytest.raises(NoExceptionError):
        draft(conn, "PO-1004", FakeModel())
    with pytest.raises(DraftError, match="not tracked"):
        draft(conn, "PO-9999", FakeModel())
    assert issubclass(NoExceptionError, DraftError)


def test_asks_again_when_no_rule_is_cited(conn):
    model = FakeModel(answer(rule_ids=[]), answer(rule_ids=["3"]))
    d = draft(conn, "PO-1001", model)
    assert len(model.calls) == 2
    assert "cite at least one rule id" in model.calls[1][-1]["content"]
    assert d.rule_ids == ["3"]


def test_model_failure_is_retried_once_then_reported(conn):
    model = FakeModel(DraftError("timeout"), answer())
    assert draft(conn, "PO-1001", model).body
    with pytest.raises(DraftError):
        draft(conn, "PO-1001", FakeModel(DraftError("down"), DraftError("down")))
    with pytest.raises(DraftError, match="did not write"):
        draft(conn, "PO-1001", FakeModel(answer(body=""), answer(body=" ")))


def test_drafts_without_history_when_embeddings_fail(conn):
    class Broken:
        signature = "broken"

        def __call__(self, texts):
            raise EmbeddingError("no key")

    model = FakeModel(answer())
    d = draft(conn, "PO-1001", model, embed=Broken())
    assert d.body
    assert "(none found)" in prompt(model)


def test_company_rules_are_marked(conn):
    conn.execute("CREATE TABLE playbook_rules (rule_id TEXT, title TEXT, text TEXT, kinds TEXT, "
                 "source TEXT, enabled INTEGER)")
    conn.execute("INSERT INTO playbook_rules VALUES ('U1', 'Escalate Alder', "
                 "'Copy the operations manager on any Alder delay over 5 days.', '[\"delayed\"]', 'pasted', 1)")
    conn.commit()
    model = FakeModel(answer(rule_ids=["U1", "4"]))
    d = draft(conn, "PO-1001", model)
    assert "[U1] [company] Escalate Alder" in prompt(model)
    assert d.rule_ids == ["U1", "4"]


def test_a_domain_is_not_used_as_the_supplier_name(conn):
    # The current PO import stores the email domain as the supplier.
    conn.execute("UPDATE purchase_orders SET supplier = 'alder.example.com' WHERE po_number = 'PO-1003'")
    conn.commit()
    model = FakeModel(answer(rule_ids=["1"], email_refs=[]))
    draft(conn, "PO-1003", model)
    assert "Supplier: (company name unknown) <sales@alder.example.com>" in prompt(model)
    assert 'neutral greeting such as "Hello,"' in model.calls[0][0]["content"]


# -------------------------------------------------------------------- helpers


def test_supplier_name():
    from agent.draft import supplier_name

    assert supplier_name({"supplier": "Alder Components", "supplier_email": "a@alder.example.com"}) == "Alder Components"
    assert supplier_name({"supplier": "example.com", "supplier_email": "supplier01@example.com"}) == ""
    assert supplier_name({"supplier": "nb-plastics.example.cn", "supplier_email": "x@other.cn"}) == ""
    assert supplier_name({"supplier": "", "supplier_email": "x@y.com"}) == ""


def test_detect_language():
    assert detect_language("您好，因原材料价格上涨，订单 PO-1002 的单价需要调整。") == "zh"
    assert detect_language("Hi, PO-1001 now ships Dec 15.") == "en"
    assert detect_language("") == "en"


def test_add_business_days_skips_weekends():
    assert add_business_days(FRIDAY, 2) == date(2026, 11, 24)
    assert add_business_days(date(2026, 11, 23), 1) == date(2026, 11, 24)


def test_style_samples_are_tagged():
    samples = load_style_samples()
    assert {s["kind"] for s in samples} == {"delayed", "no_reply", "price_change", "out_of_stock"}
    assert {s["language"] for s in samples} == {"en", "zh"}
    assert all(s["text"].startswith("Subject:") for s in samples)


# --------------------------------------------------------- review fixes (11/20)


def add_email(conn, email_id, sender, subject, body, date_, thread):
    e = email(email_id, sender, subject, body, date_, thread)
    conn.execute("INSERT INTO email_messages (email_id, data) VALUES (?, ?)", (email_id, json.dumps(e)))
    conn.commit()


def test_a_colleagues_forward_is_context_not_the_reply_target(conn):
    # The supplier wrote on Nov 12; a colleague forwarded it on Nov 13, naming the same PO.
    add_email(conn, "e5", "ops@harborline.example.com", "Fwd: PO-1001 ship date",
              "FYI, PO-1001 slips to Dec 15.", "2026-11-13T08:00:00+00:00", "t-internal")
    model = FakeModel(answer())
    d = draft(conn, "PO-1001", model)
    assert d.to == "sales@alder.example.com"
    assert d.reply_to_email_id == "e1" and d.thread_id == "t1"
    text = prompt(model)
    assert "ops@harborline.example.com (not from the supplier)" in text
    assert "sales@alder.example.com (the supplier; the draft replies to this email)" in text


def test_without_a_supplier_email_the_draft_starts_a_new_thread(conn):
    conn.execute("INSERT INTO purchase_orders (po_number, supplier, supplier_email, status) "
                 "VALUES ('PO-1005', 'Alder Components', 'sales@alder.example.com', 'delayed')")
    conn.execute("INSERT INTO exceptions (po_number, kind, detail, detected_at) "
                 "VALUES ('PO-1005', 'delayed', 'Supplier reported a delay', '2026-11-13')")
    add_email(conn, "e6", "ops@harborline.example.com", "PO-1005 heads-up",
              "Heard PO-1005 may be late.", "2026-11-13T08:00:00+00:00", "t-internal")
    model = FakeModel(answer(subject="Re: PO-1005 status"))
    d = draft(conn, "PO-1005", model)
    assert d.to == "sales@alder.example.com"
    assert d.reply_to_email_id is None and d.thread_id is None
    assert d.subject == "PO-1005 status"  # a new thread is not a reply
    assert "starts a new thread to the supplier" in prompt(model)


def test_shared_sender_history_only_holds_this_suppliers_mail(conn):
    # One test account sends for both Alder and Birch.
    shared = "tester@gmail.example.com"
    conn.execute("UPDATE purchase_orders SET supplier_email = ?", (shared,))
    for row in conn.execute("SELECT email_id, data FROM email_messages").fetchall():
        e = {**json.loads(row["data"]), "from_addr": shared}
        conn.execute("UPDATE email_messages SET data = ? WHERE email_id = ?", (json.dumps(e), row["email_id"]))
    add_email(conn, "e7", shared, "PO-1002 delayed again", "PO-1002 is late again; the line broke down.",
              "2026-10-01T08:00:00+00:00", "t7")
    from agent.draft import gather

    material = gather(conn, "PO-1001", embed=HashingEmbedder())
    history = {h["email_id"] for h in material["history"]}
    assert "e2" in history                     # Alder's own earlier delay (PO-0950)
    assert not history & {"e3", "e7"}          # Birch's mail about PO-1002 stays out
    assert material["reply_to"]["email_id"] == "e1"


def test_two_answers_with_only_invalid_rules_are_rejected(conn):
    model = FakeModel(answer(rule_ids=["999"]), answer(rule_ids=["§999"]))
    with pytest.raises(DraftError, match="did not follow any playbook rule"):
        draft(conn, "PO-1001", model)
    assert len(model.calls) == 2
