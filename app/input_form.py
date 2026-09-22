# app/input_form.py
# ── Measurement Input Form ─────────────────────────────────────
# Technician fills this in during maintenance inspection.
# Readings auto-fill via BLE simulation — manual entry as backup.

import streamlit as st
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import TOOLS, MULTIMETER, CSV_FILE, UPLOAD_DIR
from core.validate import validate_reading
from core.ble_receiver import (
    get_simulated_readings, get_simulated_defect,
    get_simulated_technician, get_simulated_asset, get_simulated_employee,
)


def show():
    st.markdown("## 📡 Measurement Input Form")
    st.caption("Readings auto-fill via Bluetooth simulation. Manual entry available as backup.")
    st.divider()

    # ── SECTION 1: Technician & Asset Info ────────────────────
    st.markdown("#### 👤 Technician & Asset Info")

    # Pre-fill from login session if available
    default_tech  = st.session_state.get("full_name", "")
    default_emp   = st.session_state.get("sap_number", "")

    c1, c2, c3, c4 = st.columns(4)
    tech_name = c1.text_input("Technician Name", value=st.session_state.get("_form_tech", default_tech), placeholder="e.g. Ali Ahmad")
    emp_id    = c2.text_input("Employee ID",      value=st.session_state.get("_form_emp",  default_emp),  placeholder="e.g. EMP-001")
    asset_id  = c3.text_input("Asset ID",         value=st.session_state.get("_form_asset", ""),          placeholder="e.g. LRT-C12")
    dt        = c4.text_input("Date & Time",       value=datetime.now().strftime("%Y-%m-%d %H:%M"))

    st.divider()

    # ── SECTION 2: BLE Simulation ─────────────────────────────
    st.markdown("#### 📡 Bluetooth Connection")
    ble_col1, ble_col2 = st.columns([1, 3])
    with ble_col1:
        simulate_ble = st.button("⚡ Simulate BLE Reading", type="secondary", use_container_width=True)
    with ble_col2:
        st.caption("Simulates Bluetooth tool readings to auto-fill the form below. Replace with real BLE once tools are connected.")

    if simulate_ble:
        sim_readings = get_simulated_readings()
        st.session_state["_sim"]        = sim_readings
        st.session_state["_sim_defect"] = get_simulated_defect()
        st.session_state["_form_tech"]  = get_simulated_technician()
        st.session_state["_form_emp"]   = get_simulated_employee()
        st.session_state["_form_asset"] = get_simulated_asset()
        st.success(f"✅ BLE readings received from all tools! Simulated defect: **{st.session_state['_sim_defect']}**")
        st.rerun()

    sim      = st.session_state.get("_sim", {})
    sim_defect = st.session_state.get("_sim_defect", "none")

    if sim:
        st.info("📡 BLE readings loaded — form auto-filled. You can adjust values manually before submitting.")

    st.divider()

    # ── SECTION 3: Multimeter ─────────────────────────────────
    st.markdown("#### ⚡ Digital Multimeter")
    st.caption("Measures voltage, current, and resistance")

    readings_multi = {}
    m1, m2, m3 = st.columns(3)
    multi_cols = [m1, m2, m3]

    for idx, (tool_name, cfg) in enumerate(MULTIMETER.items()):
        with multi_cols[idx]:
            st.markdown(f"**{tool_name.replace('Multimeter - ', '')}**")
            val = st.number_input(
                f"Reading ({cfg['unit']})",
                min_value=0.0, max_value=9999.0,
                value=float(sim.get(tool_name, 0.0)),
                key=f"multi_{idx}",
            )
            readings_multi[tool_name] = val
            if val > 0:
                in_range = cfg["min"] <= val <= cfg["max"]
                if in_range:
                    st.success(f"✅ Within range [{cfg['min']}–{cfg['max']} {cfg['unit']}]")
                else:
                    st.error(f"❌ Out of range [{cfg['min']}–{cfg['max']} {cfg['unit']}]")
            else:
                st.caption(f"Range: {cfg['min']} – {cfg['max']} {cfg['unit']}")

    st.divider()

    # ── SECTION 4: Other Tools ────────────────────────────────
    st.markdown("#### 🔧 Tool Readings")
    st.info("💡 When Bluetooth is connected, readings fill automatically. Manual entry as backup.")

    readings  = {}
    tool_list = list(TOOLS.items())

    row1 = st.columns(min(2, len(tool_list)))
    for idx in range(min(2, len(tool_list))):
        tool_name, cfg = tool_list[idx]
        with row1[idx]:
            st.markdown(f"**{tool_name}**")
            st.caption(cfg["desc"])
            if sim:
                st.success("📡 BLE")
            else:
                st.warning("⚪ Manual entry")
            val = st.number_input(
                f"Reading ({cfg['unit']})",
                min_value=0.0, max_value=9999.0,
                value=float(sim.get(tool_name, 0.0)),
                key=f"tool_{idx}",
            )
            readings[tool_name] = val
            if val > 0:
                result = validate_reading(tool_name, val, TOOLS)
                if result["passed"]:
                    st.success(f"✅ {result['message']}")
                else:
                    st.error(f"❌ {result['message']}")
            else:
                st.caption(f"Range: {cfg['min']} – {cfg['max']} {cfg['unit']}")

    if len(tool_list) > 2:
        row2 = st.columns(2)
        for idx in range(2, len(tool_list)):
            tool_name, cfg = tool_list[idx]
            with row2[idx - 2]:
                st.markdown(f"**{tool_name}**")
                st.caption(cfg["desc"])
                if sim:
                    st.success("📡 BLE")
                else:
                    st.warning("⚪ Manual entry")
                val = st.number_input(
                    f"Reading ({cfg['unit']})",
                    min_value=0.0, max_value=9999.0,
                    value=float(sim.get(tool_name, 0.0)),
                    key=f"tool_{idx}",
                )
                readings[tool_name] = val
                if val > 0:
                    result = validate_reading(tool_name, val, TOOLS)
                    if result["passed"]:
                        st.success(f"✅ {result['message']}")
                    else:
                        st.error(f"❌ {result['message']}")
                else:
                    st.caption(f"Range: {cfg['min']} – {cfg['max']} {cfg['unit']}")

    st.divider()

    # ── SECTION 5: Defect Photo & Notes ───────────────────────
    st.markdown("#### 📷 Defect Photo & Notes")
    photo_col, notes_col = st.columns([1, 2])

    with photo_col:
        uploaded = st.file_uploader(
            "Upload defect photo",
            type=["jpg", "jpeg", "png", "bmp", "webp"],
            help="Photo will be analysed by YOLO for defect detection",
        )
        if uploaded:
            st.image(uploaded, caption="Uploaded photo")

    with notes_col:
        defect_options = ["none", "crack", "wear", "corrosion", "other"]
        defect_index   = defect_options.index(sim_defect) if sim_defect in defect_options else 0
        defect_cat = st.selectbox("Defect Category", defect_options, index=defect_index)
        notes = st.text_area(
            "Notes",
            placeholder="Describe what you observed e.g. visible wear on left door edge...",
            height=120,
        )

    st.divider()

    # ── SUBMIT ─────────────────────────────────────────────────
    _, btn_col = st.columns([3, 1])
    submitted  = btn_col.button("✅ Submit All Readings", type="primary", use_container_width=True)

    if submitted:
        all_readings = {**readings_multi, **readings}

        if not tech_name:
            st.error("Please fill in Technician Name.")
        elif not emp_id:
            st.error("Please fill in Employee ID.")
        elif not asset_id:
            st.error("Please fill in Asset ID.")
        elif all(v == 0.0 for v in all_readings.values()):
            st.error("Please enter at least one tool reading.")
        else:
            # Save photo
            photo_filename = ""
            if uploaded:
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                photo_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded.name}"
                with open(os.path.join(UPLOAD_DIR, photo_filename), "wb") as f:
                    f.write(uploaded.getbuffer())

            # Write to CSV
            os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)
            write_header = not os.path.exists(CSV_FILE)
            with open(CSV_FILE, "a", newline="") as f:
                writer = csv.writer(f)
                if write_header:
                    writer.writerow([
                        "datetime", "technician", "employee_id", "asset_id",
                        "tool", "value", "unit", "min", "max",
                        "status", "defect", "notes", "photo",
                    ])
                # Multimeter rows
                for tool_name, val in readings_multi.items():
                    if val == 0.0:
                        continue
                    cfg    = MULTIMETER[tool_name]
                    status = "Within Range" if cfg["min"] <= val <= cfg["max"] else "Out of Range"
                    writer.writerow([
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        tech_name, emp_id, asset_id,
                        tool_name, val, cfg["unit"], cfg["min"], cfg["max"],
                        status, defect_cat, notes, photo_filename,
                    ])
                # Tool rows
                for tool_name, val in readings.items():
                    if val == 0.0:
                        continue
                    cfg    = TOOLS[tool_name]
                    result = validate_reading(tool_name, val, TOOLS)
                    writer.writerow([
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        tech_name, emp_id, asset_id,
                        tool_name, val, cfg["unit"], cfg["min"], cfg["max"],
                        result["status"], defect_cat, notes, photo_filename,
                    ])

            st.success("✅ All readings submitted successfully!")
            st.balloons()

            # Clear BLE simulation
            for k in ["_sim", "_sim_defect", "_form_tech", "_form_emp", "_form_asset"]:
                st.session_state.pop(k, None)

            # Submission summary
            import pandas as pd
            summary = []
            for tool_name, val in all_readings.items():
                if val == 0.0:
                    continue
                if tool_name in MULTIMETER:
                    cfg = MULTIMETER[tool_name]
                    ok  = cfg["min"] <= val <= cfg["max"]
                    status = "✅ Within Range" if ok else "❌ Out of Range"
                else:
                    cfg    = TOOLS[tool_name]
                    result = validate_reading(tool_name, val, TOOLS)
                    status = "✅ Within Range" if result["passed"] else "❌ Out of Range"
                summary.append({
                    "Tool":   tool_name,
                    "Value":  f"{val} {cfg['unit']}",
                    "Range":  f"{cfg['min']}–{cfg['max']} {cfg['unit']}",
                    "Status": status,
                })
            if summary:
                st.markdown("**Submission summary:**")
                st.dataframe(pd.DataFrame(summary), hide_index=True)
