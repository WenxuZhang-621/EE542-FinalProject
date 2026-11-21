"""FastAPI layer for the front end.  Run from the repo root:

    uvicorn api.main:app --port 8000 --reload        # docs at http://localhost:8000/docs

Next.js forwards /api/* here (frontend/next.config.ts). Every endpoint reads the SQLite
database the Python pipeline writes and returns the shapes the front end already uses
(frontend/src/modules/po/data/sample.ts), so pages switch from sample data without changes.

    GET  /api/health          what is configured (LLM key, Gmail credentials, database)
    GET  /api/orders          orders + suppliers + emails for the orders page
    GET  /api/orders/{po}     one order with events, exceptions, latest email and extraction
    POST /api/po-list         upload a CSV/xlsx PO list -> new / tracked / errors
    POST /api/sync            fetch new emails (Gmail, or the sample inbox) -> extract -> rules
    POST /api/chat            ask the expediter clone (tool calls + RAG, agent/chat.py)
    GET  /api/playbook        built-in playbook rules + the company rules users uploaded
    POST /api/playbook/preview         split pasted text into rules for review (not saved)
    POST /api/playbook/rules           save reviewed company rules (U1, U2, ...)
    PATCH/DELETE /api/playbook/rules/{id}  enable, disable, edit or remove an uploaded rule
    GET  /api/eval-runs       accuracy runs from extract/eval.py
    POST /api/reset           empty the demo database
"""

from __future__ import annotations

import json
import os
import re
import sys
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Literal, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
for p in (ROOT, ROOT / "extract", ROOT / "dashboard", ROOT / "ingest"):
    sys.path.insert(0, str(p))
import db  # noqa: E402
import run_pipeline as rp  # noqa: E402
from api.po_list import import_po_list  # noqa: E402
from eval import load_runs  # noqa: E402  (extract/eval.py)
from rules import RULE_KINDS, sync_exceptions  # noqa: E402
from schema import EmailMessage  # noqa: E402
from ingest.mailboxes import MailboxStore, token_available  # noqa: E402
from ingest.mailbox_oauth import sessions as oauth_sessions  # noqa: E402

SAMPLES = ROOT / "tests" / "samples"
# Exceptions decide the status shown in the UI; the most urgent kind wins.
KIND_PRIORITY = ["delayed", "out_of_stock", "partial", "price_change", "no_reply"]
DB_STATUS_TO_UI = {"pending": "awaiting"}
SYNC_LOCK = Lock()

