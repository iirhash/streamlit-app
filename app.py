# ─────────────────────────────────────────────────────────────────────────────
# BT PRECISION INSTRUMENTS SUITE  ·  app.py
# Run:  streamlit run app.py
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st
import sys, os, random, csv, math
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime
from tools.utils import rssi_bars_html, add_packet

st.set_page_config(
    page_title="BT Precision Instruments Suite",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Shared CSV path — always saves to data/ in the same folder as this file ──
# This is the SAME file main.py reads, so captures appear on the dashboard.
_HERE    = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(_HERE, "data", "condition_records.csv")

# ─── Thresholds — must match config/settings.py ──────────────────────────────
from config.settings import ALL_TOOLS as THRESHOLDS

# ─── Fake BT Devices ─────────────────────────────────────────────────────────
FAKE_DEVICES = [
    {"name": "Fluke-87V-BT",    "mac": "F0:08:D1:55:3A:77", "rssi": -58, "type": "Multimeter",    "battery": 84},
    {"name": "TW-DigiTork-500", "mac": "C4:DD:57:9A:1B:33", "rssi": -70, "type": "Torque Wrench", "battery": 67},
    {"name": "TH-EnviroSense",  "mac": "AA:BB:CC:DD:EE:01", "rssi": -63, "type": "Thermo/Hygro",  "battery": 91},
    {"name": "SL-SoundProBT",   "mac": "11:22:33:44:55:66", "rssi": -76, "type": "Sound Meter",   "battery": 55},
]

BLE_RANGES = {
    "Multimeter":    {"voltage": (210, 250), "current": (0.5, 18), "resistance": (5, 110)},
    "Torque Wrench": {"torque": (30, 70)},
    "Thermo/Hygro":  {"temp": (18, 38), "humidity": (30, 75)},
    "Sound Meter":   {"db": (45, 95)},
}

# ─── Session state ────────────────────────────────────────────────────────────
def _init():
    for k, v in {
        "bt_phase": "idle", "bt_devices": [], "bt_selected": None,
        "bt_rssi": -65, "bt_battery": 87, "bt_packets": [], "ble_live": {},
        # session info (who is doing the measurement)
        "session_tech": "", "session_emp": "", "session_asset": "",
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v
_init()

# ─── CSV writer ──────────────────────────────────────────────────────────────
def save_to_csv(tool_name, value, unit, passed, notes="captured via BT trigger"):
    """Write one reading to the shared condition_records.csv."""
    thr     = THRESHOLDS.get(tool_name, {})
    min_val = thr.get("min", "")
    max_val = thr.get("max", "")
    status  = "Within Range" if passed else "Out of Range"
    tech    = st.session_state.session_tech  or "Unknown"
    emp     = st.session_state.session_emp   or "---"
    asset   = st.session_state.session_asset or "---"

    os.makedirs(os.path.dirname(os.path.abspath(CSV_FILE)), exist_ok=True)
    write_header = not os.path.exists(CSV_FILE)

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow([
                "datetime","technician","employee_id","asset_id",
                "tool","value","unit","min","max","status",
                "defect","notes","photo",
            ])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            tech, emp, asset,
            tool_name, round(float(value), 3), unit,
            min_val, max_val, status,
            "none", notes, "",
        ])

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@500;600;700&display=swap');
html,body,[data-testid="stAppViewContainer"],[data-testid="stAppViewContainer"]>.main{ background:#f5f6f8 !important; color:#1a1d24 !important; }
[data-testid="block-container"]{ padding:1rem 1.6rem; max-width:1400px; }
section[data-testid="stSidebar"]{ background:#ffffff !important; border-right:1px solid #e0e2e8 !important; }
section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] span{ color:#1a1d24 !important; }
.panel{ background:#ffffff; border:1px solid #e0e2e8; border-radius:12px; padding:1rem 1.2rem; margin-bottom:0.8rem; box-shadow:0 2px 12px rgba(0,0,0,0.07); }
.panel-title{ font-family:'Rajdhani',sans-serif; font-weight:700; font-size:0.6rem; letter-spacing:0.22em; color:#9098b0; border-bottom:1px solid #e8eaf0; padding-bottom:4px; margin-bottom:8px; }
.bt-bar{ display:flex; align-items:center; gap:10px; background:#f0f2f7; border:1px solid #d8dbe6; border-radius:8px; padding:7px 12px; margin-bottom:0.8rem; font-family:'Share Tech Mono',monospace; font-size:0.68rem; color:#444; }
.bt-led{ width:10px; height:10px; border-radius:50%; flex-shrink:0; }
.bt-idle{ background:#c8cad4; }
.bt-scan{ background:#ffaa00; box-shadow:0 0 8px #ffaa0088; animation:pulse 0.6s infinite; }
.bt-conn{ background:#00bb44; box-shadow:0 0 10px #00bb4466; animation:blink 2s infinite; }
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.3}}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.6}}
.device-card{ background:#f8f9fc; border:1px solid #e0e2ea; border-radius:6px; padding:7px 10px; margin-bottom:5px; font-family:'Share Tech Mono',monospace; font-size:0.68rem; }
.device-card.selected{ border-color:#00bb44; background:#f0fbf4; }
.dev-name{ color:#3355cc; font-size:0.72rem; }
.dev-mac{ color:#aab0c0; font-size:0.6rem; }
.pkt-wrap{ background:#f8f9fc; border:1px solid #e0e2ea; border-radius:6px; padding:7px 9px; font-family:'Share Tech Mono',monospace; font-size:0.61rem; max-height:130px; overflow-y:auto; }
.pkt-row{ display:flex; gap:8px; padding:2px 0; border-bottom:1px solid #eef0f5; }
.pkt-time{ color:#b0b8cc; } .pkt-dir{ color:#2266cc; } .pkt-hex{ color:#996611; } .pkt-dec{ color:#008833; }
.lcd-outer{ background:#0d1a0d; border:2px solid #1a3a1a; border-radius:10px; padding:12px 18px 9px; box-shadow:inset 0 3px 14px rgba(0,0,0,0.6); }
.lcd-main{ font-family:'Share Tech Mono',monospace; font-size:3.6rem; font-weight:bold; color:#00dd55; text-shadow:0 0 22px rgba(0,210,80,0.55); line-height:1; }
.lcd-unit{ font-family:'Share Tech Mono',monospace; font-size:0.88rem; color:#1a7a1a; margin-top:2px; }
.lcd-sub{ font-family:'Share Tech Mono',monospace; font-size:0.63rem; color:#1a5a1a; margin-top:4px; }
.lcd-label{ font-family:'Share Tech Mono',monospace; font-size:0.56rem; letter-spacing:0.18em; color:#1a4a1a; margin-bottom:2px; }
.log-wrap{ background:#f8f9fc; border:1px solid #e0e2ea; border-radius:7px; padding:7px 9px; font-family:'Share Tech Mono',monospace; font-size:0.68rem; }
.log-hdr{ color:#2266cc; font-size:0.58rem; letter-spacing:0.14em; margin-bottom:4px; border-bottom:1px solid #e8eaf0; padding-bottom:3px; }
.log-row{ display:flex; justify-content:space-between; padding:2px 0; border-bottom:1px solid #eef0f5; }
.log-row:last-child{ border-bottom:none; }
.log-time{ color:#b0b8cc; } .log-val{ color:#1a1d24; } .log-pass{ color:#008833; } .log-fail{ color:#cc2222; }
[data-testid="stSlider"] label p{ font-family:'Share Tech Mono',monospace !important; color:#667 !important; font-size:0.67rem !important; }
.stButton>button{ font-family:'Rajdhani',sans-serif !important; font-weight:700 !important; letter-spacing:0.1em !important; border-radius:6px !important; border:1px solid #d0d3dc !important; background:#ffffff !important; color:#444 !important; }
.stButton>button:hover{ background:#f0f2f7 !important; border-color:#9098b0 !important; color:#1a1d24 !important; }
.ble-live-row{ background:#f0fbf4; border:1px solid #b8e8c8; border-radius:5px; padding:5px 10px; font-family:'Share Tech Mono',monospace; font-size:0.65rem; color:#006622; margin:3px 0; }
.saved-banner{ background:#f0fbf4; border:1px solid #00bb4466; border-radius:6px; padding:6px 12px; font-family:'Share Tech Mono',monospace; font-size:0.68rem; color:#006622; margin:6px 0; }
.saved-banner.fail{ background:#fff5f5; border-color:#cc222266; color:#cc2222; }
.session-box{ background:#f8f9fc; border:1px solid #e0e2ea; border-radius:8px; padding:8px 12px; font-family:'Share Tech Mono',monospace; font-size:0.65rem; margin-bottom:8px; color:#444; }
[data-testid="stTabs"] [data-baseweb="tab-list"]{ background:#eeeff5 !important; border-radius:8px; padding:2px; }
[data-testid="stTabs"] [data-baseweb="tab"]{ color:#667 !important; }
[data-testid="stTabs"] [aria-selected="true"]{ background:#ffffff !important; color:#1a1d24 !important; border-radius:6px; }
</style>
""", unsafe_allow_html=True)

# ─── Sidebar — session info ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="font-family:Rajdhani,sans-serif;font-weight:700;font-size:0.95rem;
    color:#333;letter-spacing:0.2em;padding:0.4rem 0 0.6rem;
    border-bottom:1px solid #1a1d24;margin-bottom:0.8rem">⚙ DIGIMETER SUITE</div>
    """, unsafe_allow_html=True)

    st.markdown('<div style="font-family:Share Tech Mono,monospace;font-size:0.6rem;color:#9098b0;letter-spacing:0.15em;margin-bottom:4px">SESSION INFO — saved with every capture</div>', unsafe_allow_html=True)
    st.session_state.session_tech  = st.text_input("Technician Name", value=st.session_state.session_tech,  placeholder="e.g. Ali Ahmad",  key="si_tech")
    st.session_state.session_emp   = st.text_input("Employee ID",      value=st.session_state.session_emp,   placeholder="e.g. 201234",     key="si_emp")
    st.session_state.session_asset = st.text_input("Asset ID",         value=st.session_state.session_asset, placeholder="e.g. V40A",       key="si_asset")

    def random_fill():
       st.session_state.si_tech = random.choice([
        "Ali Ahmad", "Farid Ismail", "Muhammad Adam", "Hazim Karim", "Iman Irhash"
    ])

       st.session_state.si_emp = random.choice([
        "201234", "256789", "298765", "243210", "297531"
    ])

       st.session_state.si_asset = random.choice([
        "V40A", "V40B", "V41A", "V41B", "V42A", "V42B"
    ])

    st.button(
        "🎲 Random fill",
        width='stretch',
        on_click=random_fill
)

    st.markdown("---")

    # Show where CSV is going
    csv_exists = os.path.exists(CSV_FILE)
    csv_rows   = 0
    if csv_exists:
        try:
            csv_rows = sum(1 for _ in open(CSV_FILE, encoding="utf-8")) - 1
        except Exception:
            pass

    csv_color = "#008833" if csv_exists else "#cc7700"
    st.markdown(f"""
    <div class="session-box">
      <div style="color:#9098b0;font-size:0.55rem;letter-spacing:0.15em;margin-bottom:4px">SAVING TO</div>
      <div style="color:{csv_color};font-size:0.6rem;word-break:break-all">{os.path.abspath(CSV_FILE)}</div>
      <div style="color:#008833;margin-top:4px">{csv_rows} rows saved</div>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.session_tech:
        st.warning("⚠ Fill in session info before capturing — readings need a name & asset.")

# ─── Header ──────────────────────────────────────────────────────────────────
st.markdown("""
<div style="display:flex;align-items:baseline;gap:14px;margin-bottom:1rem;
            border-bottom:1px solid #1a1d24;padding-bottom:0.8rem">
  <span style="font-family:Rajdhani,sans-serif;font-weight:700;font-size:1.1rem;
               color:#222;letter-spacing:0.2em">DIGIMETER INSTRUMENTS</span>
  <span style="font-family:Share Tech Mono,monospace;font-size:0.62rem;
               color:#9098b0;letter-spacing:0.2em">BLUETOOTH PRECISION SUITE v2.0</span>
</div>""", unsafe_allow_html=True)

# ─── BLE helpers ─────────────────────────────────────────────────────────────
def _gen_live(device_type):
    return {k: round(random.uniform(*rng), 2) for k, rng in BLE_RANGES.get(device_type, {}).items()}

def start_scan():
    st.session_state.bt_phase    = "found"
    st.session_state.bt_devices  = FAKE_DEVICES[:]
    st.session_state.bt_selected = None
    st.session_state.bt_packets  = []
    st.session_state.ble_live    = {}

def connect_device(dev):
    st.session_state.bt_selected = dev
    st.session_state.bt_phase    = "connected"
    st.session_state.bt_rssi     = dev["rssi"] + random.randint(-3, 3)
    st.session_state.bt_battery  = dev["battery"]
    st.session_state.ble_live    = _gen_live(dev["type"])
    add_packet(0, "TX")

def disconnect():
    st.session_state.bt_phase    = "idle"
    st.session_state.bt_selected = None
    st.session_state.bt_packets  = []
    st.session_state.ble_live    = {}

def refresh_ble():
    if st.session_state.bt_selected:
        live = _gen_live(st.session_state.bt_selected["type"])
        st.session_state.ble_live = live
        st.session_state.bt_rssi  = st.session_state.bt_selected["rssi"] + random.randint(-5, 5)
        add_packet(list(live.values())[0], "RX")

# ─── BT sidebar panel ────────────────────────────────────────────────────────
def bt_sidebar(prefix, tool_type=None):
    is_conn  = st.session_state.bt_phase == "connected"
    phase    = st.session_state.bt_phase
    led_cls  = {"idle":"bt-idle","found":"bt-scan","connected":"bt-conn"}.get(phase,"bt-idle")
    dev_name = st.session_state.bt_selected["name"] if st.session_state.bt_selected else ""
    phase_txt = {
        "idle":      "BLUETOOTH OFF",
        "found":     "DEVICES FOUND",
        "connected": f"CONNECTED · {dev_name}",
    }.get(phase, "")

    rssi_html = rssi_bars_html(st.session_state.bt_rssi) if is_conn else ""
    batt_html = f'<span style="color:#008833;margin-left:8px">🔋{st.session_state.bt_battery}%</span>' if is_conn else ""
    rssi_str  = f'<span style="color:#cc7700;margin-left:6px">{st.session_state.bt_rssi}dBm</span>' if is_conn else ""

    st.markdown(
        f'<div class="bt-bar"><div class="bt-led {led_cls}"></div>'
        f'<span style="color:{"#007733" if is_conn else "#888"}">{phase_txt}</span>'
        f'{rssi_html}{rssi_str}{batt_html}</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="panel-title">BLUETOOTH CONTROL</div>', unsafe_allow_html=True)

    b1, b2 = st.columns(2)
    with b1:
        if st.button("🔍 SCAN", use_container_width=True, disabled=is_conn, key=f"{prefix}_scan"):
            start_scan(); st.rerun()
    with b2:
        if st.button("✖ DISCONNECT", use_container_width=True, disabled=not is_conn, key=f"{prefix}_disc"):
            disconnect(); st.rerun()

    if st.session_state.bt_phase == "found" and st.session_state.bt_devices:
        st.markdown('<div class="panel-title" style="margin-top:6px">DISCOVERED DEVICES</div>', unsafe_allow_html=True)
        for dev in st.session_state.bt_devices:
            sel      = "selected" if st.session_state.bt_selected == dev else ""
            bars     = rssi_bars_html(dev["rssi"])
            is_match = tool_type and dev["type"] == tool_type
            name_col = "#00ccff" if is_match else "#88aaff"
            tip      = " ◀ MATCH" if is_match else ""
            st.markdown(
                f'<div class="device-card {sel}">'
                f'<span class="dev-name" style="color:{name_col}">{dev["name"]}{tip}</span> '
                f'<span style="color:#6688aa;font-size:0.6rem">{dev["type"]}</span><br>'
                f'<span class="dev-mac">{dev["mac"]}</span> {bars} '
                f'<span style="color:#cc7700;font-size:0.6rem">{dev["rssi"]}dBm</span> '
                f'<span style="color:#008833;font-size:0.6rem">🔋{dev["battery"]}%</span>'
                f'</div>', unsafe_allow_html=True,
            )
            if st.button(f"Connect {dev['name']}", key=f"{prefix}_conn_{dev['mac']}", use_container_width=True):
                connect_device(dev); st.rerun()

    if is_conn:
        if st.button("📡 REFRESH BLE DATA", use_container_width=True, key=f"{prefix}_refresh"):
            refresh_ble(); st.rerun()

        if st.session_state.ble_live:
            st.markdown('<div class="panel-title" style="margin-top:8px">📡 LIVE BLE STREAM</div>', unsafe_allow_html=True)
            for k, v in st.session_state.ble_live.items():
                st.markdown(f'<div class="ble-live-row"><span style="color:#336644">{k.upper()}</span>  {v}</div>', unsafe_allow_html=True)

        st.markdown('<div class="panel-title" style="margin-top:8px">BLE PACKET MONITOR</div>', unsafe_allow_html=True)
        rows_html = "".join(
            f'<div class="pkt-row"><span class="pkt-time">{pk["time"]}</span>'
            f'<span class="pkt-dir">{pk["dir"]}</span>'
            f'<span class="pkt-hex">{pk["hex"]}</span>'
            f'<span class="pkt-dec">{pk["dec"]}</span></div>'
            for pk in st.session_state.bt_packets[:12]
        )
        st.markdown(f'<div class="pkt-wrap">{rows_html or "<span style=color:#b0b8cc>No packets yet</span>"}</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ─── Hook: intercept trigger captures and write to CSV ───────────────────────
def _watch_log(log_key, tool_name, unit, value_key="raw", after_count_key=None):
    """
    Called AFTER each tool renders. Checks if a new entry was just added to
    the tool's session log, and if so, writes it to the shared CSV.
    Uses a secondary key to track how many entries we've already saved.
    """
    log  = st.session_state.get(log_key, [])
    seen_key = f"_csv_seen_{log_key}"
    seen = st.session_state.get(seen_key, 0)

    if len(log) > seen:
        # New entries since last render — save them
        new_entries = log[:len(log) - seen]
        for entry in reversed(new_entries):   # oldest first
            val    = entry.get(value_key)
            passed = entry.get("passed", False)
            if val is not None:
                save_to_csv(tool_name, val, unit, passed)
        st.session_state[seen_key] = len(log)


def _watch_thermo_log():
    """Thermo has two readings per entry (temp + humidity) → handle separately."""
    log      = st.session_state.get("th_log", [])
    seen_key = "_csv_seen_th_log"
    seen     = st.session_state.get(seen_key, 0)

    if len(log) > seen:
        new_entries = log[:len(log) - seen]
        for entry in reversed(new_entries):
            temp_c = entry.get("temp_c")
            hum    = entry.get("hum")
            passed = entry.get("passed", False)
            if temp_c is not None:
                save_to_csv("Tempmeter",            temp_c, "C",   passed)
            if hum is not None:
                save_to_csv("Humidity(Humidimeter)", hum,   "%RH", passed)
        st.session_state[seen_key] = len(log)


# ─── Tabs ─────────────────────────────────────────────────────────────────────
tabs = st.tabs(["⚡ Multimeter", "🔩 Torque Wrench", "🌡 Thermo / Hygro", "🔊 Sound Meter"])

# ── Multimeter ───────────────────────────────────────────────────────────────
with tabs[0]:
    from tools.multimeter import render_multimeter, MODE_UNITS
    col_bt, col_inst = st.columns([1, 2.5])
    with col_bt:
        bt_sidebar("mm", tool_type="Multimeter")
        live = st.session_state.ble_live
        if live and st.session_state.bt_selected and st.session_state.bt_selected["type"] == "Multimeter":
            if "voltage" in live:
                st.session_state.mm_value = live["voltage"]
                st.session_state.mm_mode  = "DC Voltage"
    with col_inst:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="panel-title">DM-800BT DIGITAL MULTIMETER</div>', unsafe_allow_html=True)
        render_multimeter()

        # Map current mode → condition monitor tool name + unit
        _mm_mode = st.session_state.get("mm_mode", "DC Voltage")
        _mm_tool_map = {
            "DC Voltage": ("Digital Multimeter - Voltage",    "V"),
            "AC Voltage": ("Digital Multimeter - Voltage",    "V"),
            "DC Current": ("Digital Multimeter - Current",    "A"),
            "AC Current": ("Digital Multimeter - Current",    "A"),
            "Resistance": ("Digital Multimeter - Resistance", "Ohm"),
        }
        _mm_tool, _mm_unit = _mm_tool_map.get(_mm_mode, ("Digital Multimeter - Voltage", "V"))
        _watch_log("mm_log", _mm_tool, _mm_unit, value_key="raw")

        # Show confirmation banner if just saved
        _mm_log = st.session_state.get("mm_log", [])
        if _mm_log:
            _e = _mm_log[0]
            _cls = "saved-banner" if _e["passed"] else "saved-banner fail"
            st.markdown(f'<div class="{_cls}">{"✔ SAVED TO DASHBOARD" if _e["passed"] else "✖ SAVED (OUT OF RANGE)"} — {_e["value"]}</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

# ── Torque Wrench ─────────────────────────────────────────────────────────────
with tabs[1]:
    from tools.torque_wrench import render_torque_wrench
    col_bt, col_inst = st.columns([1, 2.5])
    with col_bt:
        bt_sidebar("tw", tool_type="Torque Wrench")
        live = st.session_state.ble_live
        if live and st.session_state.bt_selected and st.session_state.bt_selected["type"] == "Torque Wrench":
            if "torque" in live:
                st.session_state.tw_torque = live["torque"]
    with col_inst:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="panel-title">TW-500BT DIGITAL TORQUE WRENCH</div>', unsafe_allow_html=True)
        render_torque_wrench()
        _watch_log("tw_log", "Digital Torque Wrench", "Nm", value_key="raw")

        _tw_log = st.session_state.get("tw_log", [])
        if _tw_log:
            _e = _tw_log[0]
            _cls = "saved-banner" if _e["passed"] else "saved-banner fail"
            st.markdown(f'<div class="{_cls}">{"✔ SAVED TO DASHBOARD" if _e["passed"] else "✖ SAVED (OUT OF RANGE)"} — {_e["value"]}</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

# ── Thermo / Hygro ────────────────────────────────────────────────────────────
with tabs[2]:
    from tools.thermo_hygro import render_thermo
    col_bt, col_inst = st.columns([1, 2.5])
    with col_bt:
        bt_sidebar("th", tool_type="Thermo/Hygro")
        live = st.session_state.ble_live
        if live and st.session_state.bt_selected and st.session_state.bt_selected["type"] == "Thermo/Hygro":
            if "temp"     in live: st.session_state.th_temp = live["temp"]
            if "humidity" in live: st.session_state.th_hum  = live["humidity"]
    with col_inst:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="panel-title">TH-200BT DIGITAL TEMPERATURE / HUMIDITY METER</div>', unsafe_allow_html=True)
        render_thermo()
        _watch_thermo_log()

        _th_log = st.session_state.get("th_log", [])
        if _th_log:
            _e = _th_log[0]
            _cls = "saved-banner" if _e["passed"] else "saved-banner fail"
            st.markdown(f'<div class="{_cls}">{"✔ SAVED TO DASHBOARD" if _e["passed"] else "✖ SAVED (OUT OF RANGE)"} — {_e["value"]}</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

# ── Sound Meter ───────────────────────────────────────────────────────────────
with tabs[3]:
    from tools.sound_meter import render_sound_meter
    col_bt, col_inst = st.columns([1, 2.5])
    with col_bt:
        bt_sidebar("sm", tool_type="Sound Meter")
        live = st.session_state.ble_live
        if live and st.session_state.bt_selected and st.session_state.bt_selected["type"] == "Sound Meter":
            if "db" in live: st.session_state.sm_db = live["db"]
    with col_inst:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="panel-title">SL-400BT DIGITAL SOUND LEVEL METER</div>', unsafe_allow_html=True)
        render_sound_meter()
        _watch_log("sm_log", "Digital Sound Meter", "dB", value_key="raw")

        _sm_log = st.session_state.get("sm_log", [])
        if _sm_log:
            _e = _sm_log[0]
            _cls = "saved-banner" if _e["passed"] else "saved-banner fail"
            st.markdown(f'<div class="{_cls}">{"✔ SAVED TO DASHBOARD" if _e["passed"] else "✖ SAVED (OUT OF RANGE)"} — {_e["value"]}</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
