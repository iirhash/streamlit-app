# app/landing.py
# ── Landing / Gate Page ────────────────────────────────────────
# First thing shown when the app loads.
# User must choose: Staff Login OR Public Access (technician)

import streamlit as st
import os, sys


from app.login import login


def show():
    """
    Renders the landing page briefly then auto-redirects to
    public (technician) access. Staff can log in via the
    sidebar expander once inside the app.
    """

    # ── Auto-grant public access immediately ───────────────────
    # Technicians go straight in — no click needed.
    # The landing page shows for a brief moment as a branded
    # splash screen, then redirects automatically.
    if not st.session_state.get("landing_shown", False):
        st.session_state["landing_shown"]  = True
        st.session_state["access_granted"] = True
        st.session_state["access_mode"]    = "public"
        st.rerun()

    # ── Styling ────────────────────────────────────────────────
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&display=swap');

    /* Hide default streamlit chrome on landing page */
    #MainMenu, footer, header { visibility: hidden; }

    /* Fix centering — let Streamlit handle the container normally */
    .block-container {
        max-width: 680px !important;
        padding-top: 6vh !important;
        padding-bottom: 2rem !important;
    }

    :root {
        --dark:    #0D1117;
        --panel:   #161B22;
        --border:  #30363D;
        --green:   #0A8A72;
        --green2:  #0ECF9F;
        --text:    #E6EDF3;
        --muted:   #7D8590;
        --danger:  #C9382A;
    }

    body, .stApp {
        background-color: var(--dark) !important;
        font-family: 'DM Sans', sans-serif;
        background-image:
            radial-gradient(ellipse 80% 60% at 50% -10%, rgba(10,138,114,0.18) 0%, transparent 70%),
            repeating-linear-gradient(
                0deg,
                transparent,
                transparent 39px,
                rgba(48,54,61,0.3) 39px,
                rgba(48,54,61,0.3) 40px
            ),
            repeating-linear-gradient(
                90deg,
                transparent,
                transparent 39px,
                rgba(48,54,61,0.3) 39px,
                rgba(48,54,61,0.3) 40px
            );
    }

    .landing-card {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 52px 48px 44px;
        max-width: 480px;
        width: 100%;
        box-shadow:
            0 0 0 1px rgba(10,138,114,0.08),
            0 32px 64px rgba(0,0,0,0.5),
            0 0 80px rgba(10,138,114,0.06);
        animation: fadeUp 0.5s ease both;
    }

    @keyframes fadeUp {
        from { opacity: 0; transform: translateY(24px); }
        to   { opacity: 1; transform: translateY(0);    }
    }

    .landing-badge {
        display: inline-block;
        background: rgba(10,138,114,0.15);
        border: 1px solid rgba(10,138,114,0.35);
        color: var(--green2);
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 2px;
        text-transform: uppercase;
        padding: 4px 12px;
        border-radius: 20px;
        margin-bottom: 18px;
    }

    .landing-title {
        font-family: 'Bebas Neue', sans-serif;
        font-size: 42px;
        letter-spacing: 2px;
        color: var(--text);
        line-height: 1.05;
        margin: 0 0 6px 0;
    }

    .landing-title span {
        color: var(--green2);
    }

    .landing-sub {
        color: var(--muted);
        font-size: 14px;
        margin-bottom: 36px;
        line-height: 1.6;
    }

    .divider-or {
        display: flex;
        align-items: center;
        gap: 12px;
        margin: 24px 0;
        color: var(--muted);
        font-size: 12px;
        letter-spacing: 1px;
    }

    .divider-or::before,
    .divider-or::after {
        content: '';
        flex: 1;
        height: 1px;
        background: var(--border);
    }

    /* Input fields */
    .stTextInput input {
        background: #0D1117 !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
        color: var(--text) !important;
        font-family: 'DM Sans', sans-serif !important;
        font-size: 14px !important;
        padding: 10px 14px !important;
        transition: border-color 0.2s;
    }
    .stTextInput input:focus {
        border-color: var(--green) !important;
        box-shadow: 0 0 0 3px rgba(10,138,114,0.15) !important;
    }
    .stTextInput label {
        color: var(--muted) !important;
        font-size: 12px !important;
        font-weight: 500 !important;
        letter-spacing: 0.5px !important;
    }

    /* Primary login button */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, var(--green), #087a63) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        padding: 12px !important;
        width: 100% !important;
        transition: all 0.2s !important;
        letter-spacing: 0.3px;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #0ba88c, var(--green)) !important;
        transform: translateY(-1px);
        box-shadow: 0 8px 24px rgba(10,138,114,0.35) !important;
    }

    /* Secondary public access button */
    .stButton > button[kind="secondary"] {
        background: transparent !important;
        color: var(--muted) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 500 !important;
        font-size: 14px !important;
        padding: 12px !important;
        width: 100% !important;
        transition: all 0.2s !important;
    }
    .stButton > button[kind="secondary"]:hover {
        border-color: var(--muted) !important;
        color: var(--text) !important;
        background: rgba(255,255,255,0.04) !important;
    }

    .landing-footer {
        text-align: center;
        color: var(--muted);
        font-size: 11px;
        margin-top: 28px;
        line-height: 1.8;
    }

    /* Error / success messages */
    .stAlert {
        border-radius: 8px !important;
        font-size: 13px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Layout ─────────────────────────────────────────────────
    # Center column
    _, col, _ = st.columns([0.5, 3, 0.5])

    with col:
        st.markdown("""
        <div class="landing-card">
            <div class="landing-badge">🚆 LRT Maintenance System</div>
            <div class="landing-title">CONDITION<br><span>MONITORING</span></div>
            <div class="landing-sub">
                Wireless tool readings · AI defect detection · Real-time dashboard
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Staff login form ───────────────────────────────────
        st.markdown("##### 🔐 Staff Login")
        sap = st.text_input("SAP Number", placeholder="e.g. S12345", label_visibility="visible")
        pw  = st.text_input("Password",   type="password", placeholder="Enter your password")

        login_btn = st.button("Login as Staff", type="primary", width="stretch")

        if login_btn:
            if not sap or not pw:
                st.error("Please enter your SAP number and password.")
            else:
                with st.spinner("Verifying credentials..."):
                    success, message = login(sap.strip(), pw)
                if success:
                    st.success(message)
                    st.session_state["access_granted"] = True
                    st.session_state["access_mode"]    = "staff"
                    st.rerun()
                else:
                    st.error(message)

        # ── Divider ────────────────────────────────────────────
        st.markdown('<div class="divider-or">OR</div>', unsafe_allow_html=True)

        # ── Public access ──────────────────────────────────────
        public_btn = st.button(
            "👷 Continue as Technician  —  Public Access",
            type="secondary",
            width="stretch",
        )

        if public_btn:
            st.session_state["access_granted"] = True
            st.session_state["access_mode"]    = "public"
            st.rerun()

        # ── Footer ─────────────────────────────────────────────
        st.markdown("""
        <div class="landing-footer">
            Technician access is read-only.<br>
            Staff login required to submit or edit readings.<br><br>
            © LRT Condition Monitoring System
        </div>
        """, unsafe_allow_html=True)


