# app/login.py
# ── SAP Login Page ─────────────────────────────────────────────
# Handles login/logout for supervisor, IC, and management roles
# Technicians do NOT need to log in — public read-only access

import streamlit as st
from supabase import create_client


def get_supabase():
    """
    Returns a Supabase client instance.
    If the user is logged in, returns the AUTHENTICATED client
    (stored in session state) so RLS policies recognise their role.
    Otherwise returns a fresh anonymous client.
    """
    if "supabase_client" in st.session_state:
        return st.session_state["supabase_client"]

    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


def login(sap_number: str, password: str):
    """
    Logs in a user using their SAP number + password.
    Converts SAP number to internal email format behind the scenes.
    Returns (success: bool, message: str)
    """
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)
    email = f"{sap_number}@lrt-internal.com"

    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })

        # Fetch role from profiles table
        profile = supabase.table("profiles") \
            .select("sap_number, full_name, role, department") \
            .eq("id", response.user.id) \
            .single() \
            .execute()

        if not profile.data:
            return False, "Profile not found. Contact your administrator."

        # Store in session state
        st.session_state["logged_in"]   = True
        st.session_state["user_id"]     = response.user.id
        st.session_state["sap_number"]  = profile.data["sap_number"]
        st.session_state["full_name"]   = profile.data["full_name"]
        st.session_state["role"]        = profile.data["role"]
        st.session_state["department"]  = profile.data["department"]
        st.session_state["access_token"] = response.session.access_token

        # Store the AUTHENTICATED client itself so other pages
        # can reuse it and pass RLS checks
        st.session_state["supabase_client"] = supabase

        return True, f"Welcome, {profile.data['full_name']}!"

    except Exception as e:
        error_msg = str(e)
        if "Invalid login credentials" in error_msg:
            return False, "Invalid SAP number or password."
        return False, f"Login error: {error_msg}"


def logout():
    """Clears session state and logs out."""
    try:
        supabase = get_supabase()
        supabase.auth.sign_out()
    except:
        pass

    for key in ["logged_in", "user_id", "sap_number", "full_name", "role",
                 "department", "access_token", "supabase_client"]:
        st.session_state.pop(key, None)


def is_logged_in():
    """Returns True if a user is currently logged in."""
    return st.session_state.get("logged_in", False)


def get_role():
    """Returns the current user's role, or None if not logged in."""
    return st.session_state.get("role", None)


def show_login_form():
    """
    Renders the login form in the sidebar.
    Called from main.py sidebar section.
    """
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔐 Staff Login")
    st.sidebar.caption("Supervisor / IC / Management only")

    with st.sidebar.form("login_form", clear_on_submit=True):
        sap    = st.text_input("SAP Number", placeholder="e.g. S12345")
        pw     = st.text_input("Password",   type="password")
        submit = st.form_submit_button("Login", use_container_width=True)

        if submit:
            if not sap or not pw:
                st.error("Please enter both SAP number and password.")
            else:
                success, message = login(sap.strip(), pw)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)


def show_user_info():
    """
    Shows logged-in user info + logout button in the sidebar.
    Called from main.py when user is already logged in.
    """
    role     = st.session_state.get("role", "")
    name     = st.session_state.get("full_name", "")
    sap      = st.session_state.get("sap_number", "")
    dept     = st.session_state.get("department", "")

    # Role badge colour
    badge_color = {
        "management": "#0A8A72",
        "supervisor": "#1A6FB5",
        "ic":         "#E8920A",
    }.get(role, "#888780")

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        f"""
        <div style="
            background: {badge_color}18;
            border: 1px solid {badge_color}40;
            border-radius: 8px;
            padding: 10px 12px;
            margin-bottom: 6px;
        ">
            <div style="font-size:12px;color:{badge_color};font-weight:700;text-transform:uppercase;letter-spacing:1px;">
                {role}
            </div>
            <div style="font-size:14px;font-weight:600;margin-top:2px;">{name}</div>
            <div style="font-size:11px;color:#6B7A99;">{sap} · {dept}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.sidebar.button("🚪 Logout", use_container_width=True):
        logout()
        st.rerun()
