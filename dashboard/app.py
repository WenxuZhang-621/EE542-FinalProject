"""PO Follow-Up Assistant demo page.  Run:  streamlit run dashboard/app.py"""
import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "extract", ROOT / "dashboard"):
    sys.path.insert(0, str(p))
import db  # noqa: E402
from eval import FIELDS, load_runs, run_eval, RUNS_PATH  # noqa: E402
from extract import model_name  # noqa: E402
from run_pipeline import EMAILS_OUT, EXTRACTIONS_OUT, load_offline, run  # noqa: E402

SAMPLES = ROOT / "tests" / "samples"
MILESTONE = "M1"

STATUS_LABEL = {"delayed": "Delayed", "out_of_stock": "Out of stock", "partial": "Partial",
                "price_change": "Price change", "confirmed": "Confirmed", "pending": "Pending"}
# status -> (background, text); every colored cell also carries the status word
STATUS_STYLE = {"delayed": ("#FCEBEB", "#791F1F"), "out_of_stock": ("#FCEBEB", "#791F1F"),
                "partial": ("#FAEEDA", "#633806"), "price_change": ("#FAEEDA", "#633806"),
                "confirmed": ("#EAF3DE", "#27500A")}
ROADMAP = [
    ("M1", "Extract PO updates from sample supplier emails (EN + 中文) into a dashboard"),
    ("M2", "Live Gmail inbox, PO list import, alert when a supplier never replies"),
    ("M3", "Expert-buyer clone on our cloud GPU: follow-up drafts and Q&A with sources"),
    ("M4", "Full evaluation: accuracy, recall, GPU vs API speed and cost"),
]

st.set_page_config(page_title="PO Follow-Up Assistant", layout="wide")


def load_emails() -> dict:
    if not EMAILS_OUT.exists():
        return {}
    return {d["email_id"]: d for d in json.loads(EMAILS_OUT.read_text(encoding="utf-8"))}


def show_email(e: dict) -> None:
    st.markdown(f"**From:** {e['from_addr']}  \n**Subject:** {e['subject']}  \n**Date:** {e['date']}")
    st.text(e["body_text"])
    for a in e.get("attachments", []):
        with st.expander(f"Attachment: {a['filename']}"):
            st.text(a["text"])


def fmt_date(d):
    # A delay with no new date yet arrives as None or NaN (e.g. "mid-December, day not set").
    return "—" if d is None or pd.isna(d) else pd.to_datetime(d).strftime("%b %d")


def num(v, missing="?") -> str:
    return missing if v is None or pd.isna(v) else f"{v:g}"


def one_line(r) -> str:
    """Plain-English summary of what is wrong with one PO."""
    s = r["status"]
    if s == "delayed":
        msg = f"ship date {fmt_date(r['original_date'])} → {fmt_date(r['confirmed_date'])}"
    elif s == "partial":
        msg = f"only {num(r['quantity_confirmed'])} of {num(r['quantity_ordered'])} confirmed"
    elif s == "out_of_stock":
        msg = "supplier cannot supply"
    elif s == "price_change":
        msg = f"new unit price {num(r['unit_price'])} {r['currency'] or ''}"
    else:
        msg = STATUS_LABEL.get(s, s)
    why = f" — *{r['reason']}*" if r.get("reason") else ""
    return f"**{r['po_number']}** · {r['supplier']} · {msg}{why}"


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("PO Follow-Up Assistant")
    st.caption(f"Milestone {MILESTONE[1:]} demo · offline sample inbox ({len(list(SAMPLES.glob('*.email.json')))} emails)")
    key_ok = bool(os.getenv("LLM_API_KEY"))
    st.markdown(f"**Model:** `{model_name()}`  \n"
                f"**Endpoint:** {os.getenv('LLM_BASE_URL') or 'OpenAI API'}")
    if not key_ok:
        st.error("LLM_API_KEY is missing. Add it to .env, then restart the page.")

    st.subheader("Run")
    if st.button("Process sample inbox", type="primary", disabled=not key_ok, width="stretch"):
        with st.status("Reading supplier emails…", expanded=True) as box:
            s = run(load_offline(SAMPLES), reset=True,
                    on_email=lambda i, n, m: box.write(f"{i + 1}/{n} · {m.subject}"))
            box.update(label=f"Done: {s['emails']} emails → {s['pos']} PO updates "
                             f"({s['avg_seconds']:.1f}s per email)", state="complete")
    label = st.text_input("Accuracy test label", value=MILESTONE)
    if st.button("Run accuracy test", disabled=not key_ok, width="stretch"):
        with st.spinner("Comparing the model's answers with the correct answers…"):
            r = run_eval(label)
        st.success(f"{label}: {r['overall']:.0%} of fields correct")
    if st.button("Reset demo data", width="stretch"):
        db.reset(db.connect())
        for f in (EMAILS_OUT, EXTRACTIONS_OUT):
            f.unlink(missing_ok=True)
        st.rerun()

    st.subheader("Roadmap")
    for m, text in ROADMAP:
        mark = "✅" if m == MILESTONE else "⬜"
        st.markdown(f"{mark} **{m}** · {text}")

