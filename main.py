# main.py
# ── Entry point ────────────────────────────────────────────────
# Run with: streamlit run main.py

import os
import streamlit as st
import time
from datetime import datetime

# ── MUST BE FIRST ─────────────────────────────────────────────
st.set_page_config(
    page_title="Condition Monitoring System",
    page_icon="⚙️",
    layout="wide",
)

# ── Import login helpers ───────────────────────────────────────
from app.login import is_logged_in, get_role, show_user_info, login, logout

# ── GATE: Show landing page briefly then auto-redirect ────────
if not st.session_state.get("access_granted", False):
    from app.landing import show as show_landing
    show_landing()
    st.stop()

# ── Auto refresh every 5 minutes without losing session ───────
if "last_refresh" not in st.session_state:
    st.session_state["last_refresh"] = time.time()

# Check if any edit/delete/register actions are in progress
_user_is_busy = any(
    k.startswith("edit_shoe_") or
    k.startswith("del_shoe_") or
    k == "reg_cab_end"          # registration form is open
    for k in st.session_state
)

if not _user_is_busy and time.time() - st.session_state["last_refresh"] > 300:
    st.session_state["last_refresh"] = time.time()
    st.rerun()

# ── Field Manual gate (resets every browser session) ──────────
_manual_confirmed = st.session_state.get("field_manual_confirmed", False)

# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Condition Monitoring")
    st.markdown("---")

    role = get_role() if is_logged_in() else None

    # Full nav list — Field Manual is always first
    _all_nav = [
        "📖 Visual Inspection Manual",
        "🔍 Defect Viewer",
        "👟 Shoe Health Monitor",
        "🚀 Launch Camera Stations",
    ]

    if _manual_confirmed:
        nav_options = _all_nav
    else:
        nav_options = _all_nav

    # Force to Field Manual if not yet confirmed
    if not _manual_confirmed:
        current_page = "📖 Visual Inspection Manual"
        st.session_state["current_page"] = current_page
    elif st.session_state.get("camera_station_sub"):
        # Inside a camera station sub-page — lock nav to Launch Camera Stations
        current_page = "🚀 Launch Camera Stations"
        st.session_state["current_page"] = current_page
    else:
        current_page = st.session_state.get("current_page", "🔍 Defect Viewer")
        if current_page not in nav_options:
            current_page = "🔍 Defect Viewer"
            st.session_state["current_page"] = current_page

    current_idx = nav_options.index(current_page)

    def _nav_label(opt):
        """Grey out locked tabs with a lock icon."""
        if not _manual_confirmed and opt != "📖 Visual Inspection Manual":
            return f"🔒 {opt}"
        return opt

    page = st.radio(
        "Navigation",
        nav_options,
        index=current_idx,
        format_func=_nav_label,
        label_visibility="collapsed",
    )
    # Only persist the radio selection when not inside a camera station sub-page
    if not st.session_state.get("camera_station_sub"):
        st.session_state["current_page"] = page

    st.markdown("---")
    st.markdown(f"🟢 **Live** — {datetime.now().strftime('%d %b %Y, %H:%M')}")
    st.markdown("*Auto-refreshes every 5 mins*")

    # ── Bottom of sidebar ──────────────────────────────────────
    st.markdown("---")

    if is_logged_in():
        show_user_info()
    else:
        st.markdown(
            """
            <div style="
                background:#161B22;border:1px solid #30363D;
                border-radius:8px;padding:10px 12px;margin-bottom:10px;
            ">
                <div style="font-size:11px;color:#7D8590;font-weight:600;
                            text-transform:uppercase;letter-spacing:1px;">
                    Public Access
                </div>
                <div style="font-size:13px;color:#E6EDF3;margin-top:2px;">
                    👷 Technician View
                </div>
                <div style="font-size:11px;color:#7D8590;">Read-only</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander("🔐 Staff Login"):
            with st.form("sidebar_login_form", clear_on_submit=True):
                sap = st.text_input("SAP Number", placeholder="e.g. S12345")
                pw  = st.text_input("Password",   type="password")
                submit = st.form_submit_button(
                    "Login", type="primary", width="stretch"
                )
                if submit:
                    if not sap or not pw:
                        st.error("Enter SAP number and password.")
                    else:
                        with st.spinner("Verifying..."):
                            success, message = login(sap.strip(), pw)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)


# ── Helper: block locked pages ────────────────────────────────
def _require_manual():
    if not _manual_confirmed:
        st.warning("📖 Please read the Field Manual first.")
        st.stop()


# ── Load the right page ────────────────────────────────────────

if page == "📖 Visual Inspection Manual":
    st.markdown("# 📖 Visual Inspection Field Manual")
    st.markdown("*Read this before using the system. Your confirmation unlocks all other tabs.*")
    st.markdown("---")

    # ── Section 1: Pre-Inspection Checks ──────────────────────
    st.markdown("## ✅ 1. Pre-Inspection Checks")
    st.markdown("""
Before capturing any images, ensure the following:

| Check | Requirement |
|-------|-------------|
| 🔦 Lighting | Adequate and uniform — avoid direct glare or heavy shadows on the shoe surface |
| 📷 Camera | DJI Action 3 powered on, SD card inserted, lens clean |
| 🚆 LRV | Stationary and secured before going trackside |
| 🦺 PPE | High-visibility vest, safety boots, and gloves worn |
| 📋 Shoe ID | Confirm collector shoe position label (e.g. CS-LRV00-+A1) matches the physical shoe |
    """)

    st.markdown("---")

    # ── Section 2: Collector Shoe Positions ───────────────────
    st.markdown("## 🚃 2. Collector Shoe Positions")
    st.markdown("""
Each LRV has **8 collector shoes** across 2 bogies (A End and B End), labelled using the convention `CS-LRV[XX]-[+/-][A/B][position]`:

- **`+`** = Upper shoe &nbsp;|&nbsp; **`-`** = Lower shoe
- **`A`** = A End bogie (left) &nbsp;|&nbsp; **`B`** = B End bogie (right)
- **Position 1 & 2** = A End &nbsp;|&nbsp; **Position 3 & 4** = B End

| Label | Bogie | Position | Shoe |
|-------|-------|----------|------|
| **CS-LRV00-+A1** | A End | Position 1 | Upper (+) |
| **CS-LRV00--A1** | A End | Position 1 | Lower (−) |
| **CS-LRV00-+A2** | A End | Position 2 | Upper (+) |
| **CS-LRV00--A2** | A End | Position 2 | Lower (−) |
| **CS-LRV00-+B3** | B End | Position 3 | Upper (+) |
| **CS-LRV00--B3** | B End | Position 3 | Lower (−) |
| **CS-LRV00-+B4** | B End | Position 4 | Upper (+) |
| **CS-LRV00--B4** | B End | Position 4 | Lower (−) |

> 📌 **Always confirm the shoe label before capturing.** Mislabelling will corrupt the maintenance history.
    """)

    st.markdown("---")

    # ── Section 3: 3-Angle Capture Procedure ──────────────────
    st.markdown("## 📷 3. Three-Angle Capture Procedure")
    st.markdown("""
Each shoe must be photographed from **3 angles** per inspection session.
This ensures full surface coverage for the YOLO defect model.

| Shot | Angle | Purpose |
|------|-------|---------|
| **Shot 1** | Left 15° | Capture left edge wear and side cracks |
| **Shot 2** | Centre 0° | Main surface — wear, scuff marks, corrosion |
| **Shot 3** | Right 15° | Capture right edge wear and symmetry check |
    """)

    _c1, _c2, _c3 = st.columns(3)
    with _c1:
        st.image("app/assets/left_15.jpg", caption="Shot 1 — Left 15°", width="stretch")
    with _c2:
        st.image("app/assets/centre_0.jpg", caption="Shot 2 — Centre 0°", width="stretch")
    with _c3:
        st.image("app/assets/right_15.jpg", caption="Shot 3 — Right 15°", width="stretch")

    st.markdown("""
**How to capture:**
1. Go to **🚀 Launch Camera Stations** and choose a workstation station (Wired / Wireless) or a mobile station (Mobile Capture / DJI Wireless Mobile)
2. Select the shoe ID from the dropdown
3. Take Shot 1 (Left 15°), Shot 2 (Centre 0°), Shot 3 (Right 15°) in order
4. Review the YOLO detection overlay before submitting
    """)

    st.markdown("---")

    # ── Section 4: Using the Camera Stations ──────────────────
    st.markdown("## 📡 4. Camera Stations")
    st.markdown("""
**4 capture methods are available.** Choose based on your setup at the depot.
    """)

    st.markdown("### 🔌 Method 1 — Wired Station (DJI Action 3 via USB)")
    _img1_col, _img1b_col = st.columns(2)
    _img1_col.image("app/assets/method1_wired.png", caption="DJI Action 3 connected to laptop via USB-C", width="stretch")
    _img1b_col.image("app/assets/method1_wired_popup.png", caption="Capture Tips popup — shown before the station launches", width="stretch")
    st.markdown("""
**When to use:** LRV is stationary in the depot, laptop is nearby, cable can reach the camera.

**Steps:**
1. Connect the DJI Action 3 to the laptop using the USB-C cable
2. Power on the DJI Action 3
3. On the dashboard, go to **🚀 Launch Camera Stations** → **🖥️ Launch from Workstation**
4. Click **🚀 Wired Capture** — a camera setup window will open on the desktop
5. Select the shoe ID in the popup window
6. Follow the on-screen prompts to capture Left 15°, Centre 0°, Right 15° shots
7. The station will auto-submit each photo to the YOLO detection pipeline
    """)

    st.markdown("### 📡 Method 2 — Wireless Station (DJI Action 3 via Wi-Fi / RTMP)")
    _img2_col, _ = st.columns([0.6, 0.4])
    _img2_col.image("app/assets/method2_wireless.png", caption="DJI Wireless Station popup — enter RTMP URL and click Connect", width="stretch")
    st.markdown("**DJI Mimo App Setup:**")
    _m2a, _m2b, _m2gap = st.columns([0.25, 0.25, 0.5])
    _m2a.image("app/assets/method2_mimo_platform.png", caption="Step 1 — Select RTMP as livestream platform", width="stretch")
    _m2b.image("app/assets/method2_mimo_settings.png", caption="Step 2 — Enter RTMP URL, set 1080p UHD, Auto quality", width="stretch")
    _m2c, _ = st.columns([0.35, 0.65])
    _m2c.image("app/assets/method2_mimo_streaming.png", caption="Step 3 — DJI Action 3 preparing to livestream", width="stretch")
    st.markdown("""
**When to use:** LRV is at a distance, cable cannot reach, or you prefer a wireless setup.

**Steps:**
1. Power on the DJI Action 3 and connect it to the depot Wi-Fi network
2. Confirm your laptop is on the **same Wi-Fi network** as the DJI camera
3. On the dashboard, go to **🚀 Launch Camera Stations** → **🖥️ Launch from Workstation**
4. Click **🚀 Wireless Capture** — a live stream window will open on the desktop
5. Enter the RTMP stream URL shown in DJI Mimo into the station window (e.g. `rtmp://10.x.x.x:1936/live/stream`)
6. Capture frames using the on-screen capture button for each angle (Left 15°, Centre 0°, Right 15°)
7. The station will submit captured frames to the YOLO detection pipeline

> ⚠️ **Before starting:** Ensure `rtmp_server.js` is running on the workstation (`node rtmp_server.js`). If no live feed appears, check that the DJI camera and laptop are on the same network and the RTMP address is correct.
    """)

    st.markdown("### 📱 Method 3 — Mobile Capture Station (Phone Camera)")
    _m3_img, _m3_txt = st.columns([0.25, 0.75])
    _m3_img.image("app/assets/method3_mobile.png", caption="Mobile Capture Station — open in your phone browser", width="stretch")
    with _m3_txt:
        st.markdown("""
**When to use:** Quick spot checks or on-the-go capture without the DJI camera.

**Steps:**
1. Open the dashboard on your mobile browser
2. Go to **🚀 Launch Camera Stations** → **📱 Launch from Mobile Device** → **📱 Mobile Device Capture**
3. Select the shoe ID from the dropdown
4. Use your phone camera to capture Left 15°, Centre 0°, Right 15° shots
5. Submit each photo — the system will run YOLO detection automatically
        """)

    st.markdown("### 📡 Method 4 — DJI Wireless Station (Mobile Browser)")
    _m4_img, _m4_txt = st.columns([0.25, 0.75])
    _m4_img.image("app/assets/method4_wireless_mobile.png", caption="DJI Wireless Station (Mobile) — connect to stream from your phone browser", width="stretch")
    with _m4_txt:
        st.markdown("""
**When to use:** You want to monitor or capture wirelessly from your phone while the DJI streams over Wi-Fi.

**Steps:**
1. Power on the DJI Action 3 and connect it to the depot Wi-Fi network
2. Open your phone browser and navigate to **`http://10.243.253.63:8501`** (depot local network — do NOT use the streamlit.app URL)
3. Go to **🚀 Launch Camera Stations** → **📱 Launch from Mobile Device** → **📡 DJI Wireless Mobile Remote Capture**
4. Enter the RTMP stream URL and click **Connect to Stream**
5. Capture frames for each angle (Left 15°, Centre 0°, Right 15°) and submit

> ⚠️ **Before starting:** Ensure `rtmp_server.js` is running on the workstation (`node rtmp_server.js`). Ensure the DJI camera and your mobile device are on the same Wi-Fi network before opening this tab.

> 📷 **DJI Mimo setup:** Refer to **Method 2** above for step-by-step screenshots on configuring the DJI Mimo app (select RTMP platform, enter stream URL, set 1080p UHD).
        """)

    st.markdown("---")

    # ── Section 5: Understanding YOLO Results ─────────────────
    st.markdown("## 🔍 5. Understanding YOLO Detection Results")
    st.markdown("""
After an image is submitted, the system runs an AI defect scan (Roboflow YOLOv11).

**Result indicators:**

| Icon | Meaning |
|------|---------|
| 🔍 ✅ **Auto-confirmed** | High confidence detection (≥85%, or ≥50% for scuff marks) — logged automatically |
| 🔍 ⚠️ **Needs Review** | Confidence below 85% (wear, crack, corrosion) — requires IC sign-off |
| ✅ **No Defect** | Model found no defects above threshold |

**Defect classes the model detects:**

`wear` · `crack` · `scuff marks` · `corrosion` · `none`

> 📌 **Scuff marks** use a lower threshold (50%) due to their subtle appearance. They are expected from normal rail contact, so they are recorded for trend tracking but **do not** enter the Needs Review queue.

**What to do after detection:**
- Auto-confirmed results are logged to the database immediately
- "Needs Review" items appear in the **🔍 Defect Viewer** with a blinking ⚠️ button
- The IC (In-charge) must mark each reviewed item before it is finalised
    """)

    st.markdown("---")

    # ── Section 6: When to Escalate ───────────────────────────
    st.markdown("## ⚠️ 6. When to Escalate")
    st.markdown("""
Visual inspection does not replace physical measurement. Escalate to the IC if you observe:

- **Visible cracking** running across the width of the shoe
- **Deep scoring** or material loss visible to the naked eye
- **Severe corrosion** covering more than 30% of the contact surface
- Any defect that the YOLO model flags repeatedly across 3+ sessions

> 🔴 **Do not operate the LRV if you suspect a shoe is at or near replacement threshold.** Contact the IC immediately.
    """)

    st.markdown("---")

    # ── Confirmation checkbox at the bottom ───────────────────
    st.markdown("### 📋 Confirmation")
    confirmed = st.checkbox(
        "I have read and understood this field manual — the capture steps, "
        "the camera angles, and the defect classification results.",
        value=False,
        key="fm_checkbox",
    )

    if confirmed:
        st.session_state["field_manual_confirmed"] = True
        st.success("✅ Field Manual confirmed. All tabs are now unlocked.")
        st.balloons()
        time.sleep(1)
        st.session_state["current_page"] = "🔍 Defect Viewer"
        st.rerun()
    else:
        st.info("☝️ Tick the box above to unlock the rest of the dashboard.")

elif page == "🚀 Launch Camera Stations":
    _require_manual()
    import subprocess
    import sys

    # ── Sub-page routing for mobile stations ──────────────────
    _mobile_sub = st.session_state.get("camera_station_sub", None)

    if _mobile_sub == "mobile":
        from app import mobile_capture_station
        if st.button("← Back to Launch Camera Stations"):
            st.session_state["camera_station_sub"] = None
            st.session_state["current_page"] = "🚀 Launch Camera Stations"
            st.rerun()
        mobile_capture_station.show()
        st.stop()

    elif _mobile_sub == "dji_wireless_mobile":
        from app import wireless_station
        if st.button("← Back to Launch Camera Stations"):
            st.session_state["camera_station_sub"] = None
            st.session_state["current_page"] = "🚀 Launch Camera Stations"
            st.rerun()
        wireless_station.show()
        st.stop()

    # ── Main Launch Camera Stations page ──────────────────────
    st.markdown("# 🚀 Launch Camera Stations")
    st.markdown("Select how you want to capture — from a workstation or from a mobile device.")

    if st.button("🔄 Refresh Page", use_container_width=False):
        st.rerun()

    st.markdown("---")

    launch_tab1, launch_tab2 = st.tabs(["🖥️ Launch from Workstation", "📱 Launch from Mobile Device"])

    # ── Launch from Workstation ────────────────────────────────
    with launch_tab1:
        st.markdown("### Launch a camera station on this workstation")
        st.caption("The station opens as a desktop window on the computer running Streamlit.")

        ws_col1, ws_col2 = st.columns(2)

        with ws_col1:
            st.markdown(
                """<div style="background:#0A8A72;border-radius:12px;
                padding:20px;text-align:center;margin-bottom:12px;">
                <div style="font-size:36px;">📷</div>
                <div style="color:white;font-size:16px;font-weight:700;margin-top:8px;">
                DJI Camera Station</div>
                <div style="color:#DCFCE7;font-size:12px;margin-top:4px;">
                Wired USB capture</div>
                </div>""",
                unsafe_allow_html=True
            )
            if st.button(
                "🚀 Wired Capture",
                type="primary",
                use_container_width=True,
                key="launch_wired_ws"
            ):
                try:
                    subprocess.Popen(
                        [sys.executable, "dji_camera_station.py"],
                        cwd=os.path.dirname(os.path.abspath(__file__))
                    )
                    st.info(
                        "📷 Wired camera station is starting. "
                        "A setup window will appear on your desktop shortly. "
                        "If nothing appears, check that the DJI camera is plugged in and switched on."
                    )
                except Exception as e:
                    st.error(f"❌ Could not launch wired camera station: {e}")

        with ws_col2:
            st.markdown(
                """<div style="background:#1A6FB5;border-radius:12px;
                padding:20px;text-align:center;margin-bottom:12px;">
                <div style="font-size:36px;">📡</div>
                <div style="color:white;font-size:16px;font-weight:700;margin-top:8px;">
                DJI Wireless Station</div>
                <div style="color:#DBEAFE;font-size:12px;margin-top:4px;">
                RTMP wireless capture</div>
                </div>""",
                unsafe_allow_html=True
            )
            if st.button(
                "🚀 Wireless Capture",
                type="primary",
                use_container_width=True,
                key="launch_wireless_ws"
            ):
                try:
                    subprocess.Popen(
                        [sys.executable, "dji_wireless_station.py"],
                        cwd=os.path.dirname(os.path.abspath(__file__))
                    )
                    st.info(
                        "📡 Wireless camera station is starting. "
                        "Make sure rtmp_server.js is running and DJI Mimo is streaming "
                        "before clicking Connect in the setup window."
                    )
                except Exception as e:
                    st.error(f"❌ Could not launch wireless camera station: {e}")

    # ── Launch from Mobile Device ──────────────────────────────
    with launch_tab2:
        st.markdown("### Launch a capture station in your mobile browser")
        st.caption("Open the relevant tab on your phone browser to begin capture.")

        mob_col1, mob_col2 = st.columns(2)

        with mob_col1:
            st.markdown(
                """<div style="background:#7C3AED;border-radius:12px;
                padding:20px;text-align:center;margin-bottom:12px;">
                <div style="font-size:36px;">📱</div>
                <div style="color:white;font-size:16px;font-weight:700;margin-top:8px;">
                Mobile Capture Station</div>
                <div style="color:#EDE9FE;font-size:12px;margin-top:4px;">
                Phone camera capture</div>
                </div>""",
                unsafe_allow_html=True
            )
            st.markdown(
                "Open the **📱 Mobile Capture Station** directly in your phone browser "
                "using the Streamlit Community Cloud link."
            )
            if st.button(
                "📱 Mobile Device Capture",
                type="primary",
                use_container_width=True,
                key="launch_mobile_btn"
            ):
                st.session_state["camera_station_sub"] = "mobile"
                st.session_state["current_page"] = "🚀 Launch Camera Stations"
                st.rerun()

        with mob_col2:
            st.markdown(
                """<div style="background:#B45309;border-radius:12px;
                padding:20px;text-align:center;margin-bottom:12px;">
                <div style="font-size:36px;">📡</div>
                <div style="color:white;font-size:16px;font-weight:700;margin-top:8px;">
                DJI Wireless (Mobile)</div>
                <div style="color:#FEF3C7;font-size:12px;margin-top:4px;">
                RTMP stream via local IP</div>
                </div>""",
                unsafe_allow_html=True
            )
            st.markdown(
                "⚠️ **Use laptop's local IP address** (e.g. `http://10.243.253.63:8501`) — "
                "do NOT use the Streamlit Community Cloud link. "
                "The RTMP server must be running on the workstation."
            )
            if st.button(
                "📡 DJI Wireless Mobile Remote Capture",
                type="primary",
                use_container_width=True,
                key="launch_dji_mobile_btn"
            ):
                st.session_state["camera_station_sub"] = "dji_wireless_mobile"
                st.session_state["current_page"] = "🚀 Launch Camera Stations"
                st.rerun()

elif page == "🔍 Defect Viewer":
    _require_manual()
    from app import defect_viewer
    defect_viewer.show()

elif page == "👟 Shoe Health Monitor":
    _require_manual()
    from app import collector_shoe
    collector_shoe.show()

elif page == "📡 Measurement Input":
    _require_manual()
    from app import input_form
    input_form.show()

elif page == "📊 Dashboard":
    _require_manual()
    from app import dashboard
    dashboard.show()

elif page == "🗂 History":
    _require_manual()
    from app import history
    history.show()

elif page == "⚙️ Threshold Settings":
    _require_manual()
    st.markdown("## ⚙️ Threshold Settings")
    st.info("Management threshold editor coming soon.")
