# main.py
# ── LRT Condition Monitoring System ───────────────────────────
# Run:  streamlit run main.py
# ──────────────────────────────────────────────────────────────

import streamlit as st
from datetime import datetime

st.set_page_config(
    page_title="LRT Condition Monitoring",
    page_icon="⚙️",
    layout="wide",
)

# Auto-refresh every 2 minutes
st.markdown('<meta http-equiv="refresh" content="120">', unsafe_allow_html=True)

# ── Bootstrap session state ───────────────────────────────────
if "access_granted" not in st.session_state:
    st.session_state["access_granted"] = False
if "access_mode" not in st.session_state:
    st.session_state["access_mode"] = "public"

# ── Landing / auth gate ───────────────────────────────────────
if not st.session_state["access_granted"]:
    from app.landing import show as show_landing
    show_landing()
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ LRT Condition Monitoring")
    st.markdown("---")

    # Navigation
    is_staff = st.session_state.get("logged_in", False)

    nav_options = [
        "📡 Measurement Input",
        "📊 Dashboard",
        "🗂 History",
        "🔍 Defect Viewer",
    ]

    page = st.radio(
        "Navigation",
        nav_options,
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown(f"🟢 **Live** — {datetime.now().strftime('%d %b %Y, %H:%M')}")
    st.markdown("*Auto-refreshes every 120s*")

    # ── Login / logout ────────────────────────────────────────
    from app.login import is_logged_in, show_login_form, show_user_info
    if is_logged_in():
        show_user_info()
    else:
        show_login_form()

# ── Page routing ──────────────────────────────────────────────
if page == "📡 Measurement Input":
    from app.input_form import show
    show()

elif page == "📊 Dashboard":
    from app.dashboard import show
    show()

elif page == "🗂 History":
    from app.history import show
    show()

elif page == "🔍 Defect Viewer":
    from app.defect_viewer import show
    show()
