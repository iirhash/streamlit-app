# -*- coding: utf-8 -*-
"""
Created on Mon Jun 22 08:30:52 2026

@author: Karina Nur C
"""

# tools/sound_meter.py
import streamlit as st
import math
from datetime import datetime
from tools.utils import add_packet, in_tol
import pandas as pd

WEIGHTINGS = ["A-weighted (dBA)", "C-weighted (dBC)", "Z-weighted (dBZ)"]
RESPONSE   = ["FAST (125ms)", "SLOW (1000ms)"]

def db_color(db):
    if db < 55:  return "#00ccff"
    if db < 70:  return "#00dd55"
    if db < 85:  return "#ffaa00"
    if db < 95:  return "#ff6600"
    return "#ff2828"

def db_label(db):
    if db < 30:  return "SILENCE"
    if db < 45:  return "QUIET"
    if db < 55:  return "MODERATE"
    if db < 65:  return "NORMAL"
    if db < 75:  return "LOUD"
    if db < 85:  return "VERY LOUD"
    if db < 95:  return "HARMFUL"
    return "DANGEROUS"

def sound_svg(db, peak_db, max_db, min_db, weighting, bt_on, hold, tgt, tol):
    W, H = 300, 560
    col     = db_color(db)
    peak_col= db_color(peak_db)
    pct     = max(0, min(1, (db - 20) / 110))      # 20–130 dB range
    peak_pct= max(0, min(1, (peak_db - 20) / 110))

    # Octave bar heights (simulated spectrum)
    octaves = [63, 125, 250, 500, 1000, 2000, 4000, 8000]
    oct_labels = ["63", "125", "250", "500", "1k", "2k", "4k", "8k"]
    # Simple A-weighting-ish envelope
    aw_offsets = {"A-weighted (dBA)":[-26,-16,-9,-3,0,1,1,-1],
                  "C-weighted (dBC)":[-3,-1,0,0,0,0,-3,-8],
                  "Z-weighted (dBZ)":[0,0,0,0,0,0,0,0]}
    offsets = aw_offsets.get(weighting, [0]*8)
    oct_dbs = [max(20, db + o + (i*0.5 - 2)) for i, o in enumerate(offsets)]

    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" style="background:transparent;width:100%">',
        '<defs>',
        f'<linearGradient id="smBody" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#1e2230"/><stop offset="100%" stop-color="#12141c"/></linearGradient>',
        f'<linearGradient id="smMic"  x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#5a5d68"/><stop offset="100%" stop-color="#2a2d38"/></linearGradient>',
        '</defs>',
        # Body
        f'<rect x="10" y="10" width="280" height="540" rx="20" fill="url(#smBody)" stroke="#2a2d38" stroke-width="1.5"/>',
        # Brand
        f'<text x="150" y="27" font-family="Rajdhani,sans-serif" font-weight="700" font-size="10" fill="#333" text-anchor="middle" letter-spacing="3">DIGIMETER · SL-400BT</text>',
        # BT & HOLD
        f'<circle cx="26" cy="23" r="4" fill="{"#1a7fff" if bt_on else "#1a1d28"}"/>',
        f'<text x="275" y="27" font-family="monospace" font-size="7" fill="{"#ddaa00" if hold else "#1a1d28"}" text-anchor="end">HOLD</text>',

        # ── Main LCD ──
        f'<rect x="20" y="35" width="260" height="100" rx="8" fill="#060e06" stroke="#102010" stroke-width="1.5"/>',
        f'<text x="150" y="51" font-family="monospace" font-size="7" fill="#1a3a1a" text-anchor="middle" letter-spacing="2">SOUND PRESSURE LEVEL</text>',
        f'<text x="150" y="108" font-family="Share Tech Mono,monospace" font-size="52" fill="{col}" text-anchor="middle" style="text-shadow:0 0 22px {col}88">{db:.1f}</text>',
        f'<text x="262" y="118" font-family="monospace" font-size="13" fill="{col}88" text-anchor="end">{"dBA" if "A" in weighting else ("dBC" if "C" in weighting else "dBZ")}</text>',
        f'<text x="28" y="126" font-family="monospace" font-size="7" fill="#1a3a1a">{db_label(db)}</text>',
        f'<text x="272" y="126" font-family="monospace" font-size="7" fill="#1a3a1a" text-anchor="end">{weighting.split(" ")[0]}</text>',

        # ── Analog VU meter arc ──
        f'<circle cx="150" cy="220" r="85" fill="none" stroke="#141820" stroke-width="2"/>',
    ]

    # Arc segments (180° arc at bottom)
    SEGS = 36
    for i in range(SEGS):
        ang1 = math.radians(180 + i * (180/SEGS))
        ang2 = math.radians(180 + (i+1)*(180/SEGS))
        r_in, r_out = 60, 82
        x1=150+r_in*math.cos(ang1);  y1=220+r_in*math.sin(ang1)
        x2=150+r_in*math.cos(ang2);  y2=220+r_in*math.sin(ang2)
        x3=150+r_out*math.cos(ang2); y3=220+r_out*math.sin(ang2)
        x4=150+r_out*math.cos(ang1); y4=220+r_out*math.sin(ang1)
        seg_db = 20 + i * (110/SEGS)
        seg_col = db_color(seg_db)
        filled  = (db - 20) / 110 > i/SEGS
        op = 0.85 if filled else 0.12
        p.append(f'<polygon points="{x1:.1f},{y1:.1f} {x2:.1f},{y2:.1f} {x3:.1f},{y3:.1f} {x4:.1f},{y4:.1f}" fill="{seg_col}" opacity="{op}"/>')

    # Needle
    needle_ang = math.radians(180 + pct * 180)
    nx = 150 + 75 * math.cos(needle_ang)
    ny = 220 + 75 * math.sin(needle_ang)
    p += [
        f'<line x1="150" y1="220" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{col}" stroke-width="2.5" stroke-linecap="round"/>',
        f'<circle cx="150" cy="220" r="6" fill="#1e2028" stroke="{col}" stroke-width="1.5"/>',
        # dB labels on arc
        *[f'<text x="{150 + 90*math.cos(math.radians(180+pv/110*180)):.0f}" y="{220 + 90*math.sin(math.radians(180+pv/110*180))+3:.0f}" font-family="monospace" font-size="6" fill="#1e2030" text-anchor="middle">{int(pv+20)}</text>' for pv in [0,22,44,66,88,110]],
        # Peak marker
        f'<line x1="{150 + 62*math.cos(math.radians(180+peak_pct*180)):.1f}" y1="{220 + 62*math.sin(math.radians(180+peak_pct*180)):.1f}" x2="{150 + 80*math.cos(math.radians(180+peak_pct*180)):.1f}" y2="{220 + 80*math.sin(math.radians(180+peak_pct*180)):.1f}" stroke="{peak_col}" stroke-width="2"/>',
    ]

    # ── Stats row ──
    p += [
        f'<rect x="20" y="306" width="260" height="40" rx="6" fill="#090c10" stroke="#141820" stroke-width="1"/>',
        f'<text x="55"  y="321" font-family="monospace" font-size="6" fill="#1a2a1a" text-anchor="middle">MAX</text>',
        f'<text x="55"  y="334" font-family="Share Tech Mono,monospace" font-size="10" fill="#ff6600" text-anchor="middle">{max_db:.1f}</text>',
        f'<text x="108" y="321" font-family="monospace" font-size="6" fill="#1a2a1a" text-anchor="middle">MIN</text>',
        f'<text x="108" y="334" font-family="Share Tech Mono,monospace" font-size="10" fill="#00ccff" text-anchor="middle">{min_db:.1f}</text>',
        f'<text x="162" y="321" font-family="monospace" font-size="6" fill="#1a2a1a" text-anchor="middle">PEAK</text>',
        f'<text x="162" y="334" font-family="Share Tech Mono,monospace" font-size="10" fill="{peak_col}" text-anchor="middle">{peak_db:.1f}</text>',
        f'<text x="222" y="321" font-family="monospace" font-size="6" fill="#1a2a1a" text-anchor="middle">STATUS</text>',
        f'<text x="222" y="334" font-family="monospace" font-size="8" fill="{col}" text-anchor="middle">{db_label(db)}</text>',
    ]

    # ── Octave spectrum bars ──
    p += [f'<rect x="20" y="355" width="260" height="110" rx="6" fill="#090c10" stroke="#141820" stroke-width="1"/>',
          f'<text x="30" y="370" font-family="monospace" font-size="6" fill="#1a2a1a">OCTAVE BAND SPECTRUM (Hz)</text>']
    bar_w = 26; gap = 5; bx_start = 28
    for i, (odb, olbl) in enumerate(zip(oct_dbs, oct_labels)):
        bx  = bx_start + i*(bar_w+gap)
        bpct= max(0, min(1, (odb-20)/110))
        bh  = int(bpct * 70)
        bcol= db_color(odb)
        p += [
            f'<rect x="{bx}" y="378" width="{bar_w}" height="70" rx="2" fill="#0d0f14"/>',
            f'<rect x="{bx}" y="{378+70-bh}" width="{bar_w}" height="{bh}" rx="2" fill="{bcol}" opacity="0.8"/>',
            f'<text x="{bx+bar_w//2}" y="458" font-family="monospace" font-size="6" fill="#1e2028" text-anchor="middle">{olbl}</text>',
            f'<text x="{bx+bar_w//2}" y="375" font-family="monospace" font-size="5.5" fill="{bcol}88" text-anchor="middle">{odb:.0f}</text>',
        ]

    # Microphone graphic (top decorative)
    p += [
        f'<ellipse cx="150" cy="488" rx="20" ry="28" fill="url(#smMic)" stroke="#3a3d48" stroke-width="1.5"/>',
        *[f'<line x1="133" y1="{478+i*6}" x2="167" y2="{478+i*6}" stroke="#1e2028" stroke-width="0.8"/>' for i in range(6)],
        f'<rect x="146" y="516" width="8" height="16" rx="2" fill="#2a2d38" stroke="#3a3d48" stroke-width="1"/>',
        f'<rect x="136" y="530" width="28" height="6" rx="3" fill="#2a2d38" stroke="#3a3d48" stroke-width="1"/>',
    ]

    p.append('</svg>')
    return '\n'.join(p)


