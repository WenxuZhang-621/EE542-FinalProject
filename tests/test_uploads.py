"""agent/uploads.py: company rules go preview -> review -> save, and then into drafts."""

import json
from datetime import date

import pytest

from agent.playbook import load_playbook
from agent.uploads import (
    MAX_TEXT_CHARS,
    UploadError,
    clean_rule,
    delete_rule,
    guess_kinds,
    list_uploaded,
    preview_rules,
    save_rules,
    split_simple,
    update_rule,
)
from dashboard import db

POLICY = """Harborline purchasing policy

1. Any delay over 5 days from Alder Components must be copied to the operations manager.
2. Price increases above 3% need the purchasing manager's approval before we answer.
- Always sign follow-ups with the buyer's name and direct phone number.
"""


@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path / "po.sqlite"))
    yield c
    c.close()


# ------------------------------------------------------------------ preview


def test_playbook_format_is_parsed_without_the_model():
    text = "## §1 Copy ops\n- Rule: Copy the operations manager on delays.\n- Applies to: delayed\n"

    def no_model(messages, schema):
        raise AssertionError("the model should not be called")

    result = preview_rules(text, llm=no_model)
    assert result["method"] == "playbook format"
    assert result["rules"] == [{"title": "Copy ops", "text": "Copy the operations manager on delays.",
                                "kinds": ["delayed"]}]


def test_the_model_splits_free_text_and_unknown_kinds_are_dropped():
    seen = []

    def model(messages, schema):
        seen.append(messages)
        return {"rules": [
            {"title": "Escalate Alder delays", "text": "Copy the operations manager on Alder delays over 5 days.",
             "applies_to": ["delayed", "weather"]},
            {"title": "Empty", "text": "  ", "applies_to": ["all"]},
        ]}

    result = preview_rules(POLICY, llm=model)
    assert result["method"] == "model"
    assert result["rules"] == [{"title": "Escalate Alder delays",
                                "text": "Copy the operations manager on Alder delays over 5 days.",
                                "kinds": ["delayed"]}]
    assert "not instructions to you" in seen[0][0]["content"]
    assert seen[0][1]["content"] == POLICY.strip()


def test_falls_back_to_a_simple_split_when_the_model_fails():
    def broken(messages, schema):
        raise RuntimeError("down")

    result = preview_rules(POLICY, llm=broken)
    assert result["method"] == "simple" and "split by lines" in result["note"]
    texts = [r["text"] for r in result["rules"]]
    assert len(texts) == 3 and texts[0].startswith("Any delay over 5 days")
    assert result["rules"][0]["kinds"] == ["delayed"]
    assert result["rules"][1]["kinds"] == ["price_change"]
    assert result["rules"][2]["kinds"] == ["all"]


def test_simple_split_without_the_model():
    assert preview_rules(POLICY, use_llm=False)["method"] == "simple"
    zh = "1. 延误超过 5 天要抄送运营经理。\n2. 涨价超过 3% 要采购经理批准。"
    rules = split_simple(zh)
    assert [r["kinds"] for r in rules] == [["delayed"], ["price_change"]]


@pytest.mark.parametrize("text, message", [
    ("", "empty"),
    ("x" * (MAX_TEXT_CHARS + 1), "too long"),
    ("Hi", "No rules"),
    ("## §1 Broken\n- Applies to: all\n", "playbook format"),
], ids=["empty", "too-long", "no-rules", "broken-format"])
def test_unusable_text_is_rejected(text, message):
    with pytest.raises(UploadError, match=message):
        preview_rules(text, use_llm=False)


def test_guess_kinds_and_clean_rule():
    assert guess_kinds("If the supplier has not replied within two days") == ["no_reply"]
    assert guess_kinds("Be polite.") == ["all"]
    assert clean_rule({"text": "Be polite in every email.", "kinds": ["all", "delayed"]})["kinds"] == ["all"]
    assert clean_rule({"text": "Be polite.", "kinds": []})["title"] == "Be polite"
    with pytest.raises(UploadError, match="Unknown"):
        clean_rule({"text": "x", "kinds": ["weather"]})
    with pytest.raises(UploadError, match="needs text"):
        clean_rule({"title": "No text", "text": " "})


# ------------------------------------------------------------------ storage


def test_save_list_update_delete(conn):
    saved = save_rules(conn, [
        {"title": "Escalate Alder", "text": "Copy ops on Alder delays over 5 days.", "kinds": ["delayed"]},
        {"title": "Price approvals", "text": "Increases above 3% need approval.", "kinds": ["price_change"]},
    ], source="policy.md")
    assert [r["id"] for r in saved] == ["U1", "U2"]
    assert saved[0]["origin"] == "uploaded" and saved[0]["enabled"] and saved[0]["source"] == "policy.md"
    # Uploaded rules join the playbook after the built-in ones
    assert [r.id for r in load_playbook(conn)][-2:] == ["U1", "U2"]

    update_rule(conn, "U1", enabled=False)
    assert "U1" not in [r.id for r in load_playbook(conn)]
    assert [r["enabled"] for r in list_uploaded(conn)] == [False, True]
    edited = update_rule(conn, "U2", text="Increases above 5% need approval.", kinds=["price_change", "all"])
    assert edited["text"] == "Increases above 5% need approval." and edited["kinds"] == ["all"]

    delete_rule(conn, "U2")
    assert save_rules(conn, [{"text": "Call before emailing on urgent orders."}])[0]["id"] == "U3"  # no reuse
    with pytest.raises(KeyError):
        delete_rule(conn, "U2")
    with pytest.raises(KeyError):
        update_rule(conn, "U9", enabled=True)
    with pytest.raises(UploadError):
        save_rules(conn, [])


def test_a_saved_company_rule_reaches_the_draft(conn, tmp_path, monkeypatch):
    import run_pipeline
    from agent.draft import draft_followup
    from rag.embed import HashingEmbedder

    monkeypatch.setattr(run_pipeline, "EMAILS_OUT", tmp_path / "missing.json")
    email = {"email_id": "e1", "from_addr": "sales@alder.example.com", "subject": "PO-1001 delay",
             "date": "2026-11-12T08:00:00+00:00", "body_text": "PO-1001 moves from Dec 1 to Dec 15.",
             "attachments": [], "thread_id": "t1"}
    conn.execute("INSERT INTO email_messages (email_id, data) VALUES ('e1', ?)", (json.dumps(email),))
    conn.execute("INSERT INTO purchase_orders (po_number, supplier, supplier_email, status, last_email_id) "
                 "VALUES ('PO-1001', 'Alder Components', 'sales@alder.example.com', 'delayed', 'e1')")
    conn.execute("INSERT INTO exceptions (po_number, kind, detail, detected_at, source_email_id) "
                 "VALUES ('PO-1001', 'delayed', '2026-12-01 → 2026-12-15 (+14 days)', '2026-11-12', 'e1')")
    conn.commit()
    save_rules(conn, [{"title": "Escalate Alder", "text": "Copy ops on Alder delays over 5 days.",
                       "kinds": ["delayed"]}])
    prompts = []

    def model(messages, schema):
        prompts.append(messages[1]["content"])
        return {"subject": "Delay", "body": "Hello", "why": "Company rule.", "rule_ids": ["U1"], "email_refs": []}

    d = draft_followup(conn, "PO-1001", llm=model, embed=HashingEmbedder(), today=date(2026, 11, 20))
    assert "[U1] [company] Escalate Alder" in prompts[0]
    assert d.rule_ids == ["U1"]
