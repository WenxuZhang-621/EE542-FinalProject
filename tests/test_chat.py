"""agent/chat.py and agent/tools.py: the tool loop, citations and the tools, all offline.

A scripted fake model decides which tools to call; word-hash vectors stand in for embeddings.
"""

import json
from datetime import date

import pytest

from agent.chat import MAX_ROUNDS, _history, chat, resolve_citations
from agent.tools import Toolbox, label
from dashboard import db
from rag.embed import HashingEmbedder

FRIDAY = date(2026, 11, 20)

EMAILS = [
    {"email_id": "e1", "from_addr": "sales@alder.example.com", "subject": "Re: PO-1001 ship date",
     "date": "2026-11-12T08:00:00+00:00", "body_text": "PO-1001 now ships on Dec 15 instead of Dec 1.",
     "attachments": [], "thread_id": "t1"},
    {"email_id": "e2", "from_addr": "sales@alder.example.com", "subject": "PO-0950 delayed",
     "date": "2026-09-02T08:00:00+00:00", "body_text": "PO-0950 is late again; resin did not arrive.",
     "attachments": [], "thread_id": "t0"},
]


@pytest.fixture
def conn(tmp_path, monkeypatch):
    import run_pipeline

    monkeypatch.setattr(run_pipeline, "EMAILS_OUT", tmp_path / "missing.json")
    c = db.connect(str(tmp_path / "po.sqlite"))
    for e in EMAILS:
        c.execute("INSERT INTO email_messages (email_id, data) VALUES (?, ?)", (e["email_id"], json.dumps(e)))
    c.executemany(
        "INSERT INTO purchase_orders (po_number, supplier, supplier_email, status, confirmed_date, last_email_id, "
        "item, quantity_ordered, unit_price, currency, sent_date, requested_date) "
        "VALUES (?, ?, ?, ?, ?, ?, 'Bracket', 500, 2.4, 'USD', '2026-11-02', '2026-12-01')",
        [
            ("PO-1001", "Alder Components", "sales@alder.example.com", "delayed", "2026-12-15", "e1"),
            ("PO-0950", "Alder Components", "sales@alder.example.com", "confirmed", None, "e2"),
            ("PO-1003", "example.com", "supplier03@example.com", "pending", None, None),
        ],
    )
    c.executemany(
        "INSERT INTO exceptions (po_number, kind, detail, detected_at, source_email_id) VALUES (?, ?, ?, ?, ?)",
        [
            ("PO-1003", "no_reply", "No supplier reply after 14 business days", "2026-11-20T09:00:00+00:00", None),
            ("PO-1001", "delayed", "2026-12-01 → 2026-12-15 (+14 days)", "2026-11-12T09:00:00+00:00", "e1"),
        ],
    )
    c.execute("INSERT INTO events (po_number, change_type, old_value, new_value, source_email_id, notes) "
              "VALUES ('PO-1001', 'date_change', '2026-12-01', '2026-12-15', 'e1', 'factory holiday')")
    c.commit()
    yield c
    c.close()


def call(name, call_id="c1", **args):
    return {"id": call_id, "name": name, "arguments": json.dumps(args)}


