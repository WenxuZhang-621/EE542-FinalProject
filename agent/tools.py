"""The tools the chat model can call, and the refs that let its answer cite sources.

Each tool returns plain JSON for the model. Every email in a result carries a ref such as
"E1" and every playbook rule a ref such as "R3" (rule §3) or "RU1" (uploaded rule U1). The
model cites them as [E1] / [R3]; chat.py turns those back into real email ids and rule ids.

Only draft_followup creates anything: a draft waiting for the buyer's review. No tool sends
email or changes an order.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from datetime import date

from agent.draft import KIND_PRIORITY, DraftError, draft_followup, supplier_name
from agent.playbook import KINDS
from rag.embed import Embedder, EmbeddingError
from rag.index import (
    AmbiguousSupplier,
    _mentions,
    _po_key,
    _po_pattern,
    mentions_po,
    search_emails,
    search_playbook,
    strip_quoted,
)
from schema import FollowUpDraft

MAX_EXCEPTIONS = 40
SNIPPET_CHARS = 400

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "list_exceptions",
            "description": "Open problems on tracked purchase orders (delays, partial shipments, "
                           "out of stock, price changes, suppliers that have not replied), most urgent first.",
            "parameters": {
                "type": "object",
                "properties": {"kind": {"type": "string", "enum": list(KINDS),
                                        "description": "Only this kind of problem"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_po",
            "description": "One purchase order: ordered terms, the supplier's latest terms, open "
                           "problems, history of changes and the latest emails about it.",
            "parameters": {
                "type": "object",
                "properties": {"po_number": {"type": "string", "description": "e.g. PO-2026-0412"}},
                "required": ["po_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": "Search the stored supplier emails by meaning. Use it for what a supplier "
                           "said or did before, e.g. earlier delays or promises.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "supplier": {"type": "string", "description": "Supplier name, email address or domain"},
                    "po_number": {"type": "string", "description": "Only emails that mention this PO"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_playbook",
            "description": "Search the buyer playbook: the expert rules for handling each kind of problem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string",
                              "description": "Describe the situation, e.g. 'supplier pushed the ship "
                                             "date back two weeks', not just a PO number"},
                    "kind": {"type": "string", "enum": list(KINDS)},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_followup",
            "description": "Write a follow-up email for a PO with an open problem. The draft waits "
                           "for the buyer's review; it is never sent.",
            "parameters": {
                "type": "object",
                "properties": {"po_number": {"type": "string"}},
                "required": ["po_number"],
            },
        },
    },
]


def _snippet(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= SNIPPET_CHARS else text[:SNIPPET_CHARS].rstrip() + "…"


class Toolbox:
    """Runs the tools for one chat request and remembers which refs it handed out."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        embed: Embedder | None = None,
        draft_llm: Callable | None = None,
        buyer_name: str | None = None,
        today: date | None = None,
        on_draft: Callable[[FollowUpDraft], None] | None = None,
    ):
        self.conn = conn
        self.embed = embed
        self.draft_llm = draft_llm
        self.buyer_name = buyer_name
        self.today = today
        self.on_draft = on_draft
        self.refs: dict[str, dict] = {}   # "E1" -> {"type": "email", "emailId": ...}
        self._email_refs: dict[str, str] = {}
        self.drafts: list[FollowUpDraft] = []
        self._emails: dict[str, dict] | None = None

    # -------------------------------------------------------------- refs

    def email_ref(self, email_id: str | None) -> str | None:
        if not email_id:
            return None
        if email_id not in self._email_refs:
            ref = f"E{len(self._email_refs) + 1}"
            self._email_refs[email_id] = ref
            self.refs[ref] = {"type": "email", "emailId": email_id}
        return self._email_refs[email_id]

    def rule_ref(self, rule_id: str) -> str:
        ref = f"R{rule_id}"
        self.refs[ref] = {"type": "rule", "ruleId": rule_id}
        return ref

    def emails(self) -> dict[str, dict]:
        if self._emails is None:
            import run_pipeline

            self._emails = run_pipeline.stored_emails(self.conn)
        return self._emails

    # ------------------------------------------------------------- tools

    def run(self, name: str, arguments: str | dict) -> dict:
        """Run one tool call; problems come back as {"error": ...} so the model can react."""
        try:
            args = json.loads(arguments or "{}") if isinstance(arguments, str) else dict(arguments or {})
        except json.JSONDecodeError:
            return {"error": "The tool arguments were not valid JSON."}
        handler = getattr(self, f"tool_{name}", None)
        if handler is None or name not in {t["function"]["name"] for t in TOOL_SPECS}:
            return {"error": f"Unknown tool {name}."}
        try:
            return handler(**{k: v for k, v in args.items() if v not in (None, "")})
        except TypeError as exc:
            return {"error": f"Bad arguments for {name}: {exc}"}
        except EmbeddingError as exc:
            return {"error": f"Email search is not available right now: {exc}"}
        except (DraftError, AmbiguousSupplier) as exc:
            return {"error": str(exc)}

    def _order(self, po_number: str):
        return self.conn.execute(
            "SELECT * FROM purchase_orders WHERE UPPER(REPLACE(po_number, ' ', '')) = ?",
            (_po_key(po_number),),
        ).fetchone()

    def tool_list_exceptions(self, kind: str | None = None) -> dict:
        rows = self.conn.execute(
            "SELECT e.po_number, e.kind, e.detail, e.source_email_id, o.supplier, o.supplier_email, "
            "o.item, o.requested_date FROM exceptions e JOIN purchase_orders o USING (po_number)"
            + (" WHERE e.kind = ?" if kind else ""),
            (kind,) if kind else (),
        ).fetchall()
        rows = sorted(rows, key=lambda r: (KIND_PRIORITY.index(r["kind"]) if r["kind"] in KIND_PRIORITY else 99,
                                           r["po_number"]))
        items = [
            {
                "po_number": r["po_number"],
                "kind": r["kind"],
                "detail": r["detail"],
                "supplier": supplier_name(dict(r)) or r["supplier_email"],
                "item": r["item"],
                "requested_ship_date": r["requested_date"],
                "email": self.email_ref(r["source_email_id"]),
            }
            for r in rows[:MAX_EXCEPTIONS]
        ]
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["kind"]] = counts.get(r["kind"], 0) + 1
        return {"total": len(rows), "by_kind": counts, "exceptions": items,
                "truncated": len(rows) > MAX_EXCEPTIONS}

    def tool_get_po(self, po_number: str) -> dict:
        row = self._order(po_number)
        if row is None:
            return {"error": f"{po_number} is not a tracked purchase order."}
        po = row["po_number"]
        exceptions = self.conn.execute(
            "SELECT kind, detail, source_email_id FROM exceptions WHERE po_number = ?", (po,)
        ).fetchall()
        events = self.conn.execute(
            "SELECT change_type, old_value, new_value, notes, source_email_id, created_at "
            "FROM events WHERE po_number = ? ORDER BY id", (po,)
        ).fetchall()
        # Emails linked to this PO in the database, or naming this exact PO (PO-1001 is not PO-100).
        linked = ({row["last_email_id"]} | {e["source_email_id"] for e in exceptions}
                  | {ev["source_email_id"] for ev in events}) - {None}
        mentions = [
            e for e in self.emails().values()
            if e["email_id"] in linked or mentions_po(e, po)
        ]
        mentions.sort(key=lambda e: e.get("date") or "", reverse=True)
        return {
            "po_number": po,
            "supplier": supplier_name(dict(row)) or row["supplier_email"] or row["supplier"],
            "supplier_email": row["supplier_email"],
            "item": row["item"],
            "ordered": {"quantity": row["quantity_ordered"], "unit_price": row["unit_price"],
                        "currency": row["currency"], "sent_date": row["sent_date"],
                        "requested_ship_date": row["requested_date"] or row["original_date"]},
            "supplier_latest": {"status": row["status"], "ship_date": row["confirmed_date"],
                                "quantity": row["quantity_confirmed"]},
            "open_problems": [
                {"kind": e["kind"], "detail": e["detail"], "email": self.email_ref(e["source_email_id"])}
                for e in exceptions
            ],
            "history": [
                {"change": ev["change_type"], "from": ev["old_value"], "to": ev["new_value"],
                 "note": ev["notes"], "email": self.email_ref(ev["source_email_id"])}
                for ev in events
            ],
            "latest_emails": [
                {"ref": self.email_ref(e["email_id"]), "date": (e.get("date") or "")[:10],
                 "from": e.get("from_addr"), "subject": e.get("subject"),
                 "text": _snippet(strip_quoted(e.get("body_text", "")))}
                for e in mentions[:3]
            ],
        }

    def tool_search_emails(self, query: str, supplier: str | None = None,
                           po_number: str | None = None) -> dict:
        hits = search_emails(self.conn, query, supplier=supplier, po_number=po_number, k=5, embed=self.embed)
        return {"results": [
            {"ref": self.email_ref(h["email_id"]), "date": (h["date"] or "")[:10], "from": h["from"],
             "subject": h["subject"], "po_numbers": h["po_numbers"], "text": h["snippet"],
             "score": h["score"]}
            for h in hits
        ]}

    def tool_search_playbook(self, query: str, kind: str | None = None) -> dict:
        # "What should I do about PO-1001?" -> search with that PO's problem, not its number.
        if kind is None:
            known = [r[0] for r in self.conn.execute("SELECT po_number FROM purchase_orders")]
            for po in sorted(_mentions(query, _po_pattern(known))):
                problems = self.conn.execute(
                    "SELECT kind, detail FROM exceptions WHERE UPPER(po_number) = ?", (po,)
                ).fetchall()
                if problems:
                    top = min(problems, key=lambda p: KIND_PRIORITY.index(p["kind"])
                              if p["kind"] in KIND_PRIORITY else 99)
                    kind = top["kind"]
                    query = f"{query} {top['kind'].replace('_', ' ')}: {top['detail']}"
                    break
        hits = search_playbook(self.conn, query, kind=kind, k=3, embed=self.embed)
        return {"rules": [
            {"ref": self.rule_ref(h["id"]), "title": h["title"], "rule": h["text"],
             "applies_to": h["kinds"], "company_rule": h["origin"] == "uploaded"}
            for h in hits
        ]}

    def tool_draft_followup(self, po_number: str) -> dict:
        draft = draft_followup(self.conn, po_number, buyer_name=self.buyer_name, today=self.today,
                               llm=self.draft_llm, embed=self.embed)
        self.drafts.append(draft)
        if self.on_draft:
            self.on_draft(draft)
        # No body here: the page shows the full draft, the answer only summarizes it.
        return {
            "draft_created": True,
            "note": "The draft is shown to the buyer for review. It was not sent.",
            "to": draft.to,
            "subject": draft.subject,
            "language": draft.language,
            "why": draft.why,
            "rules": [self.rule_ref(r) for r in draft.rule_ids],
            "emails": [self.email_ref(e) for e in draft.email_ids],
        }


def label(name: str, arguments: str | dict) -> str:
    """How a tool call is shown on the page, e.g. get_po(PO-1001) or search_emails(query="delay")."""
    try:
        args = json.loads(arguments or "{}") if isinstance(arguments, str) else dict(arguments or {})
    except json.JSONDecodeError:
        args = {}
    args = {k: v for k, v in args.items() if v not in (None, "")}
    if set(args) == {"po_number"}:
        return f"{name}({args['po_number']})"
    inner = ", ".join(f'{k}="{v}"' if k == "query" else f"{k}={v}" for k, v in args.items())
    return f"{name}({inner})"
