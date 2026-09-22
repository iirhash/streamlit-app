# main.py
# ── Entry point ────────────────────────────────────────────────
# Run with: streamlit run main.py

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

# ── Auto refresh every 30 seconds without losing session ──────
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

# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Condition Monitoring")
    st.markdown("---")

    role = get_role() if is_logged_in() else None

    # Build nav based on role
    nav_options = [
        "🔍 Defect Viewer",
        "👟 Collector Shoe",
        "📱 Mobile Capture Station",
        "📡 DJI Wireless Station (Mobile)",
    ]

    # ── Remember current page across reruns ───────────────────
    # Default to Defect Viewer on first load
    current_page = st.session_state.get("current_page", "🔍 Defect Viewer")
    if current_page not in nav_options:
        current_page = "🔍 Defect Viewer"
        st.session_state["current_page"] = current_page
    current_idx = nav_options.index(current_page)

    page = st.radio(
        "Navigation",
        nav_options,
        index=current_idx,
        label_visibility="collapsed",
    )
    # Persist the selection immediately
    st.session_state["current_page"] = page

    st.markdown("---")
    st.markdown(f"🟢 **Live** — {datetime.now().strftime('%d %b %Y, %H:%M')}")
    st.markdown("*Auto-refreshes every 5 mins*")

    # ── Bottom of sidebar ──────────────────────────────────────
    st.markdown("---")

    if is_logged_in():
        # Show logged-in user info
        show_user_info()
    else:
        # Technician access indicator
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

        # ── Staff login expander ───────────────────────────────
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


# ── Load the right page ────────────────────────────────────────
if page == "📡 Measurement Input":
    from app import input_form
    input_form.show()

elif page == "📱 Mobile Capture Station":
    from app import mobile_capture_station
    mobile_capture_station.show()

elif page == "📡 DJI Wireless Station (Mobile)":
    from app import wireless_station
    wireless_station.show()

elif page == "📊 Dashboard":
    from app import dashboard
    dashboard.show()

elif page == "🗂 History":
    from app import history
    history.show()

elif page == "🔍 Defect Viewer":
    from app import defect_viewer
    defect_viewer.show()

elif page == "⚙️ Threshold Settings":
    st.markdown("## ⚙️ Threshold Settings")
    st.info("Management threshold editor coming soon.")

elif page == "👟 Collector Shoe":
    from app import collector_shoe
    collector_shoe.show()
