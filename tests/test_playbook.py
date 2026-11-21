"""agent/playbook.py: the built-in playbook parses, and malformed rules are rejected."""

import json
import sqlite3

import pytest

from agent.playbook import KINDS, PlaybookError, load_playbook, parse_playbook, rules_for


def test_builtin_playbook_has_eight_sourced_rules():
    rules = load_playbook()
    assert [r.id for r in rules] == [str(n) for n in range(1, 9)]
    for rule in rules:
        assert rule.title and rule.text
        assert rule.origin == "builtin"
        assert "https://" in rule.source
        assert rule.checked.startswith("2026-")
        assert all(k in KINDS or k == "all" for k in rule.kinds)


def test_every_exception_kind_has_a_rule():
    rules = load_playbook()
    for kind in KINDS:
        assert [r for r in rules if kind in r.kinds], kind


def test_rules_for_includes_general_rules():
    rules = load_playbook()
    ids = [r.id for r in rules_for("price_change", rules)]
    assert "6" in ids and "8" in ids  # §8 applies to all follow-ups
    assert "7" not in ids


def test_format_example_in_intro_is_not_a_rule():
    text = "# Playbook\n\n    ## §<n> <short title>\n    - Rule: <...>\n\n## §1 Real\n- Rule: Do it.\n- Applies to: all\n"
    assert [r.id for r in parse_playbook(text)] == ["1"]


@pytest.mark.parametrize(
    "text, message",
    [
        ("## §1 No rule line\n- Applies to: all\n", "missing '- Rule:'"),
        ("## §1 No kinds\n- Rule: Do it.\n", "missing '- Applies to:'"),
        ("## §1 Bad kind\n- Rule: Do it.\n- Applies to: late\n", "Applies to"),
        ("## §1 A\n- Rule: x\n- Applies to: all\n## §1 B\n- Rule: y\n- Applies to: all\n", "duplicate"),
    ],
)
def test_malformed_rules_are_rejected(text, message):
    with pytest.raises(PlaybookError, match=message):
        parse_playbook(text)


def test_uploaded_rules_are_appended_when_the_table_exists():
    conn = sqlite3.connect(":memory:")
    assert len(load_playbook(conn)) == 8  # no table yet: built-in rules only
    conn.execute(
        "CREATE TABLE playbook_rules (rule_id TEXT, title TEXT, text TEXT, kinds TEXT, "
        "source TEXT, enabled INTEGER)"
    )
    conn.executemany(
        "INSERT INTO playbook_rules VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("U1", "Escalate Alder", "Copy the operations manager.", json.dumps(["delayed"]), "pasted", 1),
            ("U2", "Disabled", "Ignore me.", json.dumps(["all"]), "pasted", 0),
        ],
    )
    rules = load_playbook(conn)
    assert [r.id for r in rules][-1] == "U1"
    assert rules[-1].origin == "uploaded" and rules[-1].kinds == ["delayed"]