class Script:
    """A fake model: each reply is a list of tool calls or a final text."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.seen = []

    def __call__(self, messages, tools):
        self.seen.append((list(messages), tools))
        reply = self.replies.pop(0) if self.replies else "Done."
        if isinstance(reply, list):
            return {"content": None, "tool_calls": reply}
        return {"content": reply, "tool_calls": []}


def ask(conn, model, question="Which orders are at risk this week?", **kw):
    return chat(conn, [{"role": "user", "content": question}], llm=model, embed=HashingEmbedder(),
                today=FRIDAY, **kw)


def tool_results(model, round_no):
    """The tool messages the model saw at the start of round `round_no` (0-based)."""
    return [json.loads(m["content"]) for m in model.seen[round_no][0] if m["role"] == "tool"]


# ------------------------------------------------------------------ the loop


def test_tools_run_and_citations_become_sources(conn):
    model = Script(
        [call("list_exceptions")],
        [call("get_po", "c2", po_number="po-1001"), call("search_playbook", "c3", query="delay recovery")],
        "PO-1001 slipped to Dec 15 [E1]. Ask for the cause and a recovery plan [R3]. Ignore [E9].",
    )
    result = ask(conn, model)
    assert result["tools_used"] == ["list_exceptions()", "get_po(po-1001)", 'search_playbook(query="delay recovery")']
    assert result["answer"] == ("PO-1001 slipped to Dec 15 (email of Nov 12). "
                                "Ask for the cause and a recovery plan (§3). Ignore.")
    assert {"type": "email", "emailId": "e1"} in result["sources"]
    assert {"type": "rule", "ruleId": "3"} in result["sources"]
    assert all(s.get("emailId") != "E9" for s in result["sources"])
    # The model saw today's date and the tools
    system, tools = model.seen[0][0][0]["content"], model.seen[0][1]
    assert "Today is 2026-11-20 (Friday)" in system
    assert {t["function"]["name"] for t in tools} == {
        "list_exceptions", "get_po", "search_emails", "search_playbook", "draft_followup"}
    # Tool results carry refs, most urgent problem first
    listed = tool_results(model, 1)[0]
    assert [e["po_number"] for e in listed["exceptions"]] == ["PO-1001", "PO-1003"]
    assert listed["exceptions"][0]["email"] == "E1"
    assert listed["by_kind"] == {"no_reply": 1, "delayed": 1}


def test_stops_after_max_rounds_and_answers_without_tools(conn):
    model = Script(*[[call("list_exceptions", f"c{i}")] for i in range(MAX_ROUNDS)], "Partial answer.")
    result = ask(conn, model)
    assert len(result["tools_used"]) == MAX_ROUNDS
    assert result["answer"] == "Partial answer."
    assert len(model.seen) == MAX_ROUNDS + 1  # the last prompt already asks for refs: no rewrite
    last_messages, last_tools = model.seen[-1]
    assert last_tools is None
    assert "could not check" in last_messages[-1]["content"]


def test_unknown_po_comes_back_as_an_error_for_the_model(conn):
    model = Script([call("get_po", po_number="PO-9999")], "I could not find PO-9999.")
    result = ask(conn, model, "What about PO-9999?")
    assert tool_results(model, 1) == [{"error": "PO-9999 is not a tracked purchase order."}]
    assert result["sources"] == [] and "could not find" in result["answer"]


def test_draft_tool_creates_a_review_draft_and_never_sends(conn):
    saved = []

    def draft_model(messages, schema):
        return {"subject": "New ship date", "body": "Hello,\n\nCould part of PO-1001 ship on Dec 1?\n\nAlex",
                "why": "Delay over two weeks.", "rule_ids": ["4"], "email_refs": ["E1"]}

    model = Script([call("draft_followup", po_number="PO-1001")], "I drafted a follow-up for PO-1001 [R4].")
    result = ask(conn, model, "Draft a follow-up for PO-1001", draft_llm=draft_model,
                 buyer_name="Alex", on_draft=saved.append)
    assert [d.po_number for d in result["drafts"]] == ["PO-1001"]
    assert saved == result["drafts"]
    tool = tool_results(model, 1)[0]
    assert tool["draft_created"] and "not sent" in tool["note"]
    assert tool["rules"] == ["R4"] and tool["emails"] == ["E1"]
    assert result["sources"] == [{"type": "rule", "ruleId": "4"}]


def test_search_tools_return_refs(conn):
    model = Script(
        [call("search_emails", query="late again", supplier="Alder Components")],
        "Alder was late on PO-0950 before [E1].",
    )
    result = ask(conn, model, "Has Alder delayed before?")
    hits = tool_results(model, 1)[0]["results"]
    assert hits[0]["subject"] == "PO-0950 delayed" and hits[0]["ref"] == "E1"
    assert result["sources"] == [{"type": "email", "emailId": "e2"}]


# ------------------------------------------------- answers that forget refs


def test_uncited_answer_is_rewritten_once_with_refs(conn):
    model = Script([call("get_po", po_number="PO-1001")], "PO-1001 now ships on Dec 15.",
                   "PO-1001 now ships on Dec 15 [E1].")
    result = ask(conn, model, "When does PO-1001 ship?")
    assert result["answer"] == "PO-1001 now ships on Dec 15 (email of Nov 12)."
    assert result["sources"] == [{"type": "email", "emailId": "e1"}]
    assert len(model.seen) == 3
    messages, tools = model.seen[2]
    assert tools is None  # rewrite only, no more tool calls
    assert messages[-2] == {"role": "assistant", "content": "PO-1001 now ships on Dec 15."}
    assert "cites none" in messages[-1]["content"] and "Rewrite it in\nEnglish" in messages[-1]["content"]


def test_no_rewrite_when_the_tools_handed_out_no_refs(conn):
    greeting = Script("Hi, I keep your purchase orders on track.")
    assert ask(conn, greeting, "Hi")["sources"] == [] and len(greeting.seen) == 1
    missing = Script([call("get_po", po_number="PO-9999")], "I could not find PO-9999.")
    assert ask(conn, missing, "What about PO-9999?")["answer"] == "I could not find PO-9999."
    assert len(missing.seen) == 2


def test_no_rewrite_after_drafting(conn):
    def draft_model(messages, schema):
        return {"subject": "New ship date", "body": "Hello,\n\nCould PO-1001 ship on Dec 1?\n\nAlex",
                "why": "Delay over two weeks.", "rule_ids": ["4"], "email_refs": ["E1"]}

    model = Script([call("draft_followup", po_number="PO-1001")], "I drafted a follow-up for PO-1001.")
    result = ask(conn, model, "Draft a follow-up for PO-1001", draft_llm=draft_model, buyer_name="Alex")
    assert len(result["drafts"]) == 1 and len(model.seen) == 2  # the draft card shows its own sources


def test_rewrite_that_still_cites_nothing_keeps_the_first_answer(conn):
    model = Script([call("get_po", po_number="PO-1001")], "PO-1001 now ships on Dec 15.", "Still no refs.")
    result = ask(conn, model, "When does PO-1001 ship?")
    assert result["answer"] == "PO-1001 now ships on Dec 15." and result["sources"] == []
    assert len(model.seen) == 3  # one rewrite, never a loop

    from agent.llm import LLMError

    def failing_rewrite(messages, tools):
        if len(failing_rewrite.calls) == 2:
            raise LLMError("The model call failed: timeout")
        failing_rewrite.calls.append(1)
        return model_reply.pop(0)

    failing_rewrite.calls = []
    model_reply = [{"content": None, "tool_calls": [call("get_po", po_number="PO-1001")]},
                   {"content": "PO-1001 now ships on Dec 15.", "tool_calls": []}]
    assert ask(conn, failing_rewrite, "When does PO-1001 ship?")["answer"] == "PO-1001 now ships on Dec 15."


# --------------------------------------------------------------- the tools


def test_get_po_has_terms_problems_history_and_emails(conn):
    box = Toolbox(conn, embed=HashingEmbedder())
    po = box.run("get_po", {"po_number": "PO-1001"})
    assert po["ordered"]["requested_ship_date"] == "2026-12-01"
    assert po["supplier_latest"]["ship_date"] == "2026-12-15"
    assert po["open_problems"][0]["kind"] == "delayed"
    assert po["history"][0]["note"] == "factory holiday"
    assert po["latest_emails"][0]["ref"] == po["open_problems"][0]["email"] == "E1"
    assert box.refs["E1"] == {"type": "email", "emailId": "e1"}


def test_playbook_search_by_po_uses_that_po_problem(conn):
    box = Toolbox(conn, embed=HashingEmbedder())
    rules = box.run("search_playbook", {"query": "what should I do about PO-1001"})["rules"]
    assert rules and all(set(r["applies_to"]) & {"delayed", "all"} for r in rules)
    assert all(r["ref"].startswith("R") for r in rules)


def test_answer_language_follows_the_question(conn):
    model = Script("好的。")
    ask(conn, model, "这周哪些订单延误了？")
    assert "is in Chinese: answer in Chinese" in model.seen[0][0][0]["content"]
    model = Script("OK.")
    ask(conn, model, "Which orders are late?")
    assert "is in English: answer in English" in model.seen[0][0][0]["content"]


def test_list_exceptions_filter_and_supplier_name_fallback(conn):
    box = Toolbox(conn)
    only = box.run("list_exceptions", {"kind": "no_reply"})
    assert only["total"] == 1
    assert only["exceptions"][0]["supplier"] == "supplier03@example.com"  # domain is not a name


def test_bad_tool_calls_are_reported_not_raised(conn):
    box = Toolbox(conn)
    assert "not valid JSON" in box.run("get_po", "{not json")["error"]
    assert "Unknown tool" in box.run("delete_order", {})["error"]
    assert "Unknown tool" in box.run("_order", {})["error"]
    assert "Bad arguments" in box.run("get_po", {"po": "PO-1001"})["error"]
    assert "Bad arguments" in box.run("get_po", {})["error"]


# ---------------------------------------------------------------- helpers


def test_resolve_citations():
    refs = {"E1": {"type": "email", "emailId": "e1"}, "R3": {"type": "rule", "ruleId": "3"},
            "RU1": {"type": "rule", "ruleId": "U1"}}
    text, sources = resolve_citations("Late [E1, R3]; see [RU1] and [E1]. 已延误【E1、R3】。", refs)
    assert text == "Late; see and. 已延误。"
    assert sources == [refs["E1"], refs["R3"], refs["RU1"]]
    assert resolve_citations("No refs here.", refs) == ("No refs here.", [])
    assert resolve_citations("Keep [this] text", refs)[0] == "Keep [this] text"
    labels = {"E1": "email of Nov 12", "R3": "§3", "RU1": "rule U1"}
    text, _ = resolve_citations("Follow [R3] and [RU1] after [E1, R3, E9].", refs, labels)
    assert text == "Follow (§3) and (rule U1) after (email of Nov 12; §3)."


def test_history_is_trimmed_and_must_end_with_a_question():
    msgs = [{"role": "user", "content": f"q{i}"} for i in range(15)]
    assert [m["content"] for m in _history(msgs)] == [f"q{i}" for i in range(5, 15)]
    assert _history([{"role": "ai", "content": "Hi"}, {"role": "user", "content": "x" * 5000}])[0]["role"] == "assistant"
    assert len(_history([{"role": "user", "content": "x" * 5000}])[0]["content"]) == 4000
    with pytest.raises(ValueError):
        _history([{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}])
    with pytest.raises(ValueError):
        _history([])


def test_labels():
    assert label("get_po", '{"po_number": "PO-1"}') == "get_po(PO-1)"
    assert label("list_exceptions", "{}") == "list_exceptions()"
    assert label("search_emails", {"query": "late", "supplier": "Alder", "po_number": None}) == \
        'search_emails(query="late", supplier=Alder)'


def test_get_po_does_not_take_mail_about_a_longer_po_number(conn):
    # PO-100 must not pick up the email about PO-1001 (it contains "PO-100" as a substring).
    conn.execute("INSERT INTO purchase_orders (po_number, supplier, supplier_email, status) "
                 "VALUES ('PO-100', 'Alder Components', 'sales@alder.example.com', 'pending')")
    conn.commit()
    box = Toolbox(conn)
    assert box.run("get_po", {"po_number": "PO-100"})["latest_emails"] == []
    assert [e["subject"] for e in box.run("get_po", {"po_number": "PO-1001"})["latest_emails"]] == \
        ["Re: PO-1001 ship date"]
