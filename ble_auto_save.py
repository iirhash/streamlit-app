# ─────────────────────────────────────────────────────────────────────────────
# BLE AUTO SAVE  ·  ble_auto_save.py
#
# TWO MODES:
#
#   1. Streamlit UI  (browser dashboard to control simulation)
#      streamlit run ble_auto_save.py --server.port 8503
#
#   2. Terminal / headless  (just run in background)
#      python ble_auto_save.py
#      python ble_auto_save.py --bulk 500   ← generate 500 rows instantly
#      python ble_auto_save.py --bulk 500 --days 30  ← spread across 30 days
# ─────────────────────────────────────────────────────────────────────────────

import csv
import os
import sys
import time
import random
import logging
import argparse
from datetime import datetime, timedelta

# Allow imports from parent folder when run as `python ble_auto_save.py`
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.settings import CSV_FILE, TOOLS
from core.ble_receiver import (
    get_simulated_readings, get_simulated_defect,
    get_simulated_technician, get_simulated_asset, get_simulated_employee,
)

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("ble_auto_save.log"),
    ],
)
log = logging.getLogger(__name__)

# ─── CONFIG ──────────────────────────────────────────────────────────────────
DEFAULT_INTERVAL = 10   # seconds between live readings
DEFAULT_TECH     = "Ali Ahmad"
DEFAULT_EMP      = "201234"
DEFAULT_ASSET    = "V40A"

# All tool thresholds — imported from settings so there's one source of truth
from config.settings import ALL_TOOLS as ALL_THRESHOLDS