app = FastAPI(title="PO Follow-Up API", version="0.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3100", "http://127.0.0.1:3100"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------------ helpers


def conn():
    return db.connect(db.DB_PATH)


def mailbox_store():
    return MailboxStore(db.DB_PATH, rp.EMAILS_OUT)


def load_emails() -> dict[str, dict]:
    with closing(conn()) as c:
        return rp.stored_emails(c)


SHORT_UPPER = {"pcb", "led", "lcd", "usb", "cnc", "abs", "pvc"}


def pretty_name(domain: str) -> str:
    """shenzhen-parts.example.com -> Shenzhen Parts; dg-hardware -> DG Hardware; lakeside-pcb -> Lakeside PCB."""
    first = (domain or "").split(".")[0]
    words = [
        w.upper() if len(w) <= 2 or w in SHORT_UPPER else w.capitalize()
        for w in re.split(r"[-_]+", first)
        if w
    ]
    return " ".join(words) or domain


def supplier_view(domain: str, email: str | None) -> dict:
    return {"id": domain, "name": pretty_name(domain), "email": email or f"@{domain}", "country": ""}


def email_view(e: dict, mailbox: str | None = None) -> dict:
    return {
        "id": e["email_id"],
        "from": e["from_addr"],
        "to": "",
        "date": e["date"],
        "subject": e["subject"],
        "body": e["body_text"],
        "mailbox": mailbox,
        "attachments": [{"filename": a["filename"], "text": a["text"]} for a in e.get("attachments", [])],
    }


def local_day(iso: str | None) -> str:
    """rules.py stamps detected_at in UTC; show the local calendar day on the timeline."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).astimezone().date().isoformat()
    except ValueError:
        return iso[:10]


def _num(v):
    return None if v is None else (int(v) if float(v).is_integer() else float(v))


def _event_text(ev, latest_notes: str) -> str:
    ct, old, new = ev["change_type"], ev["old_value"], ev["new_value"]
    label = {
        "date_change": "Ship date",
        "quantity_change": "Quantity",
        "price_change": "Unit price",
        "cancellation": "Order cancelled",
        "none": "Supplier update",
        "other": "Update",
    }.get(ct, ct)
    if ct in ("date_change", "quantity_change", "price_change") and new is not None:
        text = f"{label} {old if old is not None else '?'} → {new}"
    elif ct == "none":
        text = f"Supplier replied: {new}" if new else "Supplier replied"
    else:
        text = label
    return f"{text} ({ev['notes']})" if ev["notes"] else text


def order_views(c) -> tuple[list[dict], list[dict]]:
    """Every purchase order in the front end's PurchaseOrder shape, plus the supplier list."""
    rows = c.execute("SELECT * FROM purchase_orders ORDER BY po_number").fetchall()
    events = {}
    for ev in c.execute("SELECT * FROM events ORDER BY id"):
        events.setdefault(ev["po_number"], []).append(ev)
    exceptions = {}
    for ex in c.execute("SELECT * FROM exceptions"):
        exceptions.setdefault(ex["po_number"], []).append(ex)
    latest_ext = {}
    for row in c.execute("SELECT po_number, data FROM extractions ORDER BY email_date, id"):
        if row["po_number"]:
            latest_ext[row["po_number"]] = json.loads(row["data"])
    emails = load_emails()

    orders, suppliers = [], {}
    for r in rows:
        po = r["po_number"]
        exs = sorted(exceptions.get(po, []), key=lambda e: KIND_PRIORITY.index(e["kind"]))
        status = exs[0]["kind"] if exs else DB_STATUS_TO_UI.get(r["status"], r["status"])
        evs = events.get(po, [])
        notes = next((e["notes"] for e in reversed(evs) if e["notes"]), None)
        ext = latest_ext.get(po)
        # Price change: the event row keeps "was -> now"; purchase_orders holds only one price.
        unit_price, new_price = r["unit_price"], None
        if status == "price_change":
            pe = next(
                (e for e in reversed(evs) if e["change_type"] == "price_change" and e["new_value"]), None
            )
            if pe and pe["old_value"] not in (None, "", "None"):
                unit_price, new_price = float(pe["old_value"]), float(pe["new_value"])
            elif pe:
                unit_price = float(pe["new_value"])
        timeline = []
        if r["sent_date"]:
            timeline.append({"date": r["sent_date"], "kind": "sent", "text": "PO sent to supplier"})
        for ev in evs:
            when = emails.get(ev["source_email_id"], {}).get("date") or (ev["created_at"] or "")[:10]
            timeline.append(
                {
                    "date": when,
                    "kind": "reply" if ev["change_type"] == "none" else "change",
                    "text": _event_text(ev, notes or ""),
                    "emailId": ev["source_email_id"],
                }
            )
        for ex in exs:
            timeline.append(
                {
                    "date": local_day(ex["detected_at"]),
                    "kind": "flag",
                    "text": f"Flagged: {ex['kind'].replace('_', ' ')} — {ex['detail']}",
                    "emailId": ex["source_email_id"],
                }
            )
        timeline.sort(key=lambda e: e["date"])
        domain = r["supplier"]
        suppliers.setdefault(domain, supplier_view(domain, r["supplier_email"]))
        if r["supplier_email"] and suppliers[domain]["email"].startswith("@"):
            suppliers[domain]["email"] = r["supplier_email"]
        order = {
            "po": po,
            "supplierId": domain,
            "item": r["item"] or "",
            "qty": _num(r["quantity_ordered"]) or 0,
            "unitPrice": _num(unit_price) if unit_price is not None else 0,
            "currency": r["currency"] or "",
            "sentDate": r["sent_date"] or "",
            "requestedDate": r["requested_date"] or r["original_date"] or "",
            "status": status,
            "events": timeline,
            "lastEmailId": r["last_email_id"],
            "exceptions": [
                {
                    "kind": e["kind"],
                    "detail": e["detail"],
                    "detectedAt": e["detected_at"],
                    "emailId": e["source_email_id"],
                }
                for e in exs
            ],
        }
        if r["quantity_confirmed"] is not None:
            order["qtyConfirmed"] = _num(r["quantity_confirmed"])
        if r["confirmed_date"]:
            order["currentDate"] = r["confirmed_date"]
        if new_price is not None:
            order["newUnitPrice"] = new_price
        if notes:
            order["reason"] = notes
        orders.append(order)
    return orders, list(suppliers.values())


# ---------------------------------------------------------------------- endpoints


@app.get("/api/health")
def health():
    with closing(conn()) as c:
        n = c.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0]
    return {
        "ok": True,
        "llm_configured": bool(os.getenv("LLM_API_KEY")),
        "llm_model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
        "llm_base_url": os.getenv("LLM_BASE_URL") or "OpenAI",
        "gmail_configured": any(m["authorized"] for m in mailbox_store().list()["mailboxes"]),
        "db_path": str(db.DB_PATH),
        "orders": n,
    }


