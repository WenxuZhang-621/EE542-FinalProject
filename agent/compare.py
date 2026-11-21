"""A generic LLM and the expediter clone answer the same questions, side by side.

The generic model gets only the question: no tools, no orders, no emails, no playbook.
The clone is agent/chat.py with everything. Both use the model configured in .env, so the
difference comes from the data and the playbook, not from a different model.

Usage:
    python agent/compare.py                         # default questions -> data/compare_<date>.md
    python agent/compare.py "Your question" ...     # your own questions
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.playbook import load_playbook  # noqa: E402

DEFAULT_QUESTIONS = [
    "PO-M2-0001 is delayed two weeks. What should I do?",
    "Should I accept the price increase on PO-M2-0003?",
    "Which supplier should I worry about this week?",
]
GENERIC_PROMPT = "You are a helpful assistant."


def generic_answer(question: str) -> str:
    """The configured model with no tools and no data."""
    from openai import APIError

    from agent.llm import LLMError, client, extra_options, model_name

    try:
        resp = client().chat.completions.create(
            model=model_name(), temperature=0.2, **extra_options(),
            messages=[{"role": "system", "content": GENERIC_PROMPT},
                      {"role": "user", "content": question}],
        )
    except APIError as exc:
        raise LLMError(f"The model call failed: {exc}") from exc
    return resp.choices[0].message.content or ""


def clone_answer(conn: sqlite3.Connection, question: str) -> dict:
    from agent.chat import chat

    return chat(conn, [{"role": "user", "content": question}])


def compare(
    conn: sqlite3.Connection,
    questions: list[str],
    *,
    generic: Callable[[str], str] = generic_answer,
    clone: Callable[[sqlite3.Connection, str], dict] = clone_answer,
) -> list[dict]:
    return [{"question": q, "generic": generic(q), "clone": clone(conn, q)} for q in questions]


def _source_label(source: dict, rules: dict, emails: dict) -> str:
    if source["type"] == "rule":
        rule = rules.get(source["ruleId"])
        return f"Playbook §{source['ruleId']}" + (f" {rule.title}" if rule else "")
    email = emails.get(source["emailId"], {})
    when = (email.get("date") or "")[:10]
    return f"Email {when} \"{email.get('subject', source['emailId'])}\"".strip()


def to_markdown(conn: sqlite3.Connection, rows: list[dict], *, model: str, today: date) -> str:
    import run_pipeline

    rules = {r.id: r for r in load_playbook(conn)}
    emails = run_pipeline.stored_emails(conn)
    lines = [
        "# Generic model vs the expediter clone",
        "",
        f"{today.isoformat()} · model: {model} · the generic model gets only the question; "
        "the clone has the orders, the supplier emails (RAG) and the playbook.",
    ]
    for n, row in enumerate(rows, 1):
        clone = row["clone"]
        lines += [
            "",
            f"## {n}. {row['question']}",
            "",
            "### Generic model",
            "",
            row["generic"].strip(),
            "",
            "### Expediter clone",
            "",
            clone["answer"].strip(),
            "",
            f"Tools used: {', '.join(clone['tools_used']) or 'none'}",
        ]
        if clone["sources"]:
            lines.append("Sources: " + "; ".join(_source_label(s, rules, emails) for s in clone["sources"]))
        for draft in clone.get("drafts", []):
            lines += ["", f"Draft for {draft.po_number} (not sent): {draft.subject}", "", draft.body]
    return "\n".join(lines) + "\n"


def main() -> None:
    from agent.llm import model_name
    from dashboard.db import DB_PATH, connect

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("questions", nargs="*", help="default: three questions about the M2 demo orders")
    parser.add_argument("--out", type=Path, help="Markdown file (default data/compare_<date>.md)")
    args = parser.parse_args()
    today = date.today()
    out = args.out or ROOT / "data" / f"compare_{today.isoformat()}.md"
    conn = connect(DB_PATH)
    try:
        rows = compare(conn, args.questions or DEFAULT_QUESTIONS)
        text = to_markdown(conn, rows, model=model_name(), today=today)
    finally:
        conn.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