# ─────────────────────────────────────────────────────────────────────────────
# CORE SAVE FUNCTION  (shared by all modes)
# ─────────────────────────────────────────────────────────────────────────────
def save_readings(tech, emp, asset, readings, defect, notes="auto-saved via BLE",
                  override_dt=None):
    """
    Write one cycle of readings to CSV.
    override_dt: datetime object — used for bulk backfill so dates look historical.
    Returns number of rows saved.
    """
    os.makedirs(os.path.dirname(os.path.abspath(CSV_FILE)), exist_ok=True)
    write_header = not os.path.exists(CSV_FILE)

    saved = 0
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow([
                "datetime", "technician", "employee_id", "asset_id",
                "tool", "value", "unit", "min", "max", "status",
                "defect", "notes", "photo",
            ])

        ts = (override_dt or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")

        for tool_name, value in readings.items():
            if value is None or value == 0.0:
                continue

            thr     = ALL_THRESHOLDS.get(tool_name, {})
            unit    = thr.get("unit", "")
            min_val = thr.get("min", "")
            max_val = thr.get("max", "")
            status  = ""
            if min_val != "" and max_val != "":
                status = "Within Range" if min_val <= value <= max_val else "Out of Range"

            writer.writerow([
                ts, tech, emp, asset,
                tool_name, round(value, 2), unit,
                min_val, max_val, status,
                defect, notes, "",
            ])
            saved += 1

    return saved


# ─────────────────────────────────────────────────────────────────────────────
# BULK GENERATOR  (instant historical data)
# ─────────────────────────────────────────────────────────────────────────────
def bulk_generate(n_records=200, spread_days=30, verbose=True):
    """
    Generate n_records rows spread across the past spread_days days.
    Each record = one full set of tool readings (7 tools → up to 7 rows per record).
    """
    tech_name = ["Ali Ahmad", "Farid Ismail", "Muhammad Adam", "Hazim Karim", "Iman Irhash"]
    emp_id     = ["201234", "256789", "298765", "243210", "297531"]
    asset_ids   = ["V40A", "V40B", "V41A", "V41B", "V42A", "V42B"]

    total_rows = 0
    now = datetime.now()

    for i in range(n_records):
        # Random timestamp in the past spread_days
        seconds_back = random.randint(0, spread_days * 24 * 3600)
        fake_dt = now - timedelta(seconds=seconds_back)

        tech    = random.choice(tech_name)
        emp     = random.choice(emp_id)
        asset   = random.choice(asset_ids)
        defect  = get_simulated_defect()
        readings = get_simulated_readings()

        rows = save_readings(tech, emp, asset, readings, defect,
                             notes="bulk-generated simulation",
                             override_dt=fake_dt)
        total_rows += rows

        if verbose and (i + 1) % 50 == 0:
            log.info(f"  Generated {i+1}/{n_records} records ({total_rows} rows so far)...")

    return total_rows


# ─────────────────────────────────────────────────────────────────────────────
# LIVE LOOP  (continuous simulation)
# ─────────────────────────────────────────────────────────────────────────────
def run_live_loop(tech, emp, asset, interval=DEFAULT_INTERVAL):
    log.info("=" * 55)
    log.info("BLE Auto Save — LIVE MODE")
    log.info(f"  Technician : {tech}")
    log.info(f"  Employee ID: {emp}")
    log.info(f"  Asset ID   : {asset}")
    log.info(f"  Interval   : every {interval}s")
    log.info("  Press Ctrl+C to stop")
    log.info("=" * 55)

    cycle = 1
    while True:
        try:
            log.info(f"── Cycle {cycle} ──────────────────────────────")
            readings  = get_simulated_readings()
            defect    = get_simulated_defect()
            tech_now  = get_simulated_technician()
            asset_now = get_simulated_asset()
            emp_now   = get_simulated_employee()

            for name, val in readings.items():
                log.info(f"   {name}: {val}")

            saved = save_readings(tech_now, emp_now, asset_now, readings, defect)
            log.info(f"   → Saved {saved} rows  |  defect={defect}")
            log.info(f"   Waiting {interval}s...")
            time.sleep(interval)
            cycle += 1

        except KeyboardInterrupt:
            log.info("BLE Auto Save stopped.")
            break
        except Exception as e:
            log.error(f"Error: {e}")
            time.sleep(5)


# ─────────────────────────────────────────────────────────────────────────────
# STREAMLIT UI MODE
# ─────────────────────────────────────────────────────────────────────────────
def run_streamlit_ui():
    import streamlit as st
    import pandas as pd
    import threading

    st.set_page_config(
        page_title="BLE Auto Save",
        page_icon="📡",
        layout="wide",
    )

    # ── CSS ──────────────────────────────────────────────────────────────────
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@600;700&display=swap');
    html,body,[data-testid="stAppViewContainer"],[data-testid="stAppViewContainer"]>.main{ background:#f5f6f8 !important; color:#1a1d24 !important; }
    [data-testid="block-container"]{ padding:1.2rem 2rem; max-width:1300px; }
    section[data-testid="stSidebar"]{ background:#ffffff !important; border-right:1px solid #e0e2e8 !important; } section[data-testid="stSidebar"] label,section[data-testid="stSidebar"] p,section[data-testid="stSidebar"] span{ color:#1a1d24 !important; }
    .card{ background:#ffffff; border:1px solid #e0e2e8; border-radius:10px; padding:1rem 1.2rem; margin-bottom:0.8rem; box-shadow:0 2px 10px rgba(0,0,0,0.06); }
    .card-title{ font-family:Rajdhani,sans-serif; font-weight:700; font-size:0.65rem; letter-spacing:0.2em; color:#9098b0; border-bottom:1px solid #e8eaf0; padding-bottom:4px; margin-bottom:10px; }
    .stat-big{ font-family:Share Tech Mono,monospace; font-size:2.2rem; font-weight:bold; color:#008833; line-height:1.1; }
    .stat-label{ font-family:Share Tech Mono,monospace; font-size:0.6rem; color:#9098b0; letter-spacing:0.15em; }
    .live-dot{ display:inline-block; width:9px; height:9px; border-radius:50%; background:#00bb44; box-shadow:0 0 8px #00bb4466; animation:blink 1.5s infinite; margin-right:6px; }
    .idle-dot{ display:inline-block; width:9px; height:9px; border-radius:50%; background:#c8cad4; margin-right:6px; }
    @keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}
    .row-ok{ color:#008833; } .row-fail{ color:#cc2222; }
    .stButton>button{ font-family:Rajdhani,sans-serif !important; font-weight:700 !important; letter-spacing:0.1em !important; border-radius:6px !important; }
    .bulk-done{ background:#f0fbf4; border:1px solid #00bb4466; border-radius:8px; padding:10px 16px; font-family:Share Tech Mono,monospace; font-size:0.75rem; color:#006622; margin:8px 0; }
    </style>
    """, unsafe_allow_html=True)

    # ── Session state ─────────────────────────────────────────────────────────
    for k, v in {
        "ble_running": False, "ble_saved_total": 0,
        "ble_cycle": 0, "ble_last_readings": {},
        "ble_log": [], "bulk_done_msg": "",
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="display:flex;align-items:baseline;gap:14px;margin-bottom:1rem;
                border-bottom:1px solid #e0e2e8;padding-bottom:0.8rem">
      <span style="font-family:Rajdhani,sans-serif;font-weight:700;font-size:1.1rem;
                   color:#222;letter-spacing:0.2em">DIGIMETER</span>
      <span style="font-family:Share Tech Mono,monospace;font-size:0.65rem;
                   color:#9098b0;letter-spacing:0.2em">BLE AUTO SAVE · DATA SIMULATOR</span>
    </div>""", unsafe_allow_html=True)

    # ── Layout ────────────────────────────────────────────────────────────────
    col_ctrl, col_live = st.columns([1, 1.8])

    with col_ctrl:
        # ── Live simulation controls ──────────────────────────────────────────
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">📡 LIVE BLE SIMULATION</div>', unsafe_allow_html=True)

        interval = st.slider("Interval between readings (seconds)", 2, 60, 10, key="ble_interval")
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("▶ START", width = 'stretch', disabled=st.session_state.ble_running):
                st.session_state.ble_running = True
        with c2:
            if st.button("⏹ STOP", width = 'stretch', disabled=not st.session_state.ble_running):
                st.session_state.ble_running = False

        # Status indicator
        if st.session_state.ble_running:
            st.markdown('<div style="font-family:Share Tech Mono,monospace;font-size:0.7rem;margin:8px 0"><span class="live-dot"></span><span style="color:#007733">RUNNING</span></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="font-family:Share Tech Mono,monospace;font-size:0.7rem;margin:8px 0"><span class="idle-dot"></span><span style="color:#888">IDLE</span></div>', unsafe_allow_html=True)

        # One-shot manual trigger
        if st.button("⚡ TRIGGER ONE READING NOW", width = 'stretch'):
            readings  = get_simulated_readings()
            defect    = get_simulated_defect()
            tech      = get_simulated_technician()
            emp       = get_simulated_employee()
            asset     = get_simulated_asset()
            saved     = save_readings(tech, emp, asset, readings, defect)
            st.session_state.ble_saved_total += saved
            st.session_state.ble_cycle       += 1
            st.session_state.ble_last_readings = readings
            entry = {
                "time": datetime.now().strftime("%H:%M:%S"),
                "tech": tech, "asset": asset,
                "defect": defect, "rows": saved,
                "readings": dict(readings),
            }
            st.session_state.ble_log.insert(0, entry)
            if len(st.session_state.ble_log) > 50:
                st.session_state.ble_log = st.session_state.ble_log[:50]
            st.success(f"Saved {saved} rows!")

        st.markdown('</div>', unsafe_allow_html=True)

        # ── Bulk generator ────────────────────────────────────────────────────
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">🗂 BULK DATA GENERATOR</div>', unsafe_allow_html=True)

        st.caption("Instantly generate hundreds of historical records for dashboard testing.")

        n_rec  = st.number_input("Number of records to generate", 10, 5000, 200, step=50, key="bulk_n")
        n_days = st.number_input("Spread across past N days",      1,  365,  30,  step=1,  key="bulk_days")

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("🚀 GENERATE", width = 'stretch', type="primary"):
                with st.spinner(f"Generating {n_rec} records across {n_days} days..."):
                    rows = bulk_generate(int(n_rec), int(n_days), verbose=False)
                st.session_state.ble_saved_total += rows
                st.session_state.bulk_done_msg = (
                    f"✔ Generated {n_rec} records → {rows} CSV rows\n"
                    f"  Spread: last {n_days} days\n"
                    f"  File: {os.path.abspath(CSV_FILE)}"
                )
                st.rerun()
        with col_b2:
            if st.button("🗑 CLEAR CSV", width = 'stretch'):
                if os.path.exists(CSV_FILE):
                    os.remove(CSV_FILE)
                    st.session_state.ble_saved_total = 0
                    st.session_state.bulk_done_msg = "CSV cleared."
                    st.rerun()

        if st.session_state.bulk_done_msg:
            st.markdown(
                f'<div class="bulk-done">{st.session_state.bulk_done_msg.replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True,
            )

        st.markdown('</div>', unsafe_allow_html=True)

        # ── Stats ─────────────────────────────────────────────────────────────
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">SESSION STATS</div>', unsafe_allow_html=True)

        csv_rows = 0
        if os.path.exists(CSV_FILE):
            try:
                csv_rows = sum(1 for _ in open(CSV_FILE, encoding="utf-8")) - 1
            except Exception:
                pass

        s1, s2, s3 = st.columns(3)
        with s1:
            st.markdown(f'<div class="stat-label">CYCLES</div><div class="stat-big">{st.session_state.ble_cycle}</div>', unsafe_allow_html=True)
        with s2:
            st.markdown(f'<div class="stat-label">ROWS SAVED</div><div class="stat-big">{st.session_state.ble_saved_total}</div>', unsafe_allow_html=True)
        with s3:
            st.markdown(f'<div class="stat-label">CSV TOTAL</div><div class="stat-big">{max(csv_rows,0)}</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    with col_live:
        # ── Run one cycle if live mode is on ──────────────────────────────────
        if st.session_state.ble_running:
            readings  = get_simulated_readings()
            defect    = get_simulated_defect()
            tech      = get_simulated_technician()
            emp       = get_simulated_employee()
            asset     = get_simulated_asset()
            saved     = save_readings(tech, emp, asset, readings, defect)

            st.session_state.ble_saved_total += saved
            st.session_state.ble_cycle       += 1
            st.session_state.ble_last_readings = readings

            entry = {
                "time": datetime.now().strftime("%H:%M:%S"),
                "tech": tech, "asset": asset,
                "defect": defect, "rows": saved,
                "readings": dict(readings),
            }
            st.session_state.ble_log.insert(0, entry)
            if len(st.session_state.ble_log) > 50:
                st.session_state.ble_log = st.session_state.ble_log[:50]

        # ── Latest readings panel ─────────────────────────────────────────────
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">LATEST BLE READINGS</div>', unsafe_allow_html=True)

        if st.session_state.ble_last_readings:
            rows_html = ""
            for tool, val in st.session_state.ble_last_readings.items():
                if val is None:
                    continue
                thr    = ALL_THRESHOLDS.get(tool, {})
                unit   = thr.get("unit", "")
                mn, mx = thr.get("min"), thr.get("max")
                ok     = (mn is not None) and (mn <= val <= mx)
                status_icon = "✔" if ok else "✖"
                cls    = "row-ok" if ok else "row-fail"
                rows_html += (
                    f'<div style="display:flex;justify-content:space-between;'
                    f'padding:5px 0;border-bottom:1px solid #eef0f5;'
                    f'font-family:Share Tech Mono,monospace;font-size:0.7rem">'
                    f'<span style="color:#2a3a4a;max-width:55%">{tool}</span>'
                    f'<span style="color:#008833">{val} <span style="color:#336644">{unit}</span></span>'
                    f'<span class="{cls}">{status_icon}</span>'
                    f'</div>'
                )
            st.markdown(
                f'<div style="background:#f8f9fc;border:1px solid #e0e2ea;border-radius:6px;'
                f'padding:8px 12px">{rows_html}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<span style="font-family:Share Tech Mono,monospace;font-size:0.65rem;color:#b0b8cc">No readings yet — press START or TRIGGER</span>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

        # ── Cycle log ─────────────────────────────────────────────────────────
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">CYCLE LOG</div>', unsafe_allow_html=True)

        if st.session_state.ble_log:
            log_html = ""
            for i, e in enumerate(st.session_state.ble_log[:20]):
                bg = "#f8f9fc" if i % 2 == 0 else "#f2f4f8"
                defect_col = "#cc5500" if e["defect"] != "none" else "#9098b0"
                log_html += (
                    f'<div style="display:flex;gap:12px;padding:5px 8px;background:{bg};'
                    f'border-radius:4px;font-family:Share Tech Mono,monospace;font-size:0.63rem;'
                    f'margin-bottom:2px">'
                    f'<span style="color:#b0b8cc;width:68px;flex-shrink:0">{e["time"]}</span>'
                    f'<span style="color:#3366aa;width:80px;flex-shrink:0">{e["tech"].split()[0]}</span>'
                    f'<span style="color:#336633;width:42px;flex-shrink:0">{e["asset"]}</span>'
                    f'<span style="color:{defect_col};width:60px;flex-shrink:0">{e["defect"]}</span>'
                    f'<span style="color:#008833">{e["rows"]} rows</span>'
                    f'</div>'
                )
            st.markdown(
                f'<div style="background:#f8f9fc;border:1px solid #e0e2ea;border-radius:6px;'
                f'padding:6px;max-height:320px;overflow-y:auto">{log_html}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<span style="font-family:Share Tech Mono,monospace;font-size:0.65rem;color:#b0b8cc">Log is empty</span>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

        # ── CSV preview ───────────────────────────────────────────────────────
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">CSV PREVIEW — LAST 10 ROWS</div>', unsafe_allow_html=True)

        if os.path.exists(CSV_FILE):
            try:
                df = pd.read_csv(CSV_FILE)
                if not df.empty:
                    def style_row(row):
                        if row.get("status") == "Out of Range":
                            return ["background-color:#fff5f5"] * len(row)
                        return ["background-color:#f8fff8"] * len(row)

                    show_cols = [c for c in ["datetime","technician","asset_id","tool","value","unit","status","defect"] if c in df.columns]
                    st.dataframe(
                        df[show_cols].tail(10).style.apply(style_row, axis=1),
                        width = 'stretch', height=240,
                    )
                    csv_bytes = df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "⬇ Download full CSV", data=csv_bytes,
                        file_name=f"condition_records_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv", width = 'stretch',
                    )
            except Exception as ex:
                st.caption(f"Could not read CSV: {ex}")
        else:
            st.caption("No CSV yet.")

        st.markdown('</div>', unsafe_allow_html=True)

    # ── Auto-rerun while live mode is on ──────────────────────────────────────
    if st.session_state.ble_running:
        time.sleep(max(1, interval))
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def _is_streamlit():
    """True if we're running inside `streamlit run`."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


if _is_streamlit():
    # ── Streamlit UI mode ────────────────────────────────────────────────────
    run_streamlit_ui()

else:
    # ── Terminal / CLI mode ──────────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        description="BLE Auto Save — generate or stream simulated condition data"
    )
    parser.add_argument("--bulk",     type=int,   default=0,               help="Generate N records instantly and exit")
    parser.add_argument("--days",     type=int,   default=30,              help="Spread bulk records across N past days (default 30)")
    parser.add_argument("--interval", type=int,   default=DEFAULT_INTERVAL,help="Seconds between live readings (default 10)")
    parser.add_argument("--tech",     type=str,   default=DEFAULT_TECH,    help="Technician name for live mode")
    parser.add_argument("--emp",      type=str,   default=DEFAULT_EMP,     help="Employee ID for live mode")
    parser.add_argument("--asset",    type=str,   default=DEFAULT_ASSET,   help="Asset ID for live mode")
    args = parser.parse_args()

    if args.bulk > 0:
        log.info(f"BULK MODE: generating {args.bulk} records across {args.days} days...")
        total = bulk_generate(args.bulk, args.days, verbose=True)
        log.info(f"Done! Saved {total} rows to {os.path.abspath(CSV_FILE)}")
    else:
        run_live_loop(args.tech, args.emp, args.asset, args.interval)