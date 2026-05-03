"""
Streamlit demo UI (optional) for semantic drift ingestion.

Run:
  cd backend
  streamlit run scripts/semantic_drift_demo_ui.py

Requires: pip install streamlit requests
Set API base if needed: export SEMANTIC_DRIFT_API=http://127.0.0.1:8000/api/semantic-drift
"""

from __future__ import annotations

import os

import requests
import streamlit as st

API = os.environ.get("SEMANTIC_DRIFT_API", "http://127.0.0.1:8000/api/semantic-drift")


def main() -> None:
    st.set_page_config(page_title="Semantic Drift Demo", layout="wide")
    st.title("Baseline-driven semantic drift (demo)")
    st.caption("Calls FastAPI `/api/semantic-drift/*` — data persisted in ChromaDB on the server.")

    ds = st.text_input("dataset_name", value="fashion_sales_demo")

    st.subheader("1) Create baseline")
    b_file = st.file_uploader("Baseline CSV", type=["csv"], key="bl")
    if st.button("Create baseline") and b_file:
        files = {"file": (b_file.name, b_file.getvalue(), "text/csv")}
        data = {"dataset_name": ds, "created_by": "streamlit"}
        r = requests.post(f"{API}/baseline/create", files=files, data=data, timeout=120)
        st.json(r.json())

    st.subheader("2) Ingest new CSV")
    u_file = st.file_uploader("Upload CSV", type=["csv"], key="up")
    if st.button("Run ingest") and u_file:
        files = {"file": (u_file.name, u_file.getvalue(), "text/csv")}
        data = {"dataset_name": ds}
        r = requests.post(f"{API}/ingest", files=files, data=data, timeout=120)
        st.json(r.json())

    if st.button("Refresh tables"):
        sales = requests.get(f"{API}/sales", timeout=60)
        qu = requests.get(f"{API}/quarantine", timeout=60)
        st.write("sales", sales.json())
        st.write("quarantine", qu.json())


if __name__ == "__main__":
    main()
