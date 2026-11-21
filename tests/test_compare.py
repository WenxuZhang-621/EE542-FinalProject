"""agent/compare.py: both answers end up side by side, with the clone's tools and sources."""

import json
from datetime import date

from agent.compare import compare, to_markdown
from dashboard import db
from schema import FollowUpDraft


def test_markdown_puts_both_answers_side_by_side(tmp_path, monkeypatch):
    import run_pipeline

    monkeypatch.setattr(run_pipeline, "EMAILS_OUT", tmp_path / "missing.json")
    conn = db.connect(str(tmp_path / "po.sqlite"))
    email = {"email_id": "e1", "from_addr": "a@b.example.com", "subject": "PO-1 delay",
             "date": "2026-11-12T08:00:00+00:00", "body_text": "Late.", "attachments": [], "thread_id": ""}
    conn.execute("INSERT INTO email_messages (email_id, data) VALUES ('e1', ?)", (json.dumps(email),))
    conn.commit()

    asked = []

    def generic(question):
        asked.append(question)
        return "Contact the supplier and consider alternatives."

    def clone(c, question):
        draft = FollowUpDraft("d-1", "PO-1", "a@b.example.com", "Re: PO-1", "Hello", "Late")
        return {"answer": "PO-1 slipped two weeks (email of Nov 12). Ask for a recovery plan (§3).",
                "tools_used": ["get_po(PO-1)", 'search_playbook(query="delay")'],
                "sources": [{"type": "email", "emailId": "e1"}, {"type": "rule", "ruleId": "3"}],
                "drafts": [draft]}

    rows = compare(conn, ["PO-1 is late. What should I do?"], generic=generic, clone=clone)
    text = to_markdown(conn, rows, model="gpt-4o-mini", today=date(2026, 11, 21))
    conn.close()

    assert asked == ["PO-1 is late. What should I do?"]
    assert "## 1. PO-1 is late. What should I do?" in text
    assert text.index("### Generic model") < text.index("Contact the supplier") < text.index("### Expediter clone")
    assert "Tools used: get_po(PO-1), search_playbook(query=\"delay\")" in text
    assert 'Sources: Email 2026-11-12 "PO-1 delay"; Playbook §3 Ask for the cause and the recovery plan' in text
    assert "Draft for PO-1 (not sent): Re: PO-1" in text
    assert "2026-11-21 · model: gpt-4o-mini" in text
