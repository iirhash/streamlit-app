# app/dashboard.py
# ── Dashboard page ─────────────────────────────────────────────
# Shows charts, gauges and summaries of all condition records

import streamlit as st
import pandas as pd
import plotly.express as px
import os
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime
from config.settings import TOOLS, MULTIMETER, CSV_FILE

ALL_TOOLS = {**MULTIMETER, **TOOLS}


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
    st.markdown("## 📊 Condition Monitoring Dashboard")
    st.caption(f"🟢 Live — Last updated: {datetime.now().strftime('%d %b %Y, %H:%M:%S')}")
    st.divider()

    df = load_data()

    if df.empty:
        st.info("📭 No data yet. Submit readings using the **Measurement Input** page first.")
        return

    # ── Metric cards ───────────────────────────────────────────
    total   = len(df)
    ok      = len(df[df["status"] == "Within Range"])
    out     = len(df[df["status"] == "Out of Range"])
    rate    = round((ok / total) * 100, 1) if total > 0 else 0
    defects = len(df[df["defect"] != "none"]) if "defect" in df.columns else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Readings",  total)
    c2.metric("✅ Within Range",  f"{rate}%",              delta=f"{ok} readings",  delta_color="normal")
    c3.metric("❌ Out of Range",  f"{round(100-rate,1)}%", delta=f"-{out}",         delta_color="inverse")
    c4.metric("🔍 Defects Found", defects)

    st.divider()

    # ── Latest reading per tool ────────────────────────────────
    st.markdown("#### Latest Reading per Tool")
    gauge_cols = st.columns(len(ALL_TOOLS))

    for idx, (tool_name, cfg) in enumerate(ALL_TOOLS.items()):
        tool_df = df[df["tool"] == tool_name]
        with gauge_cols[idx]:
            st.markdown(f"**{tool_name.split(' ',1)[0]}**")
            st.caption(tool_name.split(' ',1)[1] if ' ' in tool_name else tool_name)
            if not tool_df.empty:
                val      = tool_df.sort_values("datetime").iloc[-1]["value"]
                in_range = cfg["min"] <= val <= cfg["max"]
                pct      = min(100, max(0, int((val - cfg["min"]) / max(cfg["max"] - cfg["min"], 1) * 100)))
                color    = "#0A8A72" if in_range else "#C9382A"
                st.markdown(
                    f'<div style="font-size:22px;font-weight:600;color:{color}">'
                    f'{val:.1f} <span style="font-size:13px;color:#6B7A99">{cfg["unit"]}</span></div>',
                    unsafe_allow_html=True,
                )
                st.progress(pct)
                st.caption(f"Range: {cfg['min']}–{cfg['max']} {cfg['unit']}")
                st.success("OK") if in_range else st.error("OUT")
            else:
                st.markdown('<div style="font-size:18px;color:#B4B2A9">— —</div>', unsafe_allow_html=True)
                st.caption(f"Range: {cfg['min']}–{cfg['max']} {cfg['unit']}")
                st.caption("No data yet")

    st.divider()

    # ── Charts ─────────────────────────────────────────────────
    chart1, chart2 = st.columns([1.3, 0.7])

    with chart1:
        st.markdown("**Pass Rate by Tool**")
        tool_summary = []
        for tool_name in ALL_TOOLS:
            tool_df = df[df["tool"] == tool_name]
            if not tool_df.empty:
                total_t = len(tool_df)
                ok_t    = len(tool_df[tool_df["status"] == "Within Range"])
                tool_summary.append({
                    "Tool":       tool_name,
                    "Pass Rate %": round((ok_t / total_t) * 100, 1)
                })
        if tool_summary:
            ts_df         = pd.DataFrame(tool_summary)
            ts_df["color"] = ts_df["Pass Rate %"].apply(
                lambda x: "#0A8A72" if x >= 75 else ("#E8920A" if x >= 50 else "#C9382A")
            )
            fig = px.bar(ts_df, x="Tool", y="Pass Rate %",
                         color="color", color_discrete_map="identity")
            fig.update_layout(
                height=260, margin=dict(l=0,r=0,t=10,b=0),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                xaxis=dict(showgrid=False, tickfont=dict(size=10)),
                yaxis=dict(showgrid=True, gridcolor="#F0F2F7", range=[0,100], ticksuffix="%"),
            )
            st.plotly_chart(fig)
        else:
            st.info("No data yet.")

    with chart2:
        st.markdown("**Defect Breakdown**")
        if "defect" in df.columns:
            defect_df = df[df["defect"] != "none"]
            if not defect_df.empty:
                dc = defect_df["defect"].value_counts().reset_index()
                dc.columns = ["Defect","Count"]
                fig2 = px.pie(dc, names="Defect", values="Count", hole=0.6,
                              color_discrete_sequence=["#F09595","#EF9F27","#85B7EB","#B4B2A9"])
                fig2.update_layout(
                    height=260, margin=dict(l=0,r=0,t=10,b=0),
                    paper_bgcolor="rgba(0,0,0,0)",
                    legend=dict(orientation="h", y=-0.15),
                )
                fig2.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(fig2)
            else:
                st.info("No defects recorded yet.")

    st.divider()

    # ── 7-day trend ────────────────────────────────────────────
    st.markdown("**Pass Rate Trend — Last 7 Days**")
    df["date"] = df["datetime"].dt.date
    daily      = df.groupby(["date","status"]).size().unstack(fill_value=0).reset_index()
    if "Within Range" in daily.columns and len(daily) > 1:
        daily["total"]     = daily.get("Within Range", 0) + daily.get("Out of Range", 0)
        daily["pass_rate"] = (daily["Within Range"] / daily["total"] * 100).round(1)
        fig3 = px.line(daily.tail(7), x="date", y="pass_rate",
                       markers=True, color_discrete_sequence=["#0A8A72"])
        fig3.update_traces(fill="tozeroy", fillcolor="rgba(10,138,114,0.08)", line_width=2)
        fig3.update_layout(
            height=180, margin=dict(l=0,r=0,t=10,b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, title=""),
            yaxis=dict(showgrid=True, gridcolor="#F0F2F7", title="",
                       range=[0,100], ticksuffix="%"),
        )
        st.plotly_chart(fig3)
    else:
        st.info("Not enough data yet. Submit readings over multiple days to see the trend.")

    st.divider()

    # ── Recent records ─────────────────────────────────────────
    st.markdown("**Recent Readings**")

    def highlight(row):
        if row["status"] == "Out of Range":
            return ["background-color:#FFF8F8"] * len(row)
        return ["background-color:#F6FDF9"] * len(row)

    show_cols = ["datetime","technician","asset_id","tool","value","unit","status","defect"]
    show_cols = [c for c in show_cols if c in df.columns]
    st.dataframe(
        df[show_cols].sort_values("datetime", ascending=False).head(10)
            .style.apply(highlight, axis=1), height=320,
    )
