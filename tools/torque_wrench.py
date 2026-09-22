# -*- coding: utf-8 -*-
"""
Created on Mon Jun 22 08:30:51 2026

@author: Karina Nur C
"""

# tools/torque_wrench.py
import streamlit as st
import math
from datetime import datetime
from tools.utils import add_packet, in_tol
import pandas as pd

UNITS = ["N·m", "ft·lb", "in·lb", "kg·m"]
UNIT_CONV = {"N·m": 1.0, "ft·lb": 0.737562, "in·lb": 8.85075, "kg·m": 0.101972}
DRIVE_SIZES = ["1/4\"", "3/8\"", "1/2\"", "3/4\"", "1\""]
DRIVE_MAX   = {"1/4\"": 30, "3/8\"": 80, "1/2\"": 250, "3/4\"": 700, "1\"": 1500}

def torque_svg(torque_nm, max_nm, unit, target_nm, tol_nm, bt_on, hold, peak_nm=0.0):
    W, H = 320, 580
    # Colors
    pct = min(torque_nm / max_nm, 1.0) if max_nm > 0 else 0
    bar_col = "#00dd55" if pct < 0.7 else ("#ffaa00" if pct < 0.9 else "#ff2828")
    tgt_pct = min(target_nm / max_nm, 1.0) if max_nm > 0 else 0
    tol_pct = tol_nm / max_nm if max_nm > 0 else 0
    accent = bar_col

    conv = UNIT_CONV.get(unit, 1.0)
    disp_val = torque_nm * conv
    disp_tgt = target_nm * conv
    disp_tol = tol_nm * conv

    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" style="background:transparent;width:100%">',
        '<defs>',
        f'<linearGradient id="twHandle" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#1e2028"/><stop offset="30%" stop-color="#3a3d48"/><stop offset="70%" stop-color="#3a3d48"/><stop offset="100%" stop-color="#1e2028"/></linearGradient>',
        f'<linearGradient id="twHead"   x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#5a5d68"/><stop offset="100%" stop-color="#2a2d38"/></linearGradient>',
        '</defs>',
        # Brand
        f'<text x="160" y="18" font-family="Rajdhani,sans-serif" font-weight="700" font-size="10" fill="#333" text-anchor="middle" letter-spacing="3">DIGIMETER · TW-500BT</text>',
        # ── Wrench body (handle) ──
        f'<rect x="130" y="30" width="60" height="340" rx="12" fill="url(#twHandle)" stroke="#2a2d38" stroke-width="1.5"/>',
        # grip knurling
        *[f'<rect x="132" y="{200+i*10}" width="56" height="6" rx="2" fill="#141620" opacity="0.6"/>' for i in range(13)],
        # scale markings on handle
        *[f'<text x="128" y="{55+i*28}" font-family="monospace" font-size="7" fill="#2a2d38" text-anchor="end">{int(max_nm - i*(max_nm/10))}</text>' for i in range(11)],
        # ── Drive head ──
        f'<rect x="118" y="22" width="84" height="28" rx="6" fill="url(#twHead)" stroke="#4a4d58" stroke-width="1.5"/>',
        f'<rect x="142" y="16" width="36" height="12" rx="4" fill="#3a3d48" stroke="#4a4d58" stroke-width="1"/>',
        f'<circle cx="160" cy="16" r="5" fill="#1e2028" stroke="#5a5d68" stroke-width="1.5"/>',
        # ── LCD panel ──
        f'<rect x="42" y="50" width="76" height="110" rx="8" fill="#060e06" stroke="#102010" stroke-width="1.5"/>',
        f'<circle cx="54" cy="61" r="4" fill="{"#1a7fff" if bt_on else "#1a1d28"}"/>',
        f'<text x="64" y="65" font-family="monospace" font-size="7" fill="{"#1a7fff" if bt_on else "#1a1d28"}">BT</text>',
        f'<text x="110" y="65" font-family="monospace" font-size="7" fill="{"#ddaa00" if hold else "#1a1d28"}" text-anchor="end">HOLD</text>',
        f'<text x="80" y="78" font-family="monospace" font-size="7" fill="#1a3a1a" text-anchor="middle">TORQUE</text>',
        f'<text x="80" y="118" font-family="Share Tech Mono,monospace" font-size="26" fill="{accent}" text-anchor="middle" style="text-shadow:0 0 14px {accent}88">{disp_val:.1f}</text>',
        f'<text x="80" y="134" font-family="monospace" font-size="8" fill="{accent}88" text-anchor="middle">{unit}</text>',
        f'<text x="80" y="150" font-family="monospace" font-size="7" fill="#1a3a1a" text-anchor="middle">TGT {disp_tgt:.1f}±{disp_tol:.1f}</text>',
    ]

    # ── Bar graph (side of handle) ──
    BAR_X, BAR_Y, BAR_W, BAR_H = 202, 50, 18, 300
    p += [
        f'<rect x="{BAR_X}" y="{BAR_Y}" width="{BAR_W}" height="{BAR_H}" rx="4" fill="#0d0f14" stroke="#1e2028" stroke-width="1"/>',
    ]
    # green zone (0–70%)
    gh = int(BAR_H * 0.7)
    p.append(f'<rect x="{BAR_X+2}" y="{BAR_Y+BAR_H-gh}" width="{BAR_W-4}" height="{gh}" rx="2" fill="#001a06" opacity="0.5"/>')
    # orange zone (70-90%)
    oh = int(BAR_H * 0.2)
    p.append(f'<rect x="{BAR_X+2}" y="{BAR_Y+BAR_H-gh-oh}" width="{BAR_W-4}" height="{oh}" rx="2" fill="#1a0e00" opacity="0.5"/>')
    # red zone (90-100%)
    rh = int(BAR_H * 0.1)
    p.append(f'<rect x="{BAR_X+2}" y="{BAR_Y+2}" width="{BAR_W-4}" height="{rh}" rx="2" fill="#1a0000" opacity="0.5"/>')
    # fill bar
    fill_h = int(BAR_H * pct)
    if fill_h > 0:
        p.append(f'<rect x="{BAR_X+2}" y="{BAR_Y+BAR_H-fill_h}" width="{BAR_W-4}" height="{fill_h}" rx="2" fill="{bar_col}" opacity="0.85"/>')
    # target line
    tgt_y = int(BAR_Y + BAR_H - tgt_pct * BAR_H)
    tol_h = int(tol_pct * BAR_H)
    p += [
        f'<rect x="{BAR_X+1}" y="{tgt_y-tol_h//2}" width="{BAR_W-2}" height="{max(2,tol_h)}" fill="#ffaa0033" stroke="#ffaa0066" stroke-width="0.5"/>',
        f'<line x1="{BAR_X}" y1="{tgt_y}" x2="{BAR_X+BAR_W}" y2="{tgt_y}" stroke="#ffaa00" stroke-width="1.5" stroke-dasharray="3,2"/>',
    ]
    # peak marker
    if peak_nm > 0:
        pk_y = int(BAR_Y + BAR_H - min(peak_nm/max_nm, 1.0)*BAR_H)
        p.append(f'<line x1="{BAR_X}" y1="{pk_y}" x2="{BAR_X+BAR_W}" y2="{pk_y}" stroke="#ff6600" stroke-width="1" stroke-dasharray="2,2"/>')
        p.append(f'<text x="{BAR_X+BAR_W+3}" y="{pk_y+3}" font-family="monospace" font-size="6" fill="#ff6600">PK</text>')

    # Zone labels
    for label, y in [("OL", BAR_Y+8), ("MAX", BAR_Y+BAR_H//4), ("MID", BAR_Y+BAR_H//2), ("LOW", BAR_Y+3*BAR_H//4)]:
        p.append(f'<text x="{BAR_X+BAR_W+3}" y="{y}" font-family="monospace" font-size="5.5" fill="#1e2028">{label}</text>')

    # ── Angle indicator ring ──
    CX, CY, R = 160, 430, 55
    ANG = pct * 240 - 120  # -120° to +120°
    ang_rad = math.radians(ANG - 90)
    nx = 160 + 44 * math.cos(ang_rad)
    ny = 430 + 44 * math.sin(ang_rad)
    p += [
        f'<circle cx="160" cy="430" r="55" fill="#0d0f14" stroke="#1e2028" stroke-width="2"/>',
        f'<circle cx="160" cy="430" r="48" fill="none" stroke="#141820" stroke-width="8"/>',
    ]
    # arc segments
    for i in range(24):
        a1 = math.radians(-120 + i*10 - 90)
        a2 = math.radians(-120 + (i+1)*10 - 90)
        x1s=160+46*math.cos(a1); y1s=430+46*math.sin(a1)
        x2s=160+46*math.cos(a2); y2s=430+46*math.sin(a2)
        x1l=160+52*math.cos(a1); y1l=430+52*math.sin(a1)
        x2l=160+52*math.cos(a2); y2l=430+52*math.sin(a2)
        seg_pct = i / 24
        col = "#00dd55" if seg_pct < 0.7 else ("#ffaa00" if seg_pct < 0.9 else "#ff2828")
        opacity = 0.8 if i < int(pct*24) else 0.12
        p.append(f'<polygon points="{x1s:.1f},{y1s:.1f} {x2s:.1f},{y2s:.1f} {x2l:.1f},{y2l:.1f} {x1l:.1f},{y1l:.1f}" fill="{col}" opacity="{opacity}"/>')
    p += [
        f'<line x1="160" y1="430" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{accent}" stroke-width="2.5" stroke-linecap="round"/>',
        f'<circle cx="160" cy="430" r="5" fill="#1e2028" stroke="{accent}" stroke-width="1.5"/>',
        f'<text x="160" y="425" font-family="Share Tech Mono,monospace" font-size="11" fill="{accent}" text-anchor="middle">{disp_val:.1f}</text>',
        f'<text x="160" y="438" font-family="monospace" font-size="7" fill="{accent}88" text-anchor="middle">{unit}</text>',
    ]

    # Ratchet head bottom
    p += [
        f'<rect x="138" y="365" width="44" height="16" rx="4" fill="#2a2d38" stroke="#3a3d48" stroke-width="1"/>',
        f'<circle cx="160" cy="373" r="5" fill="#1a1d28" stroke="#5a5d68" stroke-width="1.5"/>',
        f'<text x="160" y="500" font-family="monospace" font-size="7" fill="#1e2028" text-anchor="middle">DIGIMETER TW-500BT TORQUE WRENCH</text>',
    ]
    p.append('</svg>')
    return '\n'.join(p)


def render_torque_wrench():
    if "tw_drive"  not in st.session_state: st.session_state.tw_drive  = "1/2\""
    if "tw_unit"   not in st.session_state: st.session_state.tw_unit   = "N·m"
    if "tw_torque" not in st.session_state: st.session_state.tw_torque = 45.0
    if "tw_hold"   not in st.session_state: st.session_state.tw_hold   = False
    if "tw_held"   not in st.session_state: st.session_state.tw_held   = 0.0
    if "tw_peak"   not in st.session_state: st.session_state.tw_peak   = 0.0
    if "tw_tgt"    not in st.session_state: st.session_state.tw_tgt    = 50.0
    if "tw_tol"    not in st.session_state: st.session_state.tw_tol    = 2.0
    if "tw_log"    not in st.session_state: st.session_state.tw_log    = []
    if "tw_track"  not in st.session_state: st.session_state.tw_track  = False

    is_conn = st.session_state.bt_phase == "connected"
    drive   = st.session_state.tw_drive
    max_nm  = DRIVE_MAX[drive]
    unit    = st.session_state.tw_unit
    conv    = UNIT_CONV[unit]

    col_svg, col_ctrl = st.columns([1, 1.6])

    with col_ctrl:
        st.markdown('<div class="panel-title">WRENCH SETTINGS</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            drive_sel = st.selectbox("Drive Size", DRIVE_SIZES, index=DRIVE_SIZES.index(drive), key="tw_drive_sel")
            st.session_state.tw_drive = drive_sel; drive = drive_sel; max_nm = DRIVE_MAX[drive]
        with c2:
            unit_sel = st.selectbox("Unit", UNITS, index=UNITS.index(unit), key="tw_unit_sel")
            st.session_state.tw_unit = unit_sel; unit = unit_sel; conv = UNIT_CONV[unit]

        torque_disp = st.slider(f"Applied Torque ({unit})", 0.0, float(max_nm * conv),
                                value=min(float(st.session_state.tw_torque * conv), float(max_nm * conv)),
                                step=float(max_nm*conv/1000), key="tw_sl",
                                format=f"%.1f {unit}")
        torque_nm = torque_disp / conv
        st.session_state.tw_torque = torque_nm

        # Peak tracking
        if st.session_state.tw_track:
            if torque_nm > st.session_state.tw_peak: st.session_state.tw_peak = torque_nm

        c3, c4, c5 = st.columns(3)
        with c3:
            if st.button("HOLD",       width='stretch', key="tw_hold_btn"):
                st.session_state.tw_hold = not st.session_state.tw_hold
                if st.session_state.tw_hold: st.session_state.tw_held = torque_nm
        with c4:
            pk_lbl = "STOP PEAK" if st.session_state.tw_track else "PEAK TRACK"
            if st.button(pk_lbl,       width='stretch', key="tw_peak_btn"):
                st.session_state.tw_track = not st.session_state.tw_track
                if st.session_state.tw_track: st.session_state.tw_peak = torque_nm
        with c5:
            if st.button("RESET PEAK", width='stretch', key="tw_rpeak"):
                st.session_state.tw_peak = 0.0

        # Trigger
        st.markdown('<div class="panel-title" style="margin-top:8px">TRIGGER POINT (N·m)</div>', unsafe_allow_html=True)

        if st.session_state.tw_tgt > max_nm:
            st.session_state.tw_tgt = float(max_nm)

        t1, t2 = st.columns(2)
        with t1:
                st.session_state.tw_tgt = st.number_input(
                    "Target (N·m)",
                    0.0,
                    float(max_nm),
                    value=st.session_state.tw_tgt,
                    step=0.5,
                    key="tw_tgt_i",
                    format="%.1f"
                    )
        with t2: st.session_state.tw_tol = st.number_input("Tol ± (N·m)",  0.0, 20.0,         value=st.session_state.tw_tol, step=0.1, key="tw_tol_i", format="%.1f")

        display_nm = st.session_state.tw_held if st.session_state.tw_hold else torque_nm
        passed = in_tol(display_nm, st.session_state.tw_tgt, st.session_state.tw_tol)

        trig = st.button("⊙  TRIGGER CAPTURE", width='stretch',
                         type="primary" if is_conn else "secondary", key="tw_trig")
        if trig:
            if is_conn:
                add_packet(display_nm)
                st.session_state.tw_log.insert(0, {
                    "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "value": f"{display_nm*conv:.2f} {unit}",
                    "raw": display_nm, "passed": passed,
                })
            else: st.warning("Connect Bluetooth first.")

        if st.session_state.tw_log:
            if st.button("CLEAR LOG", width='stretch', key="tw_cl"): st.session_state.tw_log = []
            total = len(st.session_state.tw_log); p_count = sum(1 for e in st.session_state.tw_log if e["passed"])
            rows = ""
            for i, e in enumerate(st.session_state.tw_log[:8]):
                tc="log-pass" if e["passed"] else "log-fail"
                rows += f'<div class="log-row"><span class="log-time">#{total-i:03d} {e["time"]}</span><span class="log-val">{e["value"]}</span><span class="{tc}">{"✔" if e["passed"] else "✖"}</span></div>'
            st.markdown(f'<div class="log-wrap"><div class="log-hdr">📡 {total} READINGS · {p_count}/{total} PASS</div>{rows}</div>', unsafe_allow_html=True)
            df = pd.DataFrame(st.session_state.tw_log)
            st.download_button("⬇ Export CSV", df.to_csv(index=False), "torque_log.csv", "text/csv", width='stretch', key="tw_exp")

    with col_svg:
        display_nm = st.session_state.tw_held if st.session_state.tw_hold else torque_nm
        st.markdown(torque_svg(display_nm, max_nm, unit, st.session_state.tw_tgt, st.session_state.tw_tol, is_conn, st.session_state.tw_hold, st.session_state.tw_peak), unsafe_allow_html=True)

        passed = in_tol(display_nm, st.session_state.tw_tgt, st.session_state.tw_tol)
        pct = min(display_nm/max_nm, 1.0) if max_nm > 0 else 0
        accent = "#00dd55" if pct < 0.7 else ("#ffaa00" if pct < 0.9 else "#ff2828")
        tol_str = f'<span style="color:{"#00dd55" if passed else "#ff3333"}">{"✔ IN TOL" if passed else "✖ OUT TOL"}</span>'
        peak_str = f'<span style="color:#ff6600">PEAK {st.session_state.tw_peak*conv:.1f} {unit}</span>' if st.session_state.tw_track else ""
        st.markdown(f"""
        <div class="lcd-outer" style="margin-top:8px">
          <div class="lcd-label">{"📡 BT CONNECTED" if is_conn else "⚪ BT OFF"} {"· HOLD" if st.session_state.tw_hold else ""}</div>
          <div class="lcd-main" style="color:{accent};text-shadow:0 0 20px {accent}88;font-size:3rem">{display_nm*conv:.2f}</div>
          <div class="lcd-unit" style="color:{accent}66">{unit} · Drive {drive} · Max {max_nm*conv:.0f} {unit}</div>
          <div class="lcd-sub">TGT {st.session_state.tw_tgt*conv:.1f} ± {st.session_state.tw_tol*conv:.1f} {unit} &nbsp;|&nbsp; {tol_str} &nbsp; {peak_str}</div>
        </div>""", unsafe_allow_html=True)