# ------------------------------------------------------------------ data
conn = db.connect()
df = pd.read_sql_query(
    "SELECT p.*, (SELECT notes FROM events e WHERE e.po_number = p.po_number "
    "             ORDER BY e.id DESC LIMIT 1) AS reason "
    "FROM purchase_orders p ORDER BY p.po_number", conn)
emails = load_emails()
runs = load_runs()

tab_po, tab_check, tab_acc = st.tabs(["PO dashboard", "Extraction check", "Accuracy"])

# ------------------------------------------------------------------ PO dashboard
with tab_po:
    if df.empty:
        st.info("No orders yet. Click **Process sample inbox** in the sidebar.")
    else:
        n = lambda *s: int(df["status"].isin(s).sum())  # noqa: E731
        c = st.columns(5)
        c[0].metric("POs tracked", len(df))
        c[1].metric("Delayed", n("delayed"))
        c[2].metric("Short or out of stock", n("partial", "out_of_stock"))
        c[3].metric("Price change", n("price_change"))
        c[4].metric("Confirmed", n("confirmed"))

        issues = df[~df["status"].isin(["confirmed", "pending"])]
        if len(issues):
            st.subheader(f"Needs attention ({len(issues)})")
            for _, r in issues.iterrows():
                line = one_line(r)
                (st.error if r["status"] in ("delayed", "out_of_stock") else st.warning)(line)

        exc = pd.read_sql_query(
            "SELECT po_number AS PO, kind AS Exception, detail AS Detail, "
            "detected_at AS 'First seen', source_email_id AS Email "
            "FROM exceptions ORDER BY po_number, kind", conn)
        if len(exc):
            st.subheader(f"Exceptions against the PO list ({len(exc)})")
            st.caption("From rules.py: the supplier's latest update compared with the "
                       "ordered date, quantity and price, plus orders with no reply.")
            st.dataframe(exc, hide_index=True, width="stretch")

        st.subheader("All purchase orders")
        view = pd.DataFrame({
            "PO": df["po_number"],
            "Supplier": df["supplier"],
            "Status": df["status"].map(lambda s: STATUS_LABEL.get(s, s)),
            "Ship date (ordered)": df["original_date"].fillna("—"),
            "Ship date (now)": df["confirmed_date"].fillna("—"),
            "Qty ordered": df["quantity_ordered"].map(lambda v: num(v, "—")),
            "Qty confirmed": df["quantity_confirmed"].map(lambda v: num(v, "—")),
            "Unit price": ["—" if pd.isna(p) else f"{p:g} {'' if pd.isna(c) else c}".strip()
                           for p, c in zip(df["unit_price"], df["currency"])],
        })

        def colour(row):
            bg, fg = STATUS_STYLE.get(df.loc[row.name, "status"], ("", ""))
            return [f"background-color: {bg}; color: {fg}" if bg else ""] * len(row)

        st.dataframe(view.style.apply(colour, axis=1), hide_index=True, width="stretch")

        po = st.selectbox("Open a PO", df["po_number"].tolist())
        left, right = st.columns(2)
        with left:
            st.markdown("**History**")
            ev = pd.read_sql_query(
                "SELECT created_at AS time, change_type AS change, old_value AS was, "
                "new_value AS now, notes AS reason, source_email_id AS email "
                "FROM events WHERE po_number = ? ORDER BY id", conn, params=(po,))
            st.dataframe(ev, hide_index=True, width="stretch")
        with right:
            st.markdown("**Source email**")
            eid = df.loc[df["po_number"] == po, "last_email_id"].iloc[0]
            if eid in emails:
                show_email(emails[eid])

