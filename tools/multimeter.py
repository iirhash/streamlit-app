# -*- coding: utf-8 -*-
"""
Created on Mon Jun 22 08:30:51 2026

@author: Karina Nur C
"""

# tools/multimeter.py
import streamlit as st
import random
import math
from datetime import datetime
import pandas as pd
from tools.utils import rssi_bars_html, fake_hex_packet, add_packet, send_bt_capture, disp_val, in_tol, mm_to_in

MODES = ["DC Voltage", "AC Voltage", "DC Current", "AC Current", "Resistance", "Capacitance", "Frequency", "Diode", "Continuity"]

MODE_RANGES = {
    "DC Voltage":    [("200mV", 0.2), ("2V", 2), ("20V", 20), ("200V", 200), ("1000V", 1000)],
    "AC Voltage":    [("200mV", 0.2), ("2V", 2), ("20V", 20), ("200V", 200), ("750V", 750)],
    "DC Current":    [("2mA", 0.002), ("20mA", 0.02), ("200mA", 0.2), ("10A", 10)],
    "AC Current":    [("2mA", 0.002), ("20mA", 0.02), ("200mA", 0.2), ("10A", 10)],
    "Resistance":    [("200Ω", 200), ("2kΩ", 2000), ("20kΩ", 20000), ("200kΩ", 200000), ("2MΩ", 2e6), ("20MΩ", 20e6)],
    "Capacitance":   [("2nF", 2e-9), ("20nF", 20e-9), ("200nF", 200e-9), ("2μF", 2e-6), ("20μF", 20e-6)],
    "Frequency":     [("2kHz", 2000), ("20kHz", 20000), ("200kHz", 200000), ("2MHz", 2e6)],
    "Diode":         [("Diode", 3.3)],
    "Continuity":    [("Cont.", 1)],
}

MODE_UNITS = {
    "DC Voltage": "V", "AC Voltage": "V~",
    "DC Current": "A", "AC Current": "A~",
    "Resistance": "Ω", "Capacitance": "F",
    "Frequency": "Hz", "Diode": "V", "Continuity": "Ω",
} 

MODE_ICONS = {
    "DC Voltage":"⎓V", "AC Voltage":"~V", "DC Current":"⎓A", "AC Current":"~A",
    "Resistance":"Ω", "Capacitance":"⊣⊢", "Frequency":"Hz", "Diode":"⊳|", "Continuity":"))))",
}

def format_value(val, mode, range_max):
    unit = MODE_UNITS[mode]
    if mode == "Resistance":
        if val >= 1e6: return f"{val/1e6:.3f}", "MΩ"
        if val >= 1000: return f"{val/1000:.3f}", "kΩ"
        return f"{val:.1f}", "Ω"
    if mode == "Capacitance":
        if val >= 1e-6: return f"{val*1e6:.3f}", "μF"
        if val >= 1e-9: return f"{val*1e9:.3f}", "nF"
        return f"{val*1e12:.3f}", "pF"
    if mode == "Frequency":
        if val >= 1e6: return f"{val/1e6:.4f}", "MHz"
        if val >= 1000: return f"{val/1000:.3f}", "kHz"
        return f"{val:.1f}", "Hz"
    if mode == "Continuity":
        if val < 30: return "BEEP", "●"
        return "OPEN", "○"
    if abs(val) < 0.001 and val != 0: return f"{val*1000:.3f}", "m"+unit
    return f"{val:.4f}".rstrip('0').rstrip('.') if abs(val) < 10 else f"{val:.3f}", unit

def multimeter_svg(mode, value, range_label, bt_on, hold, rel_val=None):
    W, H = 320, 520
    BODY_X, BODY_Y = 20, 10
    BODY_W, BODY_H = 280, 500
    LCD_X, LCD_Y = 40, 30
    LCD_W, LCD_H = 240, 130

    disp_num, disp_unit = format_value(value, mode, 1)
    if hold and rel_val is not None:
        rel_num, rel_unit = format_value(rel_val, mode, 1)

    # Color by mode
    MODE_COLORS = {
        "DC Voltage":"#00ccff","AC Voltage":"#ffaa00","DC Current":"#00ffaa",
        "AC Current":"#ff8800","Resistance":"#ff6666","Capacitance":"#cc88ff",
        "Frequency":"#88ffcc","Diode":"#ffdd44","Continuity":"#44ffdd",
    }
    accent = MODE_COLORS.get(mode, "#00dd55")

    # Dial positions (degrees from top)
    dial_modes = list(MODE_RANGES.keys())
    dial_idx = dial_modes.index(mode) if mode in dial_modes else 0
    dial_angle = -150 + dial_idx * (300 / max(len(dial_modes)-1, 1))
    dial_rad = math.radians(dial_angle)
    DIAL_CX, DIAL_CY, DIAL_R = 160, 370, 75
    needle_x = DIAL_CX + (DIAL_R - 15) * math.sin(dial_rad)
    needle_y = DIAL_CY - (DIAL_R - 15) * math.cos(dial_rad)

    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" style="background:transparent;width:100%">',
        '<defs>',
        f'<linearGradient id="mmBody" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#2a2d36"/><stop offset="100%" stop-color="#1a1c24"/></linearGradient>',
        f'<radialGradient id="mmDial" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#1e2030"/><stop offset="100%" stop-color="#12141c"/></radialGradient>',
        '</defs>',
        # Body
        f'<rect x="{BODY_X}" y="{BODY_Y}" width="{BODY_W}" height="{BODY_H}" rx="18" fill="url(#mmBody)" stroke="#3a3d48" stroke-width="2"/>',
        # Grip texture sides
        *[f'<rect x="{BODY_X+4}" y="{BODY_Y+160+i*8}" width="8" height="5" rx="2" fill="#141620" opacity="0.7"/>' for i in range(18)],
        *[f'<rect x="{BODY_X+BODY_W-12}" y="{BODY_Y+160+i*8}" width="8" height="5" rx="2" fill="#141620" opacity="0.7"/>' for i in range(18)],
        # Brand
        f'<text x="160" y="{BODY_Y+22}" font-family="Rajdhani,sans-serif" font-weight="700" font-size="11" fill="#333" text-anchor="middle" letter-spacing="3">DIGIMETER · DM-800BT</text>',
        # LCD
        f'<rect x="{LCD_X}" y="{LCD_Y+8}" width="{LCD_W}" height="{LCD_H}" rx="8" fill="#060e06" stroke="#102010" stroke-width="1.5"/>',
        # BT LED
        f'<circle cx="{LCD_X+12}" cy="{LCD_Y+20}" r="4" fill="{"#1a7fff" if bt_on else "#1a1d28"}"/>',
        f'<text x="{LCD_X+22}" y="{LCD_Y+24}" font-family="monospace" font-size="7" fill="{"#1a7fff" if bt_on else "#1a1d28"}">BT</text>',
        # HOLD indicator
        f'<text x="{LCD_X+LCD_W-10}" y="{LCD_Y+24}" font-family="monospace" font-size="8" fill="{"#ddaa00" if hold else "#1a1d28"}" text-anchor="end">HOLD</text>',
        # Mode label
        f'<text x="{LCD_X+LCD_W//2}" y="{LCD_Y+40}" font-family="Share Tech Mono,monospace" font-size="9" fill="#1a4a1a" text-anchor="middle" letter-spacing="2">{mode.upper()}</text>',
        # Main value
        f'<text x="{LCD_X+LCD_W//2}" y="{LCD_Y+90}" font-family="Share Tech Mono,monospace" font-size="36" fill="{accent}" text-anchor="middle" style="text-shadow:0 0 18px {accent}88">{disp_num}</text>',
        # Unit
        f'<text x="{LCD_X+LCD_W-10}" y="{LCD_Y+110}" font-family="Share Tech Mono,monospace" font-size="14" fill="{accent}88" text-anchor="end">{disp_unit}</text>',
        # Range label
        f'<text x="{LCD_X+10}" y="{LCD_Y+125}" font-family="monospace" font-size="8" fill="#1a3a1a">RANGE: {range_label}</text>',
        # AC wavy line
        *([] if "AC" not in mode else [f'<text x="{LCD_X+LCD_W//2-30}" y="{LCD_Y+50}" font-family="monospace" font-size="10" fill="{accent}66">~</text>']),
        # Dial circle
        f'<circle cx="{DIAL_CX}" cy="{DIAL_CY}" r="{DIAL_R}" fill="url(#mmDial)" stroke="#2e3140" stroke-width="2"/>',
        f'<circle cx="{DIAL_CX}" cy="{DIAL_CY}" r="{DIAL_R-8}" fill="none" stroke="#1a1d28" stroke-width="8"/>',
    ]

    # Dial mode labels around circle
    for i, m in enumerate(dial_modes):
        ang = math.radians(-150 + i * (300 / max(len(dial_modes)-1, 1)))
        lx = DIAL_CX + (DIAL_R - 22) * math.sin(ang)
        ly = DIAL_CY - (DIAL_R - 22) * math.cos(ang)
        is_sel = (m == mode)
        col = accent if is_sel else "#2a2d38"
        sz  = 7 if is_sel else 6
        icon = MODE_ICONS.get(m, m[:2])
        p.append(f'<text x="{lx:.0f}" y="{ly:.0f}" font-family="monospace" font-size="{sz}" fill="{col}" text-anchor="middle">{icon}</text>')

    # Dial tick marks
    for i in range(30):
        ang = math.radians(-150 + i * 10)
        r1 = DIAL_R; r2 = DIAL_R - (6 if i%3==0 else 3)
        x1 = DIAL_CX + r1*math.sin(ang); y1 = DIAL_CY - r1*math.cos(ang)
        x2 = DIAL_CX + r2*math.sin(ang); y2 = DIAL_CY - r2*math.cos(ang)
        p.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#1e2130" stroke-width="1"/>')

    # Needle
    p += [
        f'<line x1="{DIAL_CX}" y1="{DIAL_CY}" x2="{needle_x:.1f}" y2="{needle_y:.1f}" stroke="{accent}" stroke-width="2.5" stroke-linecap="round"/>',
        f'<circle cx="{DIAL_CX}" cy="{DIAL_CY}" r="6" fill="#1e2130" stroke="{accent}" stroke-width="1.5"/>',
        f'<circle cx="{DIAL_CX}" cy="{DIAL_CY}" r="2" fill="{accent}"/>',
    ]

    # Test probe ports
    for px_off, col, lbl in [(130, "#ff3333", "COM"), (160, "#cc0000", "VΩmA"), (190, "#ff6600", "10A")]:
        p += [
            f'<circle cx="{px_off}" cy="455" r="10" fill="#0d0f14" stroke="#2a2d38" stroke-width="2"/>',
            f'<circle cx="{px_off}" cy="455" r="5" fill="{col}" opacity="0.7"/>',
            f'<text x="{px_off}" y="473" font-family="monospace" font-size="6" fill="#333" text-anchor="middle">{lbl}</text>',
        ]

    # Buttons row
    for bx, blbl in [(55,  "HOLD"), (105, "REL"), (155, "RANGE"), (210, "BT"), (255, "LIGHT")]:
        p += [
            f'<rect x="{bx-14}" y="486" width="28" height="14" rx="3" fill="#141620" stroke="#2a2d38" stroke-width="1"/>',
            f'<text x="{bx}" y="496" font-family="monospace" font-size="5" fill="#333" text-anchor="middle">{blbl}</text>',
        ]

    p.append('</svg>')
    return '\n'.join(p)