@app.get("/api/gmail/status")
def gmail_status():
    state = mailbox_store().list()
    default = next((m for m in state["mailboxes"] if m["id"] == state["defaultMailboxId"]), None)
    return {"account": default["address"] if default else "",
            "authorized": bool(default and default["authorized"]), "query": state["query"]}


def require_local_management(request: Request):
    """The desktop demo has no server login; reject foreign browser origins."""
    origins = {"http://localhost:3100", "http://127.0.0.1:3100"}
    origin = request.headers.get("origin")
    if (request.url.hostname not in {"localhost", "127.0.0.1"}
            or (origin is not None and origin not in origins)
            or request.headers.get("sec-fetch-site") == "cross-site"):
        raise HTTPException(403, "Mailbox management is available from the local PO Assistant only.")


@app.get("/api/mailboxes")
def list_mailboxes():
    return mailbox_store().list()


class ConnectMailboxRequest(BaseModel):
    mailboxId: str | None = None


@app.post("/api/mailboxes/connect")
def connect_mailbox(request: Request, body: ConnectMailboxRequest):
    require_local_management(request)
    try:
        return oauth_sessions.start(mailbox_store(), body.mailboxId)
    except (ValueError, OSError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/mailboxes/connections/{session_id}")
def mailbox_connection_status(session_id: str):
    try:
        return oauth_sessions.status(session_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/mailboxes/connections/{session_id}/cancel")
def cancel_mailbox_connection(session_id: str, request: Request):
    require_local_management(request)
    try:
        return oauth_sessions.cancel(session_id)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@app.post("/api/mailboxes/{mailbox_id}/default")
def default_mailbox(mailbox_id: str, request: Request):
    require_local_management(request)
    try:
        mailbox_store().set_default(mailbox_id)
        return mailbox_store().list()
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/mailboxes/{mailbox_id}/disconnect")
def disconnect_mailbox(mailbox_id: str, request: Request):
    require_local_management(request)
    if not SYNC_LOCK.acquire(blocking=False):
        raise HTTPException(409, "Wait for the current sync to finish before disconnecting a mailbox.")
    try:
        mailbox_store().disconnect(mailbox_id)
        return mailbox_store().list()
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    finally:
        SYNC_LOCK.release()


@app.get("/api/orders")
def list_orders():
    with closing(conn()) as c:
        orders, suppliers = order_views(c)
    sources = mailbox_store().sources()
    return {
        "orders": orders,
        "suppliers": suppliers,
        "emails": [email_view(e, sources.get(e["email_id"])) for e in load_emails().values()],
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


@app.get("/api/orders/{po}")
def get_order(po: str):
    with closing(conn()) as c:
        orders, suppliers = order_views(c)
        ext = c.execute(
            "SELECT data FROM extractions WHERE po_number = ? ORDER BY email_date DESC, id DESC LIMIT 1", (po,)
        ).fetchone()
    order = next((o for o in orders if o["po"] == po), None)
    if order is None:
        raise HTTPException(404, f"{po} is not tracked")
    from rag.index import mentions_po  # whole PO numbers only: PO-1001 is not PO-100

    emails = load_emails()
    sources = mailbox_store().sources()
    related = [
        email_view(e, sources.get(e["email_id"]))
        for e in emails.values()
        if mentions_po(e, po) or e["email_id"] == order["lastEmailId"]
    ]
    return {
        "order": order,
        "supplier": next(s for s in suppliers if s["id"] == order["supplierId"]),
        "emails": sorted(related, key=lambda e: e["date"]),
        "extraction": json.loads(ext["data"]) if ext else None,
    }


@app.post("/api/po-list")
async def post_po_list(file: UploadFile = File(...)):
    data = await file.read()
    with closing(conn()) as c:
        result = import_po_list(c, file.filename or "po_list.csv", data)
        if result.missing_columns:
            c.rollback()
            raise HTTPException(400, f"missing columns: {', '.join(result.missing_columns)}")
        # The no-reply rule needs the imported sent dates; recompute right away.
        found = sync_exceptions(c, emails=[EmailMessage.from_dict(e) for e in load_emails().values()])
        c.commit()
    return {**result.to_dict(), "exceptions": len(found)}


class SyncRequest(BaseModel):
    source: Literal["auto", "gmail", "samples", "gold"] = "auto"
    since: str = "7d"
    query: str | None = Field(default=None, max_length=500)
    mailboxId: str | None = Field(default=None, max_length=64)


def gold_extract_timed(msg: EmailMessage):
    """Stand-in extractor for UI demos without an LLM key: the reference answers from tests/samples.
    Only used when the client asks for source="gold"; the response says so."""
    from schema import POExtraction

    for p in SAMPLES.glob("*.email.json"):
        if json.loads(p.read_text(encoding="utf-8"))["email_id"] == msg.email_id:
            gold = json.loads(p.with_suffix("").with_suffix(".gold.json").read_text(encoding="utf-8"))
            return [POExtraction.from_dict(g) for g in gold], 0.0
    return [], 0.0


def fetch_gmail(since: str, query: str | None = None, mailbox_id: str | None = None) -> list[EmailMessage]:
    from ingest.fetch_emails import fetch, gmail_service

    store = mailbox_store()
    mailbox = store.get(mailbox_id)
    if not token_available(mailbox["token_path"]):
        raise ValueError("Reconnect this Gmail account in Settings > Mailboxes before syncing.")
    messages = fetch(
        since, service=gmail_service(interactive=False, token_file=Path(mailbox["token_path"])),
        query=os.getenv("GMAIL_QUERY", "") if query is None else query,
        expected_account=mailbox["address"],
    )
    return store.namespace(mailbox["id"], messages)


@app.post("/api/sync")
def sync(req: SyncRequest | None = None):
    if not SYNC_LOCK.acquire(blocking=False):
        raise HTTPException(409, "Another inbox sync is running. Wait for it to finish.")
    try:
        req = req or SyncRequest()
        mid = None
        if req.source in ("auto", "gmail"):
            mid = req.mailboxId or mailbox_store().list()["defaultMailboxId"]
            req = req.model_copy(update={"mailboxId": mid})
        with closing(conn()) as c:
            try:
                result = _sync(req, c)
            except HTTPException as e:
                if mid:
                    mailbox_store().record_sync(mid, str(e.detail))
                raise
            if mid:
                mailbox_store().record_sync(mid)
                result["mailboxId"] = mid
                result["mailbox"] = mailbox_store().get(mid)["address"]
            return result
    finally:
        SYNC_LOCK.release()


def _sync(req: SyncRequest, c):
    from google.auth.exceptions import RefreshError
    from ingest.fetch_emails import since_query
    from openai import APIError
    from extract import ExtractionError

    req = req or SyncRequest()
    known = {r[0] for r in c.execute("SELECT DISTINCT source_email_id FROM extractions")} | set(load_emails())
    source, note = req.source, ""
    msgs: list[EmailMessage] = []
    if source in ("auto", "gmail"):
        try:
            since_query(req.since)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        try:
            if req.mailboxId:
                msgs = fetch_gmail(req.since, req.query, req.mailboxId)
            else:
                msgs = fetch_gmail(req.since, req.query)
            source = "gmail"
        except RefreshError as e:
            raise HTTPException(
                401, "Gmail authorization has expired or was revoked. Reconnect the account in "
                "Settings > Mailboxes. For the legacy CLI setup, run python ingest/fetch_emails.py --auth-only."
            ) from e
        except (RuntimeError, ValueError, FileNotFoundError, ImportError) as e:
            raise HTTPException(503, str(e)) from e
        except Exception as e:
            raise HTTPException(
                502, "Gmail could not be read. Check the backend internet connection and retry."
            ) from e
    if source in ("samples", "gold"):
        msgs = rp.load_offline(SAMPLES)
    new = [m for m in msgs if m.email_id not in known]

    def snapshot():
        return {o["po"]: (o["status"], o.get("currentDate"), o.get("qtyConfirmed"),
                          o.get("newUnitPrice"), o.get("lastEmailId"))
                for o in order_views(c)[0]}

    before = snapshot()
    if new:
        if source != "gold" and not os.getenv("LLM_API_KEY"):
            raise HTTPException(
                503, "Gmail was read, but the extraction model is not configured. "
                "Set LLM_API_KEY and the model endpoint on the backend, then retry.",
            )
        try:
            summary = rp.run(
                new, reset=False, skip_processed=True,
                extractor=gold_extract_timed if source == "gold" else None,
            )
        except (APIError, ExtractionError) as e:
            raise HTTPException(
                503, "Order extraction could not finish. Check the model service and retry. "
                "Completed emails are saved; remaining emails will be retried."
            ) from e
        if source == "gold":
            note = "reference answers used instead of the LLM (demo mode)"
    else:
        found = sync_exceptions(c, emails=[EmailMessage.from_dict(e) for e in load_emails().values()])
        c.commit()
        summary = {"emails": 0, "pos": 0, "exceptions": len(found), "avg_seconds": 0.0}
    after = snapshot()
    changed = [po for po, st in after.items() if before.get(po) != st]
    return {
        "source": source,
        "note": note,
        "newEmails": summary["emails"],
        "matchedEmails": len(msgs),
        "poUpdates": summary["pos"],
        "exceptions": summary["exceptions"],
        "avgSeconds": round(summary["avg_seconds"], 2),
        "changed": changed,
        "syncedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    buyerName: str | None = Field(default=None, max_length=100)


def draft_view(d) -> dict:
    """A schema.FollowUpDraft in the front end's FollowUpDraft shape (data/sample.ts)."""
    return {
        "id": d.draft_id,
        "po": d.po_number,
        "to": d.to,
        "subject": d.subject,
        "body": d.body,
        "why": d.why,
        "sources": [{"type": "rule", "ruleId": r} for r in d.rule_ids]
        + [{"type": "email", "emailId": e} for e in d.email_ids],
    }


@app.post("/api/chat")
def post_chat(req: ChatRequest):
    """Ask the expediter clone. The page sends the whole conversation; nothing is stored."""
    from agent.chat import chat
    from agent.llm import LLMError

    if not os.getenv("LLM_API_KEY"):
        raise HTTPException(
            503, "The chat model is not configured. Set LLM_API_KEY and the model endpoint on the backend."
        )
    try:
        with closing(conn()) as c:
            result = chat(c, [m.model_dump() for m in req.messages], buyer_name=req.buyerName)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except LLMError as e:
        raise HTTPException(502, "The chat model could not answer. Check the model service and retry.") from e
    return {
        "answer": result["answer"],
        "toolsUsed": result["tools_used"],
        "sources": result["sources"],
        "drafts": [draft_view(d) for d in result["drafts"]],
    }


class PreviewRulesRequest(BaseModel):
    text: str = Field(max_length=60_000)
    filename: str | None = Field(default=None, max_length=200)


class RuleIn(BaseModel):
    title: str = Field(default="", max_length=200)
    text: str = Field(max_length=2000)
    kinds: list[str] = Field(default_factory=list, max_length=10)


class SaveRulesRequest(BaseModel):
    rules: list[RuleIn] = Field(min_length=1, max_length=50)
    source: str | None = Field(default=None, max_length=200)
    buyerName: str | None = Field(default=None, max_length=100)


class RulePatch(BaseModel):
    enabled: bool | None = None
    title: str | None = Field(default=None, max_length=200)
    text: str | None = Field(default=None, max_length=2000)
    kinds: list[str] | None = Field(default=None, max_length=10)


def _uploaded_id(rule_id: str) -> str:
    if not re.fullmatch(r"U\d+", rule_id):
        raise HTTPException(403, "Built-in playbook rules are read-only; only uploaded rules can change.")
    return rule_id


@app.get("/api/playbook")
def get_playbook():
    """Built-in rules (agent/buyer_playbook.md) first, then every uploaded rule with `enabled`."""
    from agent.playbook import load_playbook
    from agent.uploads import list_uploaded

    with closing(conn()) as c:
        uploaded = list_uploaded(c)
    return {"rules": [{**r.to_dict(), "enabled": True} for r in load_playbook()] + uploaded}


@app.post("/api/playbook/preview")
def preview_playbook_rules(req: PreviewRulesRequest, request: Request):
    """Split pasted text or a .md/.txt file into rules. Nothing is saved."""
    from agent.uploads import UploadError, preview_rules

    require_local_management(request)
    try:
        return preview_rules(req.text, use_llm=bool(os.getenv("LLM_API_KEY")))
    except UploadError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/playbook/rules")
def save_playbook_rules(req: SaveRulesRequest, request: Request):
    """Save the rules the buyer reviewed in the preview."""
    from agent.uploads import UploadError, save_rules

    require_local_management(request)
    source = (f"Uploaded by {req.buyerName or 'the buyer'} from {req.source or 'pasted text'}, "
              f"{date.today().isoformat()}")
    with closing(conn()) as c:
        try:
            saved = save_rules(c, [r.model_dump() for r in req.rules], source=source)
        except UploadError as e:
            raise HTTPException(422, str(e)) from e
    return {"saved": saved}


@app.patch("/api/playbook/rules/{rule_id}")
def patch_playbook_rule(rule_id: str, body: RulePatch, request: Request):
    from agent.uploads import UploadError, update_rule

    require_local_management(request)
    with closing(conn()) as c:
        try:
            return update_rule(c, _uploaded_id(rule_id), **body.model_dump())
        except KeyError as e:
            raise HTTPException(404, f"{rule_id} is not an uploaded rule.") from e
        except UploadError as e:
            raise HTTPException(422, str(e)) from e


@app.delete("/api/playbook/rules/{rule_id}")
def delete_playbook_rule(rule_id: str, request: Request):
    from agent.uploads import delete_rule

    require_local_management(request)
    with closing(conn()) as c:
        try:
            delete_rule(c, _uploaded_id(rule_id))
        except KeyError as e:
            raise HTTPException(404, f"{rule_id} is not an uploaded rule.") from e
    return {"ok": True}


@app.get("/api/eval-runs")
def eval_runs():
    keep = (
        "label",
        "time",
        "model",
        "base_url",
        "n_emails",
        "n_gold_pos",
        "missed",
        "extra",
        "overall",
        "m1_overall",
        "avg_seconds",
        "field_accuracy",
    )
    return [{k: r.get(k) for k in keep} for r in load_runs()]


@app.post("/api/reset")
def reset():
    if not SYNC_LOCK.acquire(blocking=False):
        raise HTTPException(409, "Wait for the inbox sync to finish before resetting.")
    try:
        with closing(conn()) as c:
            db.reset(c)
        for f in (rp.EMAILS_OUT, rp.EXTRACTIONS_OUT):
            f.unlink(missing_ok=True)
        return {"ok": True}
    finally:
        SYNC_LOCK.release()