# ------------------------------------------------------------------ extraction check
with tab_check:
    if not runs:
        st.info("No accuracy test yet. Click **Run accuracy test** in the sidebar.")
    else:
        run_labels = [f"{r['label']} · {r['time']}" for r in runs]
        pick = st.selectbox("Test run", run_labels, index=len(runs) - 1)
        r = runs[run_labels.index(pick)]
        sample = st.selectbox("Sample email", [s["sample"] for s in r["samples"]])
        s = next(x for x in r["samples"] if x["sample"] == sample)
        left, right = st.columns(2)
        with left:
            st.markdown("**Supplier email**")
            show_email(json.loads((SAMPLES / f"{sample}.email.json").read_text(encoding="utf-8")))
        with right:
            st.markdown(f"**What the model extracted** · {s['seconds']:.1f}s")
            for g in s["gold"]:
                p = next((x for x in s["pred"] if x.get("po_number") == g.get("po_number")), None)
                st.markdown(f"`{g['po_number']}`" + ("" if p else " — **missed by the model**"))
                rows = [{"Field": f, "Correct answer": g.get(f),
                         "Model": None if p is None else p.get(f),
                         "Match": "✓" if p is not None and p.get(f) == g.get(f) else "✗"}
                        for f in FIELDS + ["notes"]]
                t = pd.DataFrame(rows).astype(str).replace("None", "—")
                t.loc[t["Field"] == "notes", "Match"] = "(not scored)"
                st.dataframe(t.style.apply(
                    lambda row: ["background-color: #FCEBEB; color: #791F1F"
                                 if row["Match"] == "✗" else ""] * len(row), axis=1),
                    hide_index=True, width="stretch")

# ------------------------------------------------------------------ accuracy
with tab_acc:
    if not runs:
        st.info("No accuracy test yet. Click **Run accuracy test** in the sidebar.")
    else:
        last = runs[-1]
        c = st.columns(5)
        # Only a run on the same emails is a fair comparison.
        prev = next((x for x in reversed(runs[:-1]) if x["n_emails"] == last["n_emails"]), None)
        c[0].metric("Fields correct", f"{last['overall']:.0%}",
                    delta=None if prev is None else f"{(last['overall'] - prev['overall']) * 100:+.1f} pts vs {prev['label']}")
        c[4].metric("On the 6 M1 emails",
                    "—" if last["m1_overall"] is None else f"{last['m1_overall']:.0%}")
        c[1].metric("Test emails", last["n_emails"])
        c[2].metric("POs in the answers", f"{last['n_gold_pos'] - last['missed']} of {last['n_gold_pos']} found")
        c[3].metric("Seconds per email", f"{last['avg_seconds']:.1f}")
        st.caption(f"Latest run: {last['label']} · {last['time']} · model `{last['model']}`")

        st.subheader("Accuracy by field")
        fa = pd.DataFrame({"Field": list(last["field_accuracy"]),
                           "Accuracy": list(last["field_accuracy"].values())})
        st.dataframe(fa, hide_index=True, width="stretch", column_config={
            "Accuracy": st.column_config.ProgressColumn(
                "Accuracy", min_value=0.0, max_value=1.0, format="percent")})

        st.subheader("Every run so far")
        hist = pd.DataFrame([{"Run": x["label"], "Time": x["time"], "Model": x["model"],
                              "Emails": x["n_emails"], "Fields correct": x["overall"],
                              "On the 6 M1 emails": x["m1_overall"],
                              "Seconds per email": round(x["avg_seconds"], 2)} for x in runs])
        st.dataframe(hist, hide_index=True, width="stretch", column_config={
            "Fields correct": st.column_config.ProgressColumn(
                "Fields correct", min_value=0.0, max_value=1.0, format="percent")})
        st.caption(f"Stored in {RUNS_PATH.relative_to(ROOT)}; each milestone adds a row. Every run is "
                   f"scored on the same {len(FIELDS)} fields with the current correct answers.")
