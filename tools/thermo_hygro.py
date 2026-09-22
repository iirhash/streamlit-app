# -*- coding: utf-8 -*-
"""
Created on Mon Jun 22 08:30:52 2026

@author: Karina Nur C
"""

# tools/thermo_hygro.py
import streamlit as st
import math
from datetime import datetime
from tools.utils import add_packet, in_tol
import pandas as pd

def thermo_svg(temp_c, humidity, dew_c, heat_idx_c, unit, bt_on, hold, t_tgt, t_tol, h_tgt, h_tol):
    W, H = 300, 520
    temp_disp = temp_c if unit == "°C" else temp_c * 9/5 + 32
    dew_disp  = dew_c  if unit == "°C" else dew_c  * 9/5 + 32
    hi_disp   = heat_idx_c if unit == "°C" else heat_idx_c * 9/5 + 32
    t_range   = (0, 100) if unit == "°C" else (32, 212)
    t_pct     = (temp_disp - t_range[0]) / (t_range[1] - t_range[0])
    t_pct     = max(0, min(1, t_pct))
    h_pct     = humidity / 100

    # Comfort zone colors
    t_col = "#00ccff" if temp_disp < (20 if unit=="°C" else 68) else ("#00dd55" if temp_disp < (26 if unit=="°C" else 79) else ("#ffaa00" if temp_disp < (35 if unit=="°C" else 95) else "#ff2828"))
    h_col = "#ff8800" if humidity < 30 else ("#00dd55" if humidity < 60 else ("#ffaa00" if humidity < 80 else "#ff2828"))

    # Dew point comfort
    dp_label = "DRY" if dew_c < 10 else ("COMFORT" if dew_c < 16 else ("STICKY" if dew_c < 21 else "HUMID"))
    dp_col   = "#00ccff" if dew_c < 10 else ("#00dd55" if dew_c < 16 else ("#ffaa00" if dew_c < 21 else "#ff2828"))

    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" style="background:transparent;width:100%">',
        '<defs>',
        f'<linearGradient id="thBody" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#1e2230"/><stop offset="100%" stop-color="#12141c"/></linearGradient>',
        f'<linearGradient id="thBulb" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="{t_col}"/><stop offset="100%" stop-color="{t_col}88"/></linearGradient>',
        '</defs>',
        # Body
        f'<rect x="10" y="10" width="280" height="500" rx="20" fill="url(#thBody)" stroke="#2a2d38" stroke-width="1.5"/>',
        # Brand
        f'<text x="150" y="28" font-family="Rajdhani,sans-serif" font-weight="700" font-size="10" fill="#333" text-anchor="middle" letter-spacing="3">DIGIMETER · TH-200BT</text>',
        # BT LED
        f'<circle cx="26" cy="24" r="4" fill="{"#1a7fff" if bt_on else "#1a1d28"}"/>',
        f'<text x="35" y="28" font-family="monospace" font-size="7" fill="{"#1a7fff" if bt_on else "#1a1d28"}">BT</text>',
        f'<text x="275" y="28" font-family="monospace" font-size="7" fill="{"#ddaa00" if hold else "#1a1d28"}" text-anchor="end">HOLD</text>',

        # ── Temperature LCD ──
        f'<rect x="20" y="35" width="260" height="90" rx="8" fill="#060e06" stroke="#102010" stroke-width="1.5"/>',
        f'<text x="150" y="52" font-family="monospace" font-size="7" fill="#1a3a1a" text-anchor="middle" letter-spacing="2">TEMPERATURE</text>',
        f'<text x="150" y="100" font-family="Share Tech Mono,monospace" font-size="44" fill="{t_col}" text-anchor="middle" style="text-shadow:0 0 18px {t_col}88">{temp_disp:.1f}</text>',
        f'<text x="262" y="115" font-family="monospace" font-size="14" fill="{t_col}88" text-anchor="end">{unit}</text>',

        # ── Humidity LCD ──
        f'<rect x="20" y="135" width="260" height="70" rx="8" fill="#060e06" stroke="#102010" stroke-width="1.5"/>',
        f'<text x="150" y="151" font-family="monospace" font-size="7" fill="#1a2a1a" text-anchor="middle" letter-spacing="2">RELATIVE HUMIDITY</text>',
        f'<text x="150" y="192" font-family="Share Tech Mono,monospace" font-size="36" fill="{h_col}" text-anchor="middle" style="text-shadow:0 0 14px {h_col}88">{humidity:.1f}</text>',
        f'<text x="246" y="196" font-family="monospace" font-size="13" fill="{h_col}88">%</text>',

        # ── Thermometer visual ──
        # tube
        f'<rect x="45" y="215" width="16" height="120" rx="8" fill="#0d0f14" stroke="#1e2028" stroke-width="1.5"/>',
        # fill
        f'<rect x="47" y="{215 + int(120*(1-t_pct))}" width="12" height="{int(120*t_pct)}" rx="4" fill="{t_col}" opacity="0.8"/>',
        # bulb
        f'<circle cx="53" cy="346" r="12" fill="url(#thBulb)" stroke="#1e2028" stroke-width="1.5"/>',
        # tick marks on thermometer
        *[f'<line x1="61" y1="{215+i*12}" x2="{65 if i%5==0 else 63}" y2="{215+i*12}" stroke="#1e2028" stroke-width="{1.2 if i%5==0 else 0.7}"/>' for i in range(11)],

        # ── Humidity bar ──
        f'<rect x="80" y="215" width="18" height="120" rx="4" fill="#0d0f14" stroke="#1e2028" stroke-width="1.5"/>',
        # comfort zones
        f'<rect x="82" y="{215+int(120*0.2)}" width="14" height="{int(120*0.4)}" rx="2" fill="#00dd5520"/>',
        f'<rect x="82" y="{215 + int(120*(1-h_pct))}" width="14" height="{int(120*h_pct)}" rx="2" fill="{h_col}" opacity="0.8"/>',
        # % labels
        *[f'<text x="100" y="{215+i*30+3}" font-family="monospace" font-size="6" fill="#1e2028">{100-i*25}%</text>' for i in range(5)],

        # Labels under bars
        f'<text x="53" y="368" font-family="monospace" font-size="6.5" fill="{t_col}" text-anchor="middle">{unit}</text>',
        f'<text x="89" y="368" font-family="monospace" font-size="6.5" fill="{h_col}" text-anchor="middle">RH</text>',

        # ── Secondary readings ──
        f'<rect x="110" y="215" width="170" height="150" rx="8" fill="#0a0d10" stroke="#1a1d28" stroke-width="1"/>',
        # Dew point
        f'<text x="120" y="235" font-family="monospace" font-size="7" fill="#1a2a1a">DEW POINT</text>',
        f'<text x="270" y="235" font-family="Share Tech Mono,monospace" font-size="13" fill="{dp_col}" text-anchor="end">{dew_disp:.1f}{unit}</text>',
        f'<text x="120" y="248" font-family="monospace" font-size="6" fill="{dp_col}">{dp_label}</text>',
        # Divider
        f'<line x1="115" y1="255" x2="275" y2="255" stroke="#1a1d28" stroke-width="0.8"/>',
        # Heat index
        f'<text x="120" y="270" font-family="monospace" font-size="7" fill="#1a2a1a">HEAT INDEX</text>',
        f'<text x="270" y="270" font-family="Share Tech Mono,monospace" font-size="13" fill="#ffaa00" text-anchor="end">{hi_disp:.1f}{unit}</text>',
        # Divider
        f'<line x1="115" y1="280" x2="275" y2="280" stroke="#1a1d28" stroke-width="0.8"/>',
        # Comfort rating
    ]
    comfort = "COLD" if temp_disp<(18 if unit=="°C" else 64) else ("COOL" if temp_disp<(22 if unit=="°C" else 72) else ("COMFY" if temp_disp<(26 if unit=="°C" else 79) else ("WARM" if temp_disp<(30 if unit=="°C" else 86) else "HOT")))
    comfort_col = {"COLD":"#00ccff","COOL":"#88ccff","COMFY":"#00dd55","WARM":"#ffaa00","HOT":"#ff2828"}.get(comfort,"#00dd55")

    abs_h = 6.112 * math.exp(17.67*temp_c/(temp_c+243.5)) * humidity * 2.1674 / (273.15+temp_c)

    t_ok = in_tol(temp_disp, t_tgt, t_tol)
    h_ok = in_tol(humidity, h_tgt, h_tol)

    p += [
        f'<text x="120" y="298" font-family="monospace" font-size="7" fill="#1a2a1a">COMFORT</text>',
        f'<text x="270" y="298" font-family="Share Tech Mono,monospace" font-size="13" fill="{comfort_col}" text-anchor="end">{comfort}</text>',
        f'<line x1="115" y1="306" x2="275" y2="306" stroke="#1a1d28" stroke-width="0.8"/>',

        f'<text x="120" y="323" font-family="monospace" font-size="7" fill="#1a2a1a">ABS HUMIDITY</text>',
        f'<text x="270" y="323" font-family="Share Tech Mono,monospace" font-size="11" fill="#88aacc" text-anchor="end">{abs_h:.2f} g/m³</text>',
        f'<line x1="115" y1="332" x2="275" y2="332" stroke="#1a1d28" stroke-width="0.8"/>',

        f'<text x="120" y="350" font-family="monospace" font-size="7" fill="#1a2a1a">TRIGGER STATUS</text>',
        f'<text x="150" y="358" font-family="monospace" font-size="7" fill="{"#00dd55" if t_ok else "#ff2828"}">T:{"✔" if t_ok else "✖"}</text>',
        f'<text x="200" y="358" font-family="monospace" font-size="7" fill="{"#00dd55" if h_ok else "#ff2828"}">RH:{"✔" if h_ok else "✖"}</text>',
]

    # Buttons
    for bx, blbl in [(55,"HOLD"),(100,"UNIT"),(150,"MAX"),(200,"MIN"),(248,"BT")]:
        p += [
            f'<rect x="{bx-18}" y="490" width="36" height="14" rx="3" fill="#141620" stroke="#2a2d38" stroke-width="1"/>',
            f'<text x="{bx}" y="500" font-family="monospace" font-size="5.5" fill="#333" text-anchor="middle">{blbl}</text>',
        ]

    p.append('</svg>')
    return '\n'.join(p)


