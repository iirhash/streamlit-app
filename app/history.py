# app/history.py
# ── History page ───────────────────────────────────────────────
# Shows all past records with filters and download option

import streamlit as st
import pandas as pd
import os
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime


from config.settings import TOOLS, CSV_FILE


@st.cache_data(ttl=30)
def load_data():
    try:
        df = pd.read_csv(CSV_FILE)
        df["datetime"] = pd.to_datetime(df["datetime"])
        return df
    except FileNotFoundError:
        return pd.DataFrame(columns=[
            "datetime","technician","employee_id","asset_id",
            "tool","value","unit","min","max","status","defect","notes","photo"
        ])


def show():
    st.markdown("## 🗂 Measurement History")
    st.caption("All recorded readings from all tools and assets.")
    st.divider()

    df = load_data()

    if df.empty:
        st.info("📭 No records yet. Submit readings using the **Measurement Input** page first.")
        return

    # ── Filters ────────────────────────────────────────────────
    f1, f2, f3, f4 = st.columns(4)
    tool_filter   = f1.selectbox("Tool",   ["All"] + list(TOOLS.keys()))
    asset_filter  = f2.text_input("Search Asset ID", placeholder="e.g. LRT-C12")
    status_filter = f3.selectbox("Status", ["All", "Within Range", "Out of Range"])
    defect_filter = f4.selectbox("Defect", ["All","none","crack","wear","corrosion","other"])

    # Apply filters
    filtered = df.copy()
    if tool_filter   != "All":
        filtered = filtered[filtered["tool"] == tool_filter]
    if asset_filter:
        filtered = filtered[filtered["asset_id"].str.contains(asset_filter, case=False, na=False)]
    if status_filter != "All":
        filtered = filtered[filtered["status"] == status_filter]
    if defect_filter != "All":
        filtered = filtered[filtered["defect"] == defect_filter]

    st.caption(f"Showing {len(filtered)} of {len(df)} records")

    # ── Table ──────────────────────────────────────────────────
    def highlight_hist(row):
        if row["status"] == "Out of Range":
            return ["background-color:#FFF8F8"] * len(row)
        return ["background-color:#F6FDF9"] * len(row)

    hist_cols = ["datetime","technician","employee_id","asset_id",
                 "tool","value","unit","min","max","status","defect","notes"]
    hist_cols = [c for c in hist_cols if c in filtered.columns]

    st.dataframe(
        filtered[hist_cols].sort_values("datetime", ascending=False)
            .style.apply(highlight_hist, axis=1), height=480,
    )

    # ── Download ───────────────────────────────────────────────
    csv_data = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download CSV",
        data=csv_data,
        file_name=f"condition_records_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )
