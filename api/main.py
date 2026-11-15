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
    GET  /api/eval-runs       accuracy runs from extract/eval.py
    POST /api/reset           empty the demo database
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "extract", ROOT / "dashboard", ROOT / "ingest"):
    sys.path.insert(0, str(p))
import db  # noqa: E402
import run_pipeline as rp  # noqa: E402
from api.po_list import import_po_list  # noqa: E402
from eval import load_runs  # noqa: E402  (extract/eval.py)
from rules import RULE_KINDS, sync_exceptions  # noqa: E402
from schema import EmailMessage  # noqa: E402

SAMPLES = ROOT / "tests" / "samples"
# Exceptions decide the status shown in the UI; the most urgent kind wins.
KIND_PRIORITY = ["delayed", "out_of_stock", "partial", "price_change", "no_reply"]
DB_STATUS_TO_UI = {"pending": "awaiting"}

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


def load_emails() -> dict[str, dict]:
    if not rp.EMAILS_OUT.exists():
        return {}
    return {d["email_id"]: d for d in json.loads(rp.EMAILS_OUT.read_text(encoding="utf-8"))}


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


def email_view(e: dict) -> dict:
    return {
        "id": e["email_id"],
        "from": e["from_addr"],
        "to": "",
        "date": e["date"],
        "subject": e["subject"],
        "body": e["body_text"],
        "attachments": [{"filename": a["filename"], "text": a["text"]} for a in e.get("attachments", [])],
    }


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
                    "date": (ex["detected_at"] or "")[:10],
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
    c = conn()
    n = c.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0]
    return {
        "ok": True,
        "llm_configured": bool(os.getenv("LLM_API_KEY")),
        "llm_model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
        "llm_base_url": os.getenv("LLM_BASE_URL") or "OpenAI",
        "gmail_configured": (ROOT / "credentials.json").exists(),
        "db_path": str(db.DB_PATH),
        "orders": n,
    }


@app.get("/api/orders")
def list_orders():
    orders, suppliers = order_views(conn())
    return {
        "orders": orders,
        "suppliers": suppliers,
        "emails": [email_view(e) for e in load_emails().values()],
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


@app.get("/api/orders/{po}")
def get_order(po: str):
    c = conn()
    orders, suppliers = order_views(c)
    order = next((o for o in orders if o["po"] == po), None)
    if order is None:
        raise HTTPException(404, f"{po} is not tracked")
    emails = load_emails()
    related = [
        email_view(e)
        for e in emails.values()
        if po.lower() in (e["subject"] + e["body_text"]).lower() or e["email_id"] == order["lastEmailId"]
    ]
    ext = c.execute(
        "SELECT data FROM extractions WHERE po_number = ? ORDER BY email_date DESC, id DESC LIMIT 1", (po,)
    ).fetchone()
    return {
        "order": order,
        "supplier": next(s for s in suppliers if s["id"] == order["supplierId"]),
        "emails": sorted(related, key=lambda e: e["date"]),
        "extraction": json.loads(ext["data"]) if ext else None,
    }


@app.post("/api/po-list")
async def post_po_list(file: UploadFile = File(...)):
    data = await file.read()
    c = conn()
    result = import_po_list(c, file.filename or "po_list.csv", data)
    if result.missing_columns:
        c.rollback()
        raise HTTPException(400, f"missing columns: {', '.join(result.missing_columns)}")
    # The no-reply rule needs the imported sent dates; recompute right away.
    found = sync_exceptions(c, emails=[EmailMessage.from_dict(e) for e in load_emails().values()])
    c.commit()
    return {**result.to_dict(), "exceptions": len(found)}


class SyncRequest(BaseModel):
    source: str = "auto"  # auto | gmail | samples | gold
    since: str = "7d"


def gold_extract_timed(msg: EmailMessage):
    """Stand-in extractor for UI demos without an LLM key: the reference answers from tests/samples.
    Only used when the client asks for source="gold"; the response says so."""
    from schema import POExtraction

    for p in SAMPLES.glob("*.email.json"):
        if json.loads(p.read_text(encoding="utf-8"))["email_id"] == msg.email_id:
            gold = json.loads(p.with_suffix("").with_suffix(".gold.json").read_text(encoding="utf-8"))
            return [POExtraction.from_dict(g) for g in gold], 0.0
    return [], 0.0


def fetch_gmail(since: str) -> list[EmailMessage]:
    from fetch_emails import fetch  # ingest/fetch_emails.py (A)

    return fetch(since)


@app.post("/api/sync")
def sync(req: SyncRequest | None = None):
    req = req or SyncRequest()
    c = conn()
    known = {r[0] for r in c.execute("SELECT DISTINCT source_email_id FROM extractions")} | set(load_emails())
    source, note = req.source, ""
    msgs: list[EmailMessage] = []
    if source in ("auto", "gmail"):
        try:
            msgs, source = fetch_gmail(req.since), "gmail"
        except (NotImplementedError, FileNotFoundError, ImportError) as e:
            if req.source == "gmail":
                raise HTTPException(503, f"Gmail is not available: {e}")
            note = f"Gmail not configured ({e.__class__.__name__}); read the sample inbox instead"
            source = "samples"
    if source in ("samples", "gold"):
        msgs = rp.load_offline(SAMPLES)
    new = [m for m in msgs if m.email_id not in known]

    before = {o["po"]: (o["status"], o.get("currentDate")) for o in order_views(c)[0]}
    if new and source == "gold":
        real = rp.extract_timed
        rp.extract_timed = gold_extract_timed  # process-wide for this call only
        try:
            summary = rp.run(new, reset=False)
        finally:
            rp.extract_timed = real
        note = "reference answers used instead of the LLM (demo mode)"
        c = conn()
    elif new:
        if not os.getenv("LLM_API_KEY"):
            raise HTTPException(
                503,
                "LLM_API_KEY is not set; new emails cannot be extracted. "
                "Copy .env.example to .env and fill it in, then restart the API.",
            )
        summary = rp.run(new, reset=False)
        c = conn()
    else:
        found = sync_exceptions(c, emails=[EmailMessage.from_dict(e) for e in load_emails().values()])
        c.commit()
        summary = {"emails": 0, "pos": 0, "exceptions": len(found), "avg_seconds": 0.0}
    after = {o["po"]: (o["status"], o.get("currentDate")) for o in order_views(c)[0]}
    changed = [po for po, st in after.items() if before.get(po) != st]
    return {
        "source": source,
        "note": note,
        "newEmails": len(new),
        "poUpdates": summary["pos"],
        "exceptions": summary["exceptions"],
        "avgSeconds": round(summary["avg_seconds"], 2),
        "changed": changed,
    }


@app.get("/api/eval-runs")
def eval_runs():
    keep = (
        "label",
        "time",
        "model",
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
    db.reset(conn())
    for f in (rp.EMAILS_OUT, rp.EXTRACTIONS_OUT):
        f.unlink(missing_ok=True)
    return {"ok": True}