def calc_dew(temp_c, rh):
    a, b = 17.27, 237.7
    gamma = (a * temp_c / (b + temp_c)) + math.log(rh / 100.0)
    return b * gamma / (a - gamma)

def calc_heat_index(temp_c, rh):
    t = temp_c * 9/5 + 32
    hi = (-42.379 + 2.04901523*t + 10.14333127*rh - 0.22475541*t*rh
          - 6.83783e-3*t**2 - 5.481717e-2*rh**2 + 1.22874e-3*t**2*rh
          + 8.5282e-4*t*rh**2 - 1.99e-6*t**2*rh**2)
    return (hi - 32) * 5/9


def render_thermo():
    if "th_temp"  not in st.session_state: st.session_state.th_temp  = 24.5
    if "th_hum"   not in st.session_state: st.session_state.th_hum   = 58.0
    if "th_unit"  not in st.session_state: st.session_state.th_unit  = "°C"
    if "th_hold"  not in st.session_state: st.session_state.th_hold  = False
    if "th_held_t"not in st.session_state: st.session_state.th_held_t= 0.0
    if "th_held_h"not in st.session_state: st.session_state.th_held_h= 0.0
    if "th_tgt_t" not in st.session_state: st.session_state.th_tgt_t = 25.0
    if "th_tol_t" not in st.session_state: st.session_state.th_tol_t = 1.0
    if "th_tgt_h" not in st.session_state: st.session_state.th_tgt_h = 55.0
    if "th_tol_h" not in st.session_state: st.session_state.th_tol_h = 5.0
    if "th_log"   not in st.session_state: st.session_state.th_log   = []
    if "th_max_t" not in st.session_state: st.session_state.th_max_t = -999.0
    if "th_min_t" not in st.session_state: st.session_state.th_min_t = 999.0

    is_conn = st.session_state.bt_phase == "connected"
    unit    = st.session_state.th_unit

    col_svg, col_ctrl = st.columns([1, 1.6])

    with col_ctrl:
        st.markdown('<div class="panel-title">ENVIRONMENT INPUT</div>', unsafe_allow_html=True)

        temp_c = st.slider("Temperature (°C)", -20.0, 60.0, value=st.session_state.th_temp, step=0.1, key="th_t_sl", format="%.1f °C")
        hum    = st.slider("Humidity (%RH)",     0.0,100.0, value=st.session_state.th_hum,  step=0.1, key="th_h_sl", format="%.1f %%")
        st.session_state.th_temp = temp_c
        st.session_state.th_hum  = hum

        if temp_c > st.session_state.th_max_t: st.session_state.th_max_t = temp_c
        if temp_c < st.session_state.th_min_t: st.session_state.th_min_t = temp_c

        dew_c    = calc_dew(temp_c, hum)
        heat_idx = calc_heat_index(temp_c, hum)

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("°C / °F", width='stretch', key="th_unit_btn"):
                st.session_state.th_unit = "°F" if unit=="°C" else "°C"
        with c2:
            if st.button("HOLD",    width='stretch', key="th_hold_btn"):
                st.session_state.th_hold = not st.session_state.th_hold
                if st.session_state.th_hold:
                    st.session_state.th_held_t = temp_c
                    st.session_state.th_held_h = hum
        with c3:
            if st.button("RESET MAX/MIN", width='stretch', key="th_rst"):
                st.session_state.th_max_t = temp_c; st.session_state.th_min_t = temp_c

        # Info cards
        temp_disp = temp_c if unit=="°C" else temp_c*9/5+32
        dew_disp  = dew_c  if unit=="°C" else dew_c*9/5+32
        hi_disp   = heat_idx if unit=="°C" else heat_idx*9/5+32
        max_disp  = st.session_state.th_max_t if unit=="°C" else st.session_state.th_max_t*9/5+32
        min_disp  = st.session_state.th_min_t if unit=="°C" else st.session_state.th_min_t*9/5+32
        st.markdown(f"""
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:8px 0">
          <div class="reading-card" style="background:#090c10;border:1px solid #1a1d28;border-radius:6px;padding:8px;font-family:Share Tech Mono,monospace">
            <div style="color:#333;font-size:0.6rem">DEW POINT</div>
            <div style="color:#88aaff;font-size:1rem">{dew_disp:.1f}{unit}</div>
          </div>
          <div class="reading-card" style="background:#090c10;border:1px solid #1a1d28;border-radius:6px;padding:8px;font-family:Share Tech Mono,monospace">
            <div style="color:#333;font-size:0.6rem">HEAT INDEX</div>
            <div style="color:#ffaa00;font-size:1rem">{hi_disp:.1f}{unit}</div>
          </div>
          <div class="reading-card" style="background:#090c10;border:1px solid #1a1d28;border-radius:6px;padding:8px;font-family:Share Tech Mono,monospace">
            <div style="color:#333;font-size:0.6rem">MAX TEMP</div>
            <div style="color:#ff6600;font-size:1rem">{max_disp:.1f}{unit}</div>
          </div>
          <div class="reading-card" style="background:#090c10;border:1px solid #1a1d28;border-radius:6px;padding:8px;font-family:Share Tech Mono,monospace">
            <div style="color:#333;font-size:0.6rem">MIN TEMP</div>
            <div style="color:#00ccff;font-size:1rem">{min_disp:.1f}{unit}</div>
          </div>
        </div>""", unsafe_allow_html=True)

        # Trigger
        st.markdown('<div class="panel-title">TRIGGER POINT</div>', unsafe_allow_html=True)
        ta, tb = st.columns(2)
        with ta: st.session_state.th_tgt_t = st.number_input("Temp target (°C)", -20.0, 60.0, value=st.session_state.th_tgt_t, step=0.5, key="th_tt", format="%.1f")
        with tb: st.session_state.th_tol_t = st.number_input("Temp tol ±",        0.0,  10.0, value=st.session_state.th_tol_t, step=0.1, key="th_tl", format="%.1f")
        ha, hb = st.columns(2)
        with ha: st.session_state.th_tgt_h = st.number_input("Humidity target (%)", 0.0, 100.0, value=st.session_state.th_tgt_h, step=1.0, key="th_ht", format="%.1f")
        with hb: st.session_state.th_tol_h = st.number_input("Humidity tol ±",      0.0,  20.0, value=st.session_state.th_tol_h, step=0.5, key="th_hl", format="%.1f")

        dt = st.session_state.th_held_t if st.session_state.th_hold else temp_c
        dh = st.session_state.th_held_h if st.session_state.th_hold else hum
        t_ok = in_tol(dt, st.session_state.th_tgt_t, st.session_state.th_tol_t)
        h_ok = in_tol(dh, st.session_state.th_tgt_h, st.session_state.th_tol_h)
        both = t_ok and h_ok

        trig = st.button("⊙  TRIGGER CAPTURE", width='stretch',
                         type="primary" if is_conn else "secondary", key="th_trig")
        if trig:
            if is_conn:
                add_packet(dt)
                td = dt if unit=="°C" else dt*9/5+32
                st.session_state.th_log.insert(0, {
                    "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "value": f"T:{td:.1f}{unit} RH:{dh:.1f}%",
                    "temp_c": dt, "hum": dh, "passed": both,
                })
            else: st.warning("Connect Bluetooth first.")

        if st.session_state.th_log:
            if st.button("CLEAR LOG", width='stretch', key="th_cl"): st.session_state.th_log = []
            total = len(st.session_state.th_log); p_count = sum(1 for e in st.session_state.th_log if e["passed"])
            rows = ""
            for i, e in enumerate(st.session_state.th_log[:8]):
                tc="log-pass" if e["passed"] else "log-fail"
                rows += f'<div class="log-row"><span class="log-time">#{total-i:03d} {e["time"]}</span><span class="log-val">{e["value"]}</span><span class="{tc}">{"✔" if e["passed"] else "✖"}</span></div>'
            st.markdown(f'<div class="log-wrap"><div class="log-hdr">📡 {total} READINGS · {p_count}/{total} PASS</div>{rows}</div>', unsafe_allow_html=True)
            df = pd.DataFrame(st.session_state.th_log)
            st.download_button("⬇ Export CSV", df.to_csv(index=False), "thermo_log.csv", "text/csv", width='stretch', key="th_exp")

    with col_svg:
        dt = st.session_state.th_held_t if st.session_state.th_hold else temp_c
        dh = st.session_state.th_held_h if st.session_state.th_hold else hum
        st.markdown(thermo_svg(dt, dh, calc_dew(dt,dh), calc_heat_index(dt,dh), unit, is_conn, st.session_state.th_hold,
                               st.session_state.th_tgt_t, st.session_state.th_tol_t,
                               st.session_state.th_tgt_h, st.session_state.th_tol_h), unsafe_allow_html=True)