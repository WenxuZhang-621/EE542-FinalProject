"""Streamlit dashboard.  Run:  streamlit run dashboard/app.py"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import connect  # noqa: E402

st.set_page_config(page_title="PO Follow-Up", layout="wide")
st.title("PO Follow-Up Dashboard")

conn = connect()
df = pd.read_sql_query("SELECT * FROM purchase_orders ORDER BY updated_at DESC", conn)

# --- summary ---
c1, c2, c3 = st.columns(3)
c1.metric("Delayed", int((df["status"] == "delayed").sum()) if len(df) else 0)
c2.metric("Out of stock", int((df["status"] == "out_of_stock").sum()) if len(df) else 0)
c3.metric("Pending", int((df["status"] == "pending").sum()) if len(df) else 0)

# --- filter + table ---
status = st.multiselect("Status", sorted(df["status"].unique()) if len(df) else [])
view = df[df["status"].isin(status)] if status else df


def _highlight(row):
    return ["background-color: #ffd6d6" if row["status"] == "delayed" else ""] * len(row)


st.dataframe(view.style.apply(_highlight, axis=1), use_container_width=True)

# --- history ---
po = st.selectbox("PO history", view["po_number"].tolist() if len(view) else [])
if po:
    ev = pd.read_sql_query("SELECT * FROM events WHERE po_number = ? ORDER BY created_at", conn, params=(po,))
    st.table(ev)