def render_multimeter():
    if "mm_mode"    not in st.session_state: st.session_state.mm_mode    = "DC Voltage"
    if "mm_range_i" not in st.session_state: st.session_state.mm_range_i = 2
    if "mm_value"   not in st.session_state: st.session_state.mm_value   = 12.0
    if "mm_hold"    not in st.session_state: st.session_state.mm_hold    = False
    if "mm_held"    not in st.session_state: st.session_state.mm_held    = 0.0
    if "mm_log"     not in st.session_state: st.session_state.mm_log     = []
    if "mm_tgt"     not in st.session_state: st.session_state.mm_tgt     = 12.0
    if "mm_tol"     not in st.session_state: st.session_state.mm_tol     = 0.5

    is_conn = st.session_state.bt_phase == "connected"

    col_svg, col_ctrl = st.columns([1, 1.6])

    with col_ctrl:
        st.markdown('<div class="panel-title">MODE SELECT</div>', unsafe_allow_html=True)
        mode = st.selectbox("Measurement Mode", MODES,
                            index=MODES.index(st.session_state.mm_mode), key="mm_mode_sel")
        st.session_state.mm_mode = mode

        ranges = MODE_RANGES[mode]
        ri = min(st.session_state.mm_range_i, len(ranges)-1)
        range_labels = [r[0] for r in ranges]
        range_sel = st.select_slider("Range", options=range_labels, value=range_labels[ri], key="mm_range_sel")
        ri = range_labels.index(range_sel)
        st.session_state.mm_range_i = ri
        range_max = ranges[ri][1]

        st.markdown('<div class="panel-title" style="margin-top:8px">MEASUREMENT INPUT</div>', unsafe_allow_html=True)

        if mode == "Continuity":
            val = st.slider("Resistance (Ω)", 0.0, 200.0, value=float(st.session_state.mm_value), step=0.1, key="mm_val_sl")
        elif mode == "Diode":
            val = st.slider("Forward Voltage (V)", 0.0, 3.3, value=min(float(st.session_state.mm_value), 3.3), step=0.001, key="mm_val_sl")
        elif mode == "Capacitance":
            val = st.slider("Capacitance (nF)", 0.0, float(range_max*1e9), value=min(float(st.session_state.mm_value)*1e9 if st.session_state.mm_value < 1 else 10.0, float(range_max*1e9)), step=0.001, key="mm_val_sl") * 1e-9
        else:
            val = st.slider(f"Value ({MODE_UNITS[mode]})", -float(range_max), float(range_max),
                            value=min(float(st.session_state.mm_value), float(range_max)),
                            step=float(range_max/1000), key="mm_val_sl")
        st.session_state.mm_value = val

        # Controls row
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("HOLD", width='stretch', key="mm_hold_btn"):
                st.session_state.mm_hold = not st.session_state.mm_hold
                if st.session_state.mm_hold: st.session_state.mm_held = val
        with c2:
            if st.button("AUTO RANGE", width='stretch', key="mm_ar"):
                # pick best range
                for i, (_, rm) in enumerate(ranges):
                    if abs(val) <= rm:
                        st.session_state.mm_range_i = i; break
        with c3:
            if st.button("CLEAR LOG", width='stretch', key="mm_cl"):
                st.session_state.mm_log = []

        # Trigger
        st.markdown('<div class="panel-title" style="margin-top:8px">TRIGGER POINT</div>', unsafe_allow_html=True)
        t1, t2 = st.columns(2)
        with t1: st.session_state.mm_tgt = st.number_input("Target", value=st.session_state.mm_tgt, step=0.01, key="mm_tgt_i", format="%.3f")
        with t2: st.session_state.mm_tol = st.number_input("Tol ±",  value=st.session_state.mm_tol, step=0.01, key="mm_tol_i", format="%.3f")

        trig = st.button("⊙  TRIGGER CAPTURE", width='stretch',
                         type="primary" if is_conn else "secondary", key="mm_trig")
        if trig:
            if is_conn:
                passed = in_tol(val, st.session_state.mm_tgt, st.session_state.mm_tol)
                disp_n, disp_u = format_value(val, mode, range_max)
                add_packet(val)
                st.session_state.mm_log.insert(0, {
                    "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "value": f"{disp_n} {disp_u}", "raw": val, "passed": passed,
                })
            else:
                st.warning("Connect Bluetooth first.")

        # Log
        if st.session_state.mm_log:
            total = len(st.session_state.mm_log); passed = sum(1 for e in st.session_state.mm_log if e["passed"])
            rows = ""
            for i, e in enumerate(st.session_state.mm_log[:8]):
                tc = "log-pass" if e["passed"] else "log-fail"
                rows += f'<div class="log-row"><span class="log-time">#{total-i:03d} {e["time"]}</span><span class="log-val">{e["value"]}</span><span class="{tc}">{"✔" if e["passed"] else "✖"}</span></div>'
            st.markdown(f'<div class="log-wrap"><div class="log-hdr">📡 {total} READINGS · {passed}/{total} PASS</div>{rows}</div>', unsafe_allow_html=True)

            df = pd.DataFrame(st.session_state.mm_log)
            st.download_button("⬇ Export CSV", df.to_csv(index=False), "multimeter_log.csv", "text/csv", width='stretch', key="mm_exp")

    with col_svg:
        disp_mm = st.session_state.mm_held if st.session_state.mm_hold else val
        st.markdown(multimeter_svg(mode, disp_mm, range_labels[ri], is_conn, st.session_state.mm_hold), unsafe_allow_html=True)

        # Mini LCD readout
        disp_n, disp_u = format_value(disp_mm, mode, range_max)
        accent = {"DC Voltage":"#00ccff","AC Voltage":"#ffaa00","DC Current":"#00ffaa","AC Current":"#ff8800","Resistance":"#ff6666","Capacitance":"#cc88ff","Frequency":"#88ffcc","Diode":"#ffdd44","Continuity":"#44ffdd"}.get(mode,"#00dd55")
        passed = in_tol(disp_mm, st.session_state.mm_tgt, st.session_state.mm_tol)
        tol_str = f'<span style="color:{"#00dd55" if passed else "#ff3333"}">{"✔ IN TOL" if passed else "✖ OUT TOL"}</span>'
        st.markdown(f"""
        <div class="lcd-outer" style="margin-top:8px">
          <div class="lcd-label">{"📡 BT CONNECTED" if is_conn else "⚪ BT OFF"} {"· HOLD" if st.session_state.mm_hold else ""}</div>
          <div class="lcd-main" style="color:{accent};text-shadow:0 0 20px {accent}88;font-size:3rem">{disp_n}</div>
          <div class="lcd-unit" style="color:{accent}66">{disp_u} · {mode}</div>
          <div class="lcd-sub">TGT {st.session_state.mm_tgt:.3f} ± {st.session_state.mm_tol:.3f} &nbsp;|&nbsp; {tol_str}</div>
        </div>""", unsafe_allow_html=True)