def render_sound_meter():
    if "sm_db"    not in st.session_state: st.session_state.sm_db    = 62.5
    if "sm_peak"  not in st.session_state: st.session_state.sm_peak  = 62.5
    if "sm_max"   not in st.session_state: st.session_state.sm_max   = 62.5
    if "sm_min"   not in st.session_state: st.session_state.sm_min   = 62.5
    if "sm_wt"    not in st.session_state: st.session_state.sm_wt    = WEIGHTINGS[0]
    if "sm_resp"  not in st.session_state: st.session_state.sm_resp  = RESPONSE[0]
    if "sm_hold"  not in st.session_state: st.session_state.sm_hold  = False
    if "sm_held"  not in st.session_state: st.session_state.sm_held  = 0.0
    if "sm_tgt"   not in st.session_state: st.session_state.sm_tgt   = 65.0
    if "sm_tol"   not in st.session_state: st.session_state.sm_tol   = 3.0
    if "sm_log"   not in st.session_state: st.session_state.sm_log   = []
    if "sm_track" not in st.session_state: st.session_state.sm_track = False

    is_conn = st.session_state.bt_phase == "connected"

    col_svg, col_ctrl = st.columns([1, 1.6])

    with col_ctrl:
        st.markdown('<div class="panel-title">MEASUREMENT SETTINGS</div>', unsafe_allow_html=True)
        wt   = st.selectbox("Frequency Weighting", WEIGHTINGS, index=WEIGHTINGS.index(st.session_state.sm_wt), key="sm_wt_sel")
        resp = st.selectbox("Time Response",        RESPONSE,   index=RESPONSE.index(st.session_state.sm_resp), key="sm_resp_sel")
        st.session_state.sm_wt = wt; st.session_state.sm_resp = resp

        db = st.slider("Sound Level (dB)", 20.0, 130.0, value=st.session_state.sm_db, step=0.1, key="sm_db_sl", format="%.1f dB")
        st.session_state.sm_db = db

        if db > st.session_state.sm_max: st.session_state.sm_max = db
        if db < st.session_state.sm_min: st.session_state.sm_min = db
        if st.session_state.sm_track and db > st.session_state.sm_peak: st.session_state.sm_peak = db

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("HOLD",        width='stretch', key="sm_hold_btn"):
                st.session_state.sm_hold = not st.session_state.sm_hold
                if st.session_state.sm_hold: st.session_state.sm_held = db
        with c2:
            pk_lbl = "STOP PEAK" if st.session_state.sm_track else "PEAK HOLD"
            if st.button(pk_lbl,        width='stretch', key="sm_pk_btn"):
                st.session_state.sm_track = not st.session_state.sm_track
                if st.session_state.sm_track: st.session_state.sm_peak = db
        with c3:
            if st.button("RESET",       width='stretch', key="sm_rst"):
                st.session_state.sm_max = db; st.session_state.sm_min = db; st.session_state.sm_peak = db

        # Exposure info
        disp_db = st.session_state.sm_held if st.session_state.sm_hold else db
        safe_hrs = max(0, 2 ** ((85 - disp_db) / 3)) if disp_db > 60 else 999
        st.markdown(f"""
        <div style="background:#090c10;border:1px solid #1a1d28;border-radius:6px;padding:8px 10px;font-family:Share Tech Mono,monospace;font-size:0.68rem;margin:8px 0">
          <div style="color:#1a2a1a;font-size:0.58rem;letter-spacing:0.15em">EXPOSURE GUIDE (NIOSH)</div>
          <div style="color:{"#ff2828" if disp_db>85 else "#00dd55"};margin-top:4px">
            Safe exposure: {"< 0.1 hr" if safe_hrs < 0.1 else (f"{safe_hrs:.1f} hrs" if safe_hrs < 999 else "Unlimited")}
          </div>
          <div style="color:#1a3a1a;font-size:0.6rem;margin-top:2px">85 dB limit · 3 dB exchange rate</div>
        </div>""", unsafe_allow_html=True)

        # Trigger
        st.markdown('<div class="panel-title">TRIGGER POINT</div>', unsafe_allow_html=True)
        t1, t2 = st.columns(2)
        with t1: st.session_state.sm_tgt = st.number_input("Target (dB)", 20.0, 130.0, value=st.session_state.sm_tgt, step=0.5, key="sm_tgt_i", format="%.1f")
        with t2: st.session_state.sm_tol = st.number_input("Tol ± (dB)",   0.0,  20.0, value=st.session_state.sm_tol, step=0.5, key="sm_tol_i", format="%.1f")

        passed = in_tol(disp_db, st.session_state.sm_tgt, st.session_state.sm_tol)
        trig = st.button("⊙  TRIGGER CAPTURE", width='stretch',
                         type="primary" if is_conn else "secondary", key="sm_trig")
        if trig:
            if is_conn:
                add_packet(disp_db)
                st.session_state.sm_log.insert(0, {
                    "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "value": f"{disp_db:.1f} dB  {db_label(disp_db)}",
                    "raw": disp_db, "passed": passed,
                })
            else: st.warning("Connect Bluetooth first.")

        if st.session_state.sm_log:
            if st.button("CLEAR LOG", width='stretch', key="sm_cl"): st.session_state.sm_log = []
            total = len(st.session_state.sm_log); p_count = sum(1 for e in st.session_state.sm_log if e["passed"])
            rows = ""
            for i, e in enumerate(st.session_state.sm_log[:8]):
                tc="log-pass" if e["passed"] else "log-fail"
                rows += f'<div class="log-row"><span class="log-time">#{total-i:03d} {e["time"]}</span><span class="log-val">{e["value"]}</span><span class="{tc}">{"✔" if e["passed"] else "✖"}</span></div>'
            st.markdown(f'<div class="log-wrap"><div class="log-hdr">📡 {total} READINGS · {p_count}/{total} PASS</div>{rows}</div>', unsafe_allow_html=True)
            df = pd.DataFrame(st.session_state.sm_log)
            st.download_button("⬇ Export CSV", df.to_csv(index=False), "sound_log.csv", "text/csv", width='stretch', key="sm_exp")

    with col_svg:
        disp_db = st.session_state.sm_held if st.session_state.sm_hold else db
        st.markdown(sound_svg(disp_db, st.session_state.sm_peak, st.session_state.sm_max,
                              st.session_state.sm_min, wt, is_conn, st.session_state.sm_hold,
                              st.session_state.sm_tgt, st.session_state.sm_tol), unsafe_allow_html=True)

        col = db_color(disp_db)
        passed = in_tol(disp_db, st.session_state.sm_tgt, st.session_state.sm_tol)
        tol_str = f'<span style="color:{"#00dd55" if passed else "#ff3333"}">{"✔ IN TOL" if passed else "✖ OUT TOL"}</span>'
        st.markdown(f"""
        <div class="lcd-outer" style="margin-top:8px">
          <div class="lcd-label">{"📡 BT CONNECTED" if is_conn else "⚪ BT OFF"} {"· HOLD" if st.session_state.sm_hold else ""} {"· PEAK HOLD" if st.session_state.sm_track else ""}</div>
          <div class="lcd-main" style="color:{col};text-shadow:0 0 20px {col}88;font-size:3rem">{disp_db:.1f}</div>
          <div class="lcd-unit" style="color:{col}66">{"dBA" if "A" in wt else ("dBC" if "C" in wt else "dBZ")} · {db_label(disp_db)}</div>
          <div class="lcd-sub">TGT {st.session_state.sm_tgt:.1f} ± {st.session_state.sm_tol:.1f} dB &nbsp;|&nbsp; {tol_str}</div>
        </div>""", unsafe_allow_html=True)