"""Load the buyer playbook: the expert rules the digital clone follows.

Two places hold rules, merged by `load_playbook()`:

- `agent/buyer_playbook.md`: the built-in rules §1, §2, ... (read-only, `origin="builtin"`).
- the `playbook_rules` table: rules a user uploads (M4, `origin="uploaded"`, ids U1, U2, ...).
  The table may not exist yet; then only the built-in rules are returned.

Usage:
    python agent/playbook.py            # print the parsed rules as JSON
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

PLAYBOOK_PATH = Path(__file__).with_name("buyer_playbook.md")

# The exception kinds from rules.py, plus "all" for rules that apply to every follow-up.
KINDS = ("delayed", "partial", "out_of_stock", "price_change", "no_reply")
ALL = "all"

_HEADING = re.compile(r"^## §(\S+)\s+(.+?)\s*$")
_FIELD = re.compile(r"^- (Rule|Applies to|Source|Checked):\s*(.*?)\s*$")


class PlaybookError(ValueError):
    """The playbook text does not follow the documented format."""


@dataclass
class PlaybookRule:
    id: str                     # "3" for §3; "U1" for an uploaded rule
    title: str
    text: str
    kinds: list[str] = field(default_factory=list)   # exception kinds, or ["all"]
    source: str = ""
    checked: str = ""
    origin: str = "builtin"     # builtin | uploaded

    def applies_to(self, kind: str | None) -> bool:
        return kind is None or ALL in self.kinds or kind in self.kinds

    def to_dict(self) -> dict:
        return asdict(self)


def _kinds(value: str, rule_id: str) -> list[str]:
    kinds = [k.strip() for k in value.split(",") if k.strip()]
    unknown = [k for k in kinds if k not in KINDS and k != ALL]
    if not kinds or unknown:
        raise PlaybookError(
            f"§{rule_id}: 'Applies to' must list {', '.join(KINDS)} or {ALL}; got {value!r}"
        )
    return kinds


def parse_playbook(markdown: str, *, origin: str = "builtin") -> list[PlaybookRule]:
    """Parse rules written as `## §<id> <title>` followed by `- Rule:` / `- Applies to:` /
    `- Source:` / `- Checked:` lines. Text outside a rule (intro, format notes) is ignored."""
    rules: list[PlaybookRule] = []
    current: dict | None = None

    def finish():
        if current is None:
            return
        rid = current["id"]
        if not current.get("Rule"):
            raise PlaybookError(f"§{rid}: missing '- Rule:' line")
        if "Applies to" not in current:
            raise PlaybookError(f"§{rid}: missing '- Applies to:' line")
        if any(r.id == rid for r in rules):
            raise PlaybookError(f"§{rid}: duplicate rule id")
        rules.append(
            PlaybookRule(
                id=rid,
                title=current["title"],
                text=current["Rule"],
                kinds=_kinds(current["Applies to"], rid),
                source=current.get("Source", ""),
                checked=current.get("Checked", ""),
                origin=origin,
            )
        )

    for line in markdown.splitlines():
        heading = _HEADING.match(line)
        if heading:
            finish()
            current = {"id": heading[1], "title": heading[2]}
            continue
        if current is None:
            continue
        if line.startswith("## ") or line.startswith("# "):
            finish()  # another section that is not a rule ends the current rule
            current = None
            continue
        item = _FIELD.match(line)
        if item:
            current[item[1]] = item[2]
    finish()
    return rules


def _uploaded_rules(conn: sqlite3.Connection) -> list[PlaybookRule]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'playbook_rules'"
    ).fetchone()
    if not exists:
        return []
    rows = conn.execute(
        "SELECT rule_id, title, text, kinds, source FROM playbook_rules "
        "WHERE enabled = 1 ORDER BY rowid"
    ).fetchall()
    return [
        PlaybookRule(
            id=row[0], title=row[1], text=row[2], kinds=json.loads(row[3] or '["all"]'),
            source=row[4] or "", origin="uploaded",
        )
        for row in rows
    ]


def load_playbook(
    conn: sqlite3.Connection | None = None, *, path: Path = PLAYBOOK_PATH
) -> list[PlaybookRule]:
    """Built-in rules from the Markdown file, then the user's uploaded rules if any."""
    rules = parse_playbook(path.read_text(encoding="utf-8"))
    if conn is not None:
        rules += _uploaded_rules(conn)
    return rules


def rules_for(kind: str | None, rules: list[PlaybookRule]) -> list[PlaybookRule]:
    """Rules tagged for this exception kind, including the general ("all") ones."""
    return [r for r in rules if r.applies_to(kind)]


if __name__ == "__main__":
    sys.stdout.write(json.dumps([r.to_dict() for r in load_playbook()], indent=2) + "\n")
