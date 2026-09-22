# app/collector_shoe.py
# ── Collector Shoe Wear Tracking — Redesigned ─────────────────

import streamlit as st
import pandas as pd
import plotly.express as px
import os, sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.login import get_supabase, is_logged_in, get_role

# ── NEA Weather — Sengkang/Punggol (North-East) ───────────────
NEA_FORECAST_URL = "https://api-open.data.gov.sg/v2/real-time/api/two-hr-forecast"
NEA_TARGET_AREAS = ["sengkang", "punggol"]  # priority order — Sengkang checked first

ROTATION_THRESHOLD_DRY   = 4.0  # mm — default (non-rainy season)
ROTATION_THRESHOLD_RAINY = 3.0  # mm — rainy season (wet rails increase wear)

WEATHER_EMOJI = {
    "rainy":   "🌧️",
    "cloudy":  "☁️",
    "fair":    "☀️",
    "unknown": "🌤️",
}


@st.cache_data(ttl=600)  # cache for 10 minutes — NEA updates every 30 mins
def fetch_nea_weather():
    """
    Fetches the 2-hour weather forecast from NEA data.gov.sg.
    Checks areas covering Sengkang/Punggol (North-East region).
    Returns dict: {is_rainy, condition, area, threshold}
    No API key required — data.gov.sg is open access.
    """
    try:
        import requests
        resp = requests.get(NEA_FORECAST_URL, timeout=5)
        if resp.status_code != 200:
            return {"is_rainy": False, "condition": "unknown", "area": "N/A", "threshold": ROTATION_THRESHOLD_DRY, "error": f"HTTP {resp.status_code}"}

        data = resp.json()

        # Navigate NEA response structure
        forecasts = (
            data.get("data", {})
                .get("items", [{}])[0]
                .get("forecasts", [])
        )

        # Check Sengkang first, then Punggol as fallback
        is_rainy     = False
        condition    = "Fair"
        matched_area = "Sengkang"

        # Build lookup dict for fast area search
        forecast_map = {f.get("area", "").lower(): f for f in forecasts}

        for target in NEA_TARGET_AREAS:
            if target in forecast_map:
                f    = forecast_map[target]
                fcst = f.get("forecast", "").lower()
                condition    = f.get("forecast", "Fair")
                matched_area = f.get("area", target.title())
                if "rain" in fcst or "shower" in fcst or "thunder" in fcst:
                    is_rainy = True
                break  # stop at first found area (Sengkang priority)

        threshold = ROTATION_THRESHOLD_RAINY if is_rainy else ROTATION_THRESHOLD_DRY

        return {
            "is_rainy":  is_rainy,
            "condition": condition,
            "area":      matched_area,
            "threshold": threshold,
            "error":     None,
        }

    except Exception as e:
        return {
            "is_rainy":  False,
            "condition": "unknown",
            "area":      "N/A",
            "threshold": ROTATION_THRESHOLD_DRY,
            "error":     str(e),
        }


def _show_weather_banner(supabase):
    """
    Displays a weather banner at the top of the Collector Shoe page showing:
    - Current NEA weather for Sengkang/Punggol
    - Active rotation threshold (auto-toggled based on weather)
    - Manual override toggle for supervisors/management
    """
    weather = fetch_nea_weather()

    # ── Manual override (supervisor/management only) ───────────
    override_key = "weather_threshold_override"
    if is_logged_in() and get_role() in ("management", "supervisor", "ic"):
        if override_key not in st.session_state:
            st.session_state[override_key] = None  # None = use auto

    override = st.session_state.get(override_key, None)
    threshold = override if override is not None else weather["threshold"]
    is_rainy  = threshold == ROTATION_THRESHOLD_RAINY

    # ── Banner colour ──────────────────────────────────────────
    if weather["error"]:
        banner_bg, banner_border, banner_text = "#F8FAFC", "#E2E8F0", "#64748B"
        emoji = "🌤️"
    elif is_rainy:
        banner_bg, banner_border, banner_text = "#EFF6FF", "#3B82F6", "#1D4ED8"
        emoji = "🌧️"
    else:
        banner_bg, banner_border, banner_text = "#F0FDF4", "#0A8A72", "#166534"
        emoji = "☀️"

    source = "⚙️ Manual override" if override is not None else "🌐 NEA live forecast"
    auto_label = f"Rainy season (≥{ROTATION_THRESHOLD_RAINY}mm)" if is_rainy else f"Dry season (≥{ROTATION_THRESHOLD_DRY}mm)"

    st.markdown(
        f"""<div style="background:{banner_bg};border:1px solid {banner_border};
        border-radius:12px;padding:14px 20px;margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
            <div>
                <span style="font-size:22px;">{emoji}</span>
                <span style="font-size:14px;font-weight:700;color:{banner_text};margin-left:8px;">
                    {weather['condition']} — {weather['area']}
                </span>
                <span style="font-size:11px;color:#94A3B8;margin-left:8px;">({source})</span>
            </div>
            <div style="text-align:right;">
                <div style="font-size:11px;color:#94A3B8;text-transform:uppercase;letter-spacing:1px;">
                    Active Rotation Threshold
                </div>
                <div style="font-size:20px;font-weight:700;color:{banner_text};">
                    ≥ {threshold}mm — {auto_label}
                </div>
            </div>
        </div>
        </div>""",
        unsafe_allow_html=True
    )

    if weather["error"]:
        st.caption(f"⚠️ Could not fetch NEA weather ({weather['error']}) — using default dry season threshold.")

    # ── Manual override toggle (supervisor/management only) ────
    if is_logged_in() and get_role() in ("management", "supervisor", "ic"):
        with st.expander("⚙️ Manual Threshold Override", expanded=False):
            st.caption("Override the auto-detected threshold if weather data is incorrect or conditions have changed.")
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("☀️ Force Dry (4mm)", use_container_width=True,
                             type="primary" if override == ROTATION_THRESHOLD_DRY else "secondary"):
                    st.session_state[override_key] = ROTATION_THRESHOLD_DRY
                    st.rerun()
            with col2:
                if st.button("🌧️ Force Rainy (3mm)", use_container_width=True,
                             type="primary" if override == ROTATION_THRESHOLD_RAINY else "secondary"):
                    st.session_state[override_key] = ROTATION_THRESHOLD_RAINY
                    st.rerun()
            with col3:
                if st.button("🔄 Reset to Auto", use_container_width=True,
                             type="primary" if override is None else "secondary"):
                    st.session_state[override_key] = None
                    st.rerun()

    return threshold  # return active threshold for use in wear severity logic

# ── Design tokens ──────────────────────────────────────────────
PASS_COLOR    = "#0A8A72"
FAIL_COLOR    = "#C9382A"
WARN_COLOR    = "#E8920A"
SLATE         = "#1E293B"
CARD_BG       = "#F8FAFC"
BORDER        = "#E2E8F0"

SEVERITY_COLOR = {
    "none":     "#0A8A72",
    "minor":    "#E8920A",
    "moderate": "#E85D04",
    "severe":   "#C9382A",
}
SEVERITY_EMOJI = {
    "none": "🟢", "minor": "🟡", "moderate": "🟠", "severe": "🔴"
}
CORR_EMOJI = {"agree": "✅", "disagree": "❌"}
PF_EMOJI   = {"pass":  "✅", "fail":     "❌"}


# ── Data loaders ───────────────────────────────────────────────
@st.cache_data(ttl=30)
@st.cache_data(ttl=60)
def load_correlation(_sb):
    try:
        r = _sb.table("shoe_wear_correlation").select("*").execute()
        return pd.DataFrame(r.data) if r.data else pd.DataFrame()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=60)
def load_degradation(_sb):
    try:
        r = _sb.table("shoe_degradation_trend").select("*").execute()
        return pd.DataFrame(r.data) if r.data else pd.DataFrame()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=60)
def load_shoes(_sb):
    try:
        r = _sb.table("collector_shoes") \
            .select("shoe_id,condition,lrv_asset_id,baseline_thickness_mm,registered_at,notes,rotation_status") \
            .order("registered_at", desc=True).execute()
        return pd.DataFrame(r.data) if r.data else pd.DataFrame()
    except:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_confidence_progression(_sb, days=90):
    """
    Loads YOLO confidence scores over time per asset from defect_records.
    Defaults to last 90 days to reduce egress — enough for trend analysis.
    With multiple records per capture (Option B), only the highest confidence
    defect detection per session is shown — prevents one capture appearing
    as multiple data points on the trend chart.
    """
    try:
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        r = _sb.table("defect_records") \
            .select("session_id, confidence, defect_type, detected_at, inspection_sessions(asset_id)") \
            .not_.is_("confidence", "null") \
            .gt("confidence", 0) \
            .neq("defect_type", "none") \
            .gte("detected_at", cutoff) \
            .order("detected_at", desc=False) \
            .execute()
        if not r.data:
            return pd.DataFrame()
        df = pd.DataFrame(r.data)
        df["asset_id"] = df["inspection_sessions"].apply(
            lambda x: x.get("asset_id") if isinstance(x, dict) else None
        )
        df["detected_at"]    = pd.to_datetime(df["detected_at"])
        df["confidence_pct"] = (df["confidence"] * 100).round(1)
        df = df[["session_id", "asset_id", "defect_type", "confidence_pct", "detected_at"]].dropna(subset=["asset_id"])

        # Keep only highest confidence detection per session
        df = df.sort_values("confidence_pct", ascending=False)
        df = df.drop_duplicates(subset=["session_id"], keep="first")
        df = df.sort_values("detected_at")

        return df[["asset_id", "defect_type", "confidence_pct", "detected_at"]]
    except:
        return pd.DataFrame()


# ── CSS ────────────────────────────────────────────────────────
def _inject_css():
    st.markdown("""
    <style>
    /* Shoe status card */
    .shoe-card {
        background: #fff;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 0;
        overflow: hidden;
        margin-bottom: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .shoe-card-bar {
        height: 6px;
        width: 100%;
    }
    .shoe-card-body {
        padding: 18px 20px 16px;
    }
    .shoe-card-id {
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        color: #64748B;
        margin-bottom: 4px;
    }
    .shoe-card-thickness {
        font-size: 32px;
        font-weight: 700;
        font-family: 'Courier New', monospace;
        color: #1E293B;
        line-height: 1;
        margin-bottom: 2px;
    }
    .shoe-card-unit {
        font-size: 13px;
        color: #94A3B8;
        font-weight: 400;
    }
    .shoe-card-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.5px;
        margin: 10px 0 12px;
    }
    .shoe-card-badge.pass {
        background: #DCFCE7;
        color: #166534;
    }
    .shoe-card-badge.fail {
        background: #FEE2E2;
        color: #991B1B;
    }
    .shoe-card-row {
        display: flex;
        justify-content: space-between;
        font-size: 12px;
        color: #64748B;
        margin-top: 4px;
    }
    .shoe-card-label {
        font-weight: 500;
    }
    .wear-bar-bg {
        background: #F1F5F9;
        border-radius: 4px;
        height: 6px;
        margin-top: 10px;
        overflow: hidden;
    }
    .wear-bar-fill {
        height: 6px;
        border-radius: 4px;
        transition: width 0.3s;
    }
    .shoe-card-divider {
        border: none;
        border-top: 1px solid #F1F5F9;
        margin: 12px 0 10px;
    }

    /* Metric cards */
    .metric-card {
        background: #fff;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 16px 18px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .metric-card .metric-label {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 1px;
        text-transform: uppercase;
        color: #94A3B8;
        margin-bottom: 6px;
    }
    .metric-card .metric-value {
        font-size: 28px;
        font-weight: 700;
        font-family: 'Courier New', monospace;
        line-height: 1;
    }
    .metric-card .metric-sub {
        font-size: 11px;
        color: #94A3B8;
        margin-top: 4px;
    }

    /* Section header */
    .section-header {
        font-size: 16px;
        font-weight: 700;
        letter-spacing: 0.5px;
        color: #1E293B;
        margin: 28px 0 6px;
        padding-bottom: 8px;
        border-bottom: 2px solid #E2E8F0;
    }
    /* Section intro */
    .section-intro {
        font-size: 13px;
        color: #475569;
        margin-bottom: 12px;
        line-height: 1.5;
    }
    </style>
    """, unsafe_allow_html=True)


# ── Shoe status card ───────────────────────────────────────────
def _shoe_card(shoe_id, corr_df, shoes_df):
    latest = corr_df[corr_df["shoe_id"] == shoe_id].iloc[0] if not corr_df[corr_df["shoe_id"] == shoe_id].empty else None
    shoe   = shoes_df[shoes_df["shoe_id"] == shoe_id].iloc[0] if not shoes_df[shoes_df["shoe_id"] == shoe_id].empty else None

    if latest is None:
        return

    thick     = latest.get("thickness_mm", "—")
    pf        = latest.get("pass_fail", "—")
    phys_sev  = latest.get("physical_severity", "—")
    vis_sev   = latest.get("visual_severity", "—")
    corr      = latest.get("correlation_status", "—")
    bar_color = PASS_COLOR if pf == "pass" else FAIL_COLOR
    badge_cls = "pass" if pf == "pass" else "fail"
    badge_txt = "✅ PASS" if pf == "pass" else "❌ FAIL"

    # Wear percentage
    wear_pct = 0
    if shoe is not None and shoe.get("baseline_thickness_mm") and thick != "—":
        baseline = float(shoe["baseline_thickness_mm"])
        wear_pct = min(100, round((baseline - float(thick)) / baseline * 100, 1))
    wear_color = PASS_COLOR if wear_pct < 30 else (WARN_COLOR if wear_pct < 60 else FAIL_COLOR)

    condition = shoe["condition"].upper() if shoe is not None else "—"
    baseline  = f"{shoe['baseline_thickness_mm']}mm" if shoe is not None and shoe.get("baseline_thickness_mm") else "—"

    st.markdown(f"""
    <div class="shoe-card">
        <div class="shoe-card-bar" style="background:{bar_color}"></div>
        <div class="shoe-card-body">
            <div class="shoe-card-id">{shoe_id} &nbsp;·&nbsp; {condition}</div>
            <div class="shoe-card-thickness">{thick}<span class="shoe-card-unit"> mm</span></div>
            <div class="shoe-card-badge {badge_cls}">{badge_txt}</div>
            <hr class="shoe-card-divider">
            <div class="shoe-card-row">
                <span class="shoe-card-label">Baseline</span>
                <span>{baseline}</span>
            </div>
            <div class="shoe-card-row">
                <span class="shoe-card-label">Wear</span>
                <span style="color:{wear_color};font-weight:600">{wear_pct}%</span>
            </div>
            <div class="wear-bar-bg">
                <div class="wear-bar-fill" style="width:{wear_pct}%;background:{wear_color}"></div>
            </div>
            <hr class="shoe-card-divider">
            <div class="shoe-card-row">
                <span class="shoe-card-label">Physical</span>
                <span>{SEVERITY_EMOJI.get(phys_sev,'')} {phys_sev}</span>
            </div>
            <div class="shoe-card-row">
                <span class="shoe-card-label">Visual (YOLO)</span>
                <span>{SEVERITY_EMOJI.get(vis_sev,'')} {vis_sev}</span>
            </div>
            <div class="shoe-card-row">
                <span class="shoe-card-label">Correlation</span>
                <span>{CORR_EMOJI.get(corr,'')} {corr}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Metric card ────────────────────────────────────────────────
def _metric(label, value, sub="", color="#1E293B"):
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value" style="color:{color}">{value}</div>
        <div class="metric-sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


# ── Registration form ──────────────────────────────────────────
def _show_registration_form(supabase):
    st.markdown("#### ➕ Register New Collector Shoe")
    st.caption("Register a new collector shoe when it is installed on an LRV.")

    # ── LRV vehicle data ───────────────────────────────────────
    LRV_MODELS = {
        "Test / Training Vehicle": [0],
        "Non-Modified C810": [
            2,3,6,8,11,14,16,17,19,20,24,29,32,37,38,39,40,41
        ],
        "Modified C810": [
            4,5,7,9,10,12,15,18,22,25,27,28,30,33,35,36
        ],
        "New C810A": [
            42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57
        ],
        "C810D": [
            58,59,60,61,62,63,64,65,66,67,68,69
        ],
    }
    CAB_POSITIONS = {"A": ["1", "2"], "B": ["3", "4"]}

    # ── LRV Model + Number + Cab End all outside form ────────────
    # Keeps them reactive without glitchiness
    c1, c2 = st.columns(2)
    lrv_model  = c1.selectbox("LRV Model", list(LRV_MODELS.keys()), key="reg_lrv_model")
    lrv_nums   = [f"LRV{n:02d}" for n in LRV_MODELS[lrv_model]]
    lrv_number = c2.selectbox("LRV Number", lrv_nums, key="reg_lrv_number")

    st.markdown("**Position**")
    p1, p2, p3 = st.columns(3)
    cab_end = p1.selectbox(
        "Cab End", ["A", "B"],
        help="A = Cab End A | B = Cab End B",
        key="reg_cab_end"
    )

    with st.form("register_shoe_form", clear_on_submit=True):

        # ── Row 2: Condition ───────────────────────────────────
        condition_descriptions = {
            "new":     "new — Never installed, straight from storage",
            "old":     "old — Previously used, has visible wear",
            "unknown": "unknown — Condition not yet assessed",
        }
        condition_display = list(condition_descriptions.values())
        condition_keys    = list(condition_descriptions.keys())
        condition_sel     = st.selectbox("Condition", condition_display)
        condition         = condition_keys[condition_display.index(condition_sel)]

        # ── Position + Side (inside form, uses cab_end from above)
        position = p2.selectbox(
            "Position", CAB_POSITIONS[cab_end],
            help="A: positions 1 & 2 | B: positions 3 & 4"
        )
        side_sel = p3.selectbox("Upper / Lower", ["+ Upper", "- Lower"])
        side     = "+" if side_sel.startswith("+") else "-"

        # ── Generated Shoe ID ──────────────────────────────────
        shoe_id = f"CS-{lrv_number}-{side}{cab_end}{position}"
        st.markdown(
            f"""<div style="background:#F0FDF4;border:1px solid #0A8A72;border-radius:8px;
            padding:10px 14px;margin:8px 0;">
            <span style="font-size:11px;color:#64748B;font-weight:600;">
            GENERATED SHOE ID</span><br>
            <span style="font-size:20px;font-weight:700;font-family:monospace;
            color:#0A8A72;">{shoe_id}</span>
            </div>""",
            unsafe_allow_html=True
        )

        # ── Row 3: Baseline + Date ─────────────────────────────
        c3, c4 = st.columns(2)
        baseline = c3.number_input(
            "Baseline Thickness (mm)",
            min_value=0.0, max_value=100.0,
            value=16.0, step=0.1,
            help="Original unworn thickness — confirmed as 16mm by engineer"
        )
        if baseline != 16.0 and baseline > 0:
            if baseline < 10.0 or baseline > 20.0:
                c3.warning(f"⚠️ {baseline}mm is unusual — confirmed original depth is 16mm.")
            else:
                c3.info("ℹ️ Default is 16mm — are you sure this shoe has a different baseline?")
        reg_date = c4.date_input(
            "Installation Date",
            value=datetime.now().date(),
            help="Date the collector shoe was physically installed on the LRV"
        )

        # ── Rotation Status ────────────────────────────────────
        rotation_status_options = {
            "in_service":    "In Service — wear < 3mm (rainy) / < 4mm (dry), actively monitored",
            "not_rotated":   "Not Rotated — wear ≥ 3mm (rainy) / ≥ 4mm (dry), rotation pending",
            "rotated_once":  "Rotated Once — rotation performed, second side in use",
            "rotated_twice": "Rotated Twice — both sides worn, pending replacement",
            "retired":       "Retired — removed from service",
        }
        rs_display = list(rotation_status_options.values())
        rs_keys    = list(rotation_status_options.keys())
        rs_sel     = st.selectbox(
            "Rotation Status", rs_display, index=0,
            help="Select the current service state of this collector shoe"
        )
        rotation_status = rs_keys[rs_display.index(rs_sel)]

        notes = st.text_area(
            "Notes (optional)",
            placeholder="e.g. Cab End A, Position 1, Upper — inspected during 2000km PM",
            height=60
        )

        submitted = st.form_submit_button(
            "Register Shoe", type="primary", width="stretch"
        )

        if submitted:
            if baseline == 0.0:
                st.error("Please enter the baseline thickness.")
            else:
                try:
                    supabase.table("collector_shoes").insert({
                        "shoe_id":               shoe_id,
                        "condition":             condition,
                        "lrv_asset_id":          lrv_number,
                        "baseline_thickness_mm": baseline,
                        "registered_at":         reg_date.isoformat(),
                        "rotation_status":       rotation_status,
                        "notes":                 notes.strip() or None,
                    }).execute()
                    st.session_state["reg_success_msg"] = f"✅ **{shoe_id}** registered successfully!"
                    st.session_state["reg_expander_open"] = False
                    load_shoes.clear()
                    load_correlation.clear()
                    st.rerun()
                except Exception as e:
                    if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                        st.error(f"**{shoe_id}** is already registered.")
                    else:
                        st.error(f"Registration failed: {e}")


# ── Main show() ────────────────────────────────────────────────
def _show_confidence_progression(supabase):
    """
    Shows YOLO detection confidence over time per asset.
    Rising confidence = defect becoming more visually pronounced (worsening).
    Stable/falling confidence = condition stable or improving.
    """
    # ── Check registered shoes first ──────────────────────────
    try:
        registered = supabase.table("collector_shoes").select("shoe_id").execute()
        registered_ids = {r["shoe_id"] for r in registered.data} if registered.data else set()
    except:
        registered_ids = set()

    if not registered_ids:
        st.info("📭 No collector shoes registered yet. Register a shoe above to start tracking.")
        return

    df = load_confidence_progression(supabase)

    if df.empty:
        st.info("📅 No inspection captures found in the last 90 days for registered shoes. Older data exists but is not shown to save bandwidth. Use the camera station to capture new inspections.")
        return

    # Filter to only defect detections (exclude 'none')
    defect_df = df[df["defect_type"] != "none"].copy()

    if defect_df.empty:
        st.info("📷 No defect detections recorded yet for registered shoes. Trend will appear once wear is detected.")
        return

    # ── Filter to registered shoes only ───────────────────────
    if registered_ids:
        defect_df = defect_df[defect_df["asset_id"].isin(registered_ids)]

    if defect_df.empty:
        st.info("📷 No inspection captures found for registered collector shoes yet. Use the camera station to begin capturing.")
        return

    # Asset filter
    assets = sorted(defect_df["asset_id"].unique().tolist())
    selected = st.selectbox(
        "Select asset", ["All"] + assets, key="conf_asset"
    )

    plot_df = defect_df if selected == "All" else defect_df[defect_df["asset_id"] == selected]

    # Build chart
    fig = px.line(
        plot_df,
        x="detected_at",
        y="confidence_pct",
        color="asset_id" if selected == "All" else None,
        markers=True,
        color_discrete_sequence=["#0A8A72", "#C9382A", "#E8920A", "#6B21A8"],
        labels={"confidence_pct": "YOLO Confidence (%)", "detected_at": ""},
    )

    # Add 75% threshold line
    fig.add_hline(
        y=75,
        line_dash="dash",
        line_color="#E8920A",
        annotation_text="75% review threshold",
        annotation_position="right",
    )

    # Add 95% target line
    fig.add_hline(
        y=95,
        line_dash="dot",
        line_color="#0A8A72",
        annotation_text="95% target",
        annotation_position="right",
    )

    fig.update_layout(
        height=300,
        margin=dict(l=0, r=100, t=10, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, title=""),
        yaxis=dict(
            showgrid=True,
            gridcolor="#F1F5F9",
            title="Confidence (%)",
            range=[0, 100],
        ),
        legend=dict(orientation="h", y=-0.2),
    )

    st.plotly_chart(fig)

    # Interpretation helper
    if selected != "All" and len(plot_df) >= 2:
        first_conf = plot_df.iloc[0]["confidence_pct"]
        last_conf  = plot_df.iloc[-1]["confidence_pct"]
        change     = last_conf - first_conf
        n          = len(plot_df)

        if change > 10:
            st.warning(
                f"⚠️ **Confidence rising (+{change:.1f}% over {n} inspections)** — "
                f"the defect is becoming more visually pronounced. Consider increasing inspection frequency."
            )
        elif change < -10:
            st.success(
                f"✅ **Confidence falling ({change:.1f}% over {n} inspections)** — "
                f"defect may be less prominent. Verify with physical measurement."
            )
        else:
            st.info(
                f"📊 **Confidence stable ({change:+.1f}% over {n} inspections)** — "
                f"no significant visual change detected."
            )

    st.caption(
        "⚠️ Note: confidence reflects how visually distinct the defect appears to the YOLO model. "
        "A jump in confidence may also reflect a model update (v3→v4→v5) rather than physical worsening. "
        "Always correlate with physical depth gauge measurements for definitive severity assessment."
    )

    # ── Dynamic interpretation ─────────────────────────────────
    if not defect_df.empty:
        # Load registered shoe IDs to filter out test/legacy assets
        try:
            registered = supabase.table("collector_shoes").select("shoe_id").execute()
            registered_ids = {r["shoe_id"] for r in registered.data} if registered.data else set()
        except:
            registered_ids = set()

        with st.expander("📊 Chart Interpretation", expanded=False):
            assets = defect_df["asset_id"].unique() if selected == "All" else [selected]

            # Filter to registered shoes only — skip test/legacy asset IDs
            registered_assets = [a for a in assets if a in registered_ids]

            if not registered_assets:
                st.info("No registered collector shoes have enough detections to show a trend yet.")
            else:
                for asset in registered_assets:
                    asset_data = defect_df[defect_df["asset_id"] == asset].sort_values("detected_at")
                    if len(asset_data) < 2:
                        st.markdown(f"**{asset}** — Only 1 detection recorded. More inspections needed to identify a trend.")
                        continue

                    first_conf = asset_data.iloc[0]["confidence_pct"]
                    last_conf  = asset_data.iloc[-1]["confidence_pct"]
                    change     = round(last_conf - first_conf, 1)
                    n          = len(asset_data)

                    if change > 10:
                        st.warning(
                            f"**{asset}** — 📈 Rising trend (+{change}% over {n} inspections). "
                            f"The defect is becoming more visually pronounced, typically indicating "
                            f"progressive surface wear or growing defect extent. "
                            f"Recommend increasing inspection frequency and correlating with physical measurement."
                        )
                    elif change < -10:
                        st.info(
                            f"**{asset}** — 📉 Falling trend ({change}% over {n} inspections). "
                            f"The defect appears less visually distinct. This may reflect improved capture "
                            f"conditions (better lighting/angle) rather than actual improvement. "
                            f"Verify with physical depth gauge measurement."
                        )
                    else:
                        st.success(
                            f"**{asset}** — 📊 Stable trend ({change:+.1f}% over {n} inspections). "
                            f"No significant change in defect visibility. Continue normal inspection schedule."
                        )
    _inject_css()


def _show_defect_heatmap(supabase):
    """Shows a heatmap of worst defect per shoe position across all LRVs."""
    st.markdown('<div class="section-header">Per-LRV Defect Heatmap</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="section-intro">Fleet-wide overview showing the most severe defect detected per shoe position across all inspected LRVs. Quickly identifies which vehicles and positions need attention.</div>', unsafe_allow_html=True)

    with st.expander("🗺️ View Per-LRV Defect Heatmap", expanded=False):
        try:
            r = supabase.table("defect_records") \
                .select("defect_type, confidence, inspection_sessions(asset_id)") \
                .gt("confidence", 0) \
                .execute()

            if not r.data:
                st.info("No defect data yet. Heatmap will appear once inspections are submitted.")
                return

            df = pd.DataFrame(r.data)
            df["asset_id"] = df["inspection_sessions"].apply(
                lambda x: x.get("asset_id") if isinstance(x, dict) else None
            )
            df = df.dropna(subset=["asset_id"])

            if df.empty:
                st.info("No defect data yet.")
                return

            def extract_parts(asset_id):
                try:
                    parts  = asset_id.split("-")
                    lrv    = parts[1]
                    prefix = f"CS-{lrv}-"
                    pos    = asset_id[len(prefix):]
                    return lrv, pos
                except:
                    return None, None

            df[["lrv", "position"]] = df["asset_id"].apply(
                lambda x: pd.Series(extract_parts(x))
            )
            df = df.dropna(subset=["lrv", "position"])

            SEVERITY_RANK = {
                "none": 0, "scuff marks": 1, "wear": 2,
                "corrosion": 3, "crack": 3, "arcing": 4,
            }
            SEVERITY_COLOR = {
                0: "#DCFCE7", 1: "#FEF9C3", 2: "#FED7AA",
                3: "#FECACA", 4: "#DC2626",
            }
            SEVERITY_LABEL = {
                0: "✅ None", 1: "🟡 Scuff Marks", 2: "🟠 Wear",
                3: "🔴 Crack/Corrosion", 4: "🚨 Arcing",
            }

            df["severity_rank"] = df["defect_type"].apply(
                lambda x: SEVERITY_RANK.get(x.lower(), 0) if isinstance(x, str) else 0
            )
            worst     = df.groupby(["lrv", "position"])["severity_rank"].max().reset_index()
            worst["color"] = worst["severity_rank"].map(SEVERITY_COLOR)
            worst["label"] = worst["severity_rank"].map(SEVERITY_LABEL)

            lrvs      = sorted(worst["lrv"].unique().tolist())
            positions = ["+A1", "-A1", "+A2", "-A2", "+B3", "-B3", "+B4", "-B4"]

            header_cells = "".join(
                f'<th style="padding:8px 12px;font-size:11px;color:#64748B;font-weight:600;">{p}</th>'
                for p in positions
            )
            rows_html = ""
            for lrv in lrvs:
                row = f'<tr><td style="padding:8px 12px;font-weight:700;font-size:12px;color:#1E293B;white-space:nowrap;">{lrv}</td>'
                for pos in positions:
                    match = worst[(worst["lrv"] == lrv) & (worst["position"] == pos)]
                    if not match.empty:
                        color = match.iloc[0]["color"]
                        label = match.iloc[0]["label"]
                        row += f'<td style="padding:8px;text-align:center;background:{color};border-radius:4px;font-size:11px;">{label}</td>'
                    else:
                        row += '<td style="padding:8px;text-align:center;background:#F8FAFC;color:#94A3B8;font-size:11px;">—</td>'
                row += "</tr>"
                rows_html += row

            st.markdown(f"""
            <div style="overflow-x:auto;margin-top:8px;">
            <table style="border-collapse:separate;border-spacing:4px;width:100%;">
                <thead><tr>
                    <th style="padding:8px 12px;font-size:11px;color:#64748B;font-weight:600;text-align:left;">LRV</th>
                    {header_cells}
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table></div>""", unsafe_allow_html=True)

            st.markdown(
                """<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:12px;font-size:11px;">
                <span style="background:#DCFCE7;padding:4px 10px;border-radius:4px;">✅ None</span>
                <span style="background:#FEF9C3;padding:4px 10px;border-radius:4px;">🟡 Scuff Marks</span>
                <span style="background:#FED7AA;padding:4px 10px;border-radius:4px;">🟠 Wear</span>
                <span style="background:#FECACA;padding:4px 10px;border-radius:4px;">🔴 Crack / Corrosion</span>
                <span style="background:#DC2626;color:white;padding:4px 10px;border-radius:4px;">🚨 Arcing</span>
                <span style="background:#F8FAFC;color:#94A3B8;padding:4px 10px;border-radius:4px;">— Not inspected</span>
                </div>""", unsafe_allow_html=True
            )
            st.caption("Heatmap shows most severe defect per shoe position. Physical depth gauge measurement required for accurate severity assessment.")

        except Exception as e:
            st.error(f"Could not load defect heatmap: {e}")


def _show_session_frequency(supabase):
    """Shows number of inspection sessions over time."""
    st.markdown('<div class="section-header">Inspection Session Frequency</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="section-intro">Tracks how often inspections are being conducted over time. Helps monitor inspection compliance across the fleet or for a specific shoe.</div>', unsafe_allow_html=True)

    with st.expander("📅 View Session Frequency Chart", expanded=False):
        try:
            r = supabase.table("inspection_sessions") \
                .select("id, asset_id, created_at") \
                .order("created_at", desc=False) \
                .execute()

            if not r.data:
                st.info("No inspection session data yet.")
                return

            df = pd.DataFrame(r.data)
            df["created_at"] = pd.to_datetime(df["created_at"])

            if df.empty:
                st.info("No inspection session data yet.")
                return

            f1, f2     = st.columns(2)
            assets     = sorted(df["asset_id"].dropna().unique().tolist())
            selected   = f1.selectbox("Select asset", ["All"] + assets, key="sf_asset")
            granularity = f2.radio("View by", ["Week", "Day"], horizontal=True, key="sf_gran")

            plot_df = df if selected == "All" else df[df["asset_id"] == selected]

            if granularity == "Week":
                plot_df = plot_df.copy()
                plot_df["period"] = plot_df["created_at"].dt.to_period("W").apply(lambda x: x.start_time)
                x_label = "Week"
            else:
                plot_df = plot_df.copy()
                plot_df["period"] = plot_df["created_at"].dt.date
                x_label = "Day"

            freq = plot_df.groupby("period").size().reset_index(name="sessions")
            freq["period"] = pd.to_datetime(freq["period"])

            fig = px.line(
                freq,
                x="period",
                y="sessions",
                markers=True,
                color_discrete_sequence=["#0A8A72"],
                labels={"period": x_label, "sessions": "Number of Sessions"},
            )
            fig.update_layout(
                height=300,
                margin=dict(l=0, r=0, t=10, b=0),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=False, title=x_label),
                yaxis=dict(showgrid=True, gridcolor="#F1F5F9", title="Number of Sessions", rangemode="tozero"),
            )
            st.plotly_chart(fig)

            total_sessions      = len(plot_df)
            avg                 = round(freq["sessions"].mean(), 1)
            most_active_period  = freq.loc[freq["sessions"].idxmax(), "period"].strftime(
                "%d %b %Y" if granularity == "Day" else "Week of %d %b %Y"
            )
            most_active_count   = freq["sessions"].max()

            st.markdown(
                f"""<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;padding:12px 16px;margin-top:8px;">
                <div style="font-size:14px;font-weight:700;color:#1E293B;">
                📅 Total Sessions: {total_sessions} &nbsp;·&nbsp;
                Avg per {granularity}: <span style="color:#0A8A72;">{avg}</span> &nbsp;·&nbsp;
                Most Active: <span style="color:#0A8A72;">{most_active_period}</span> ({most_active_count} sessions)
                </div>
                <div style="font-size:12px;color:#64748B;margin-top:4px;">
                ⚠️ Each session represents one 3-angle inspection. Regular sessions indicate good inspection compliance.
                </div>
                </div>""",
                unsafe_allow_html=True
            )

        except Exception as e:
            st.error(f"Could not load session frequency: {e}")

def _show_detection_frequency(supabase):
    """Shows detection frequency by defect type per asset."""
    st.markdown('<div class="section-header">Detection Frequency by Defect Type</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="section-intro">Shows how often each defect type has been detected across all inspections. Useful for identifying which defects are most common on a specific shoe or across the fleet.</div>', unsafe_allow_html=True)

    with st.expander("📊 View Detection Frequency Chart", expanded=False):
        try:
            r = supabase.table("defect_records") \
                .select("*, inspection_sessions(asset_id)") \
                .not_.eq("defect_type", "none") \
                .gt("confidence", 0) \
                .execute()

            if not r.data:
                st.info("No defect detection data yet. Data will appear once inspections are submitted.")
                return

            df = pd.DataFrame(r.data)
            df["asset_id"] = df["inspection_sessions"].apply(
                lambda x: x.get("asset_id") if isinstance(x, dict) else None
            )
            df = df.dropna(subset=["asset_id"])

            if df.empty:
                st.info("No defect detection data yet.")
                return

            assets   = sorted(df["asset_id"].unique().tolist())
            selected = st.selectbox("Select asset", ["All"] + assets, key="freq_asset")
            plot_df  = df if selected == "All" else df[df["asset_id"] == selected]

            freq = plot_df.groupby("defect_type").size().reset_index(name="count")
            freq = freq.sort_values("count", ascending=False)

            color_map = {
                "wear":        "#E8920A",
                "scuff marks": "#1A6FB5",
                "crack":       "#C9382A",
                "corrosion":   "#6B21A8",
                "arcing":      "#DC2626",
            }
            colors = [color_map.get(d, "#64748B") for d in freq["defect_type"]]

            fig = px.bar(
                freq,
                x="defect_type",
                y="count",
                color="defect_type",
                color_discrete_sequence=colors,
                labels={"defect_type": "Defect Type", "count": "Number of Detections"},
            )
            fig.update_layout(
                height=300,
                margin=dict(l=0, r=0, t=10, b=0),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=False, title="Defect Type"),
                yaxis=dict(showgrid=True, gridcolor="#F1F5F9", title="Number of Detections"),
                showlegend=False,
            )
            st.plotly_chart(fig)

            top_defect = freq.iloc[0]["defect_type"] if not freq.empty else "none"
            top_count  = freq.iloc[0]["count"] if not freq.empty else 0
            total      = freq["count"].sum()

            st.markdown(
                f"""<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;padding:12px 16px;margin-top:8px;">
                <div style="font-size:14px;font-weight:700;color:#1E293B;">
                📊 Total Detections: {total} &nbsp;·&nbsp;
                Most Frequent: <span style="color:#E8920A;">{top_defect}</span> ({top_count} detections)
                </div>
                <div style="font-size:12px;color:#64748B;margin-top:4px;">
                ⚠️ Defect frequency reflects how often each defect type was detected — not physical severity.
                </div>
                </div>""",
                unsafe_allow_html=True
            )

        except Exception as e:
            st.error(f"Could not load detection frequency: {e}")


def show():
    _inject_css()
    st.markdown("## 👟 Collector Shoe Wear Tracking")

    # ── Persistent success message after registration ──────────
    if "reg_success_msg" in st.session_state:
        st.success(st.session_state.pop("reg_success_msg"))
    st.caption("Physical measurements vs visual YOLO inspection — correlation and degradation tracking.")
    st.divider()

    supabase  = get_supabase()
    corr_df   = load_correlation(supabase)
    degrad_df = load_degradation(supabase)
    shoes_df  = load_shoes(supabase)

    # ── Weather banner + active rotation threshold ─────────────
    active_threshold = _show_weather_banner(supabase)

    # ── Register new shoe — open to all (technician registers on install) ─
    # Persist expander state so it doesn't collapse on rerun
    reg_expanded = st.session_state.get("reg_expander_open", False)
    with st.expander("➕ Register New Collector Shoe", expanded=reg_expanded):
        st.caption("Register a new collector shoe when it is installed on an LRV.")
        _show_registration_form(supabase)

    # ── No data ────────────────────────────────────────────────
    # Note: don't return early here — confidence progression chart
    # should still show even if physical measurement data is empty.

    # ── Physical measurement sections (partner's scope) ─────────
    st.markdown(
        """<div style="background:#FFF7ED;border:1px solid #F59E0B;border-radius:12px;
        padding:18px 22px;margin-bottom:20px;">
        <div style="font-size:15px;font-weight:700;color:#92400E;margin-bottom:6px;">
        📋 Physical Measurement Data — Awaiting Input
        </div>
        <div style="font-size:13px;color:#78350F;line-height:1.6;">
        The following sections require <b>physical depth gauge measurements</b> taken during 
        scheduled preventive maintenance (PM) inspections:<br><br>
        &nbsp;&nbsp;• <b>Current Status</b> — shoe thickness and pass/fail per asset<br>
        &nbsp;&nbsp;• <b>Programme Summary</b> — fleet-wide pass rate and correlation metrics<br>
        &nbsp;&nbsp;• <b>Thickness Degradation Over Time</b> — wear trend per shoe<br>
        &nbsp;&nbsp;• <b>Wear Rate (mm/week)</b> — degradation rate and fleet average<br><br>
        </div>
        </div>""",
        unsafe_allow_html=True
    )

    # ── SECTION 5: Confidence progression ─────────────────────
    st.markdown('<div class="section-header">Visual Wear Progression (YOLO Confidence Trend)</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="section-intro">Tracks YOLO detection confidence scores over time per shoe. A rising trend may indicate the defect is becoming more visually prominent. Not a direct measure of physical severity — always verify with a depth gauge.</div>', unsafe_allow_html=True)
    with st.expander("📈 View Confidence Trend Chart", expanded=False):
        _show_confidence_progression(supabase)

    # ── SECTION 5b: Detection Frequency Chart ──────────────────
    _show_detection_frequency(supabase)

    # ── SECTION 5c: Session Frequency Chart ────────────────────
    _show_session_frequency(supabase)

    # ── SECTION 5d: Per-LRV Defect Heatmap ─────────────────────
    _show_defect_heatmap(supabase)

    # ── SECTION 6: Correlation records (collapsible) ───────────
    st.markdown('<div class="section-header">Correlation Records</div>', unsafe_allow_html=True)

    if not corr_df.empty:
        # Filters always visible
        f1, f2, f3, f4 = st.columns(4)
        shoe_filter = f1.selectbox("Shoe",     ["All"] + list(corr_df["shoe_id"].unique()) if "shoe_id" in corr_df.columns else ["All"])
        corr_filter = f2.selectbox("Correlation", ["All", "agree", "disagree"])
        pf_filter   = f3.selectbox("Pass / Fail",  ["All", "pass", "fail"])
        sev_filter  = f4.selectbox("Severity",     ["All", "none", "minor", "moderate", "severe"])

        filtered = corr_df.copy()
        if shoe_filter != "All" and "shoe_id"            in filtered.columns: filtered = filtered[filtered["shoe_id"] == shoe_filter]
        if corr_filter != "All" and "correlation_status" in filtered.columns: filtered = filtered[filtered["correlation_status"] == corr_filter]
        if pf_filter   != "All" and "pass_fail"          in filtered.columns: filtered = filtered[filtered["pass_fail"] == pf_filter]
        if sev_filter  != "All" and "physical_severity"  in filtered.columns: filtered = filtered[filtered["physical_severity"] == sev_filter]

        st.caption(f"Showing {len(filtered)} of {len(corr_df)} records")

        with st.expander(f"📋 Show records ({len(filtered)})", expanded=False):
            display_cols = [c for c in [
                "inspection_date","shoe_id","shoe_condition","thickness_mm",
                "physical_severity","pass_fail","visual_severity","visual_pass_fail",
                "yolo_confidence","correlation_status","technician_name"
            ] if c in filtered.columns]

            display_df = filtered[display_cols].copy()
            if "thickness_mm"       in display_df.columns: display_df["thickness_mm"]       = display_df["thickness_mm"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
            if "physical_severity"  in display_df.columns: display_df["physical_severity"]  = display_df["physical_severity"].apply(lambda x: f"{SEVERITY_EMOJI.get(x,'')} {x}" if x else x)
            if "visual_severity"    in display_df.columns: display_df["visual_severity"]    = display_df["visual_severity"].apply(lambda x: f"{SEVERITY_EMOJI.get(x,'')} {x}" if x else x)
            if "pass_fail"          in display_df.columns: display_df["pass_fail"]          = display_df["pass_fail"].apply(lambda x: f"{PF_EMOJI.get(x,'')} {x.upper()}" if x else x)
            if "visual_pass_fail"   in display_df.columns: display_df["visual_pass_fail"]   = display_df["visual_pass_fail"].apply(lambda x: f"{PF_EMOJI.get(x,'')} {x.upper()}" if x else x)
            if "correlation_status" in display_df.columns: display_df["correlation_status"] = display_df["correlation_status"].apply(lambda x: f"{CORR_EMOJI.get(x,'')} {x}" if x else x)
            if "yolo_confidence"    in display_df.columns: display_df["yolo_confidence"]    = display_df["yolo_confidence"].apply(lambda x: f"{x:.0%}" if pd.notna(x) else "—")

            def highlight(row):
                if "❌" in str(row.get("correlation_status", "")): return ["background-color:#FFF0F0"] * len(row)
                if "❌" in str(row.get("pass_fail", "")): return ["background-color:#FFF5F0"] * len(row)
                return ["background-color:#F0FDF4"] * len(row)

            st.dataframe(display_df.style.apply(highlight, axis=1), height=300, hide_index=True)

            csv_data = filtered.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download CSV", data=csv_data,
                file_name=f"collector_shoe_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

    # ── SECTION 7: Registered shoes (collapsible) ──────────────
    st.markdown('<div class="section-header">Registered Shoes</div>', unsafe_allow_html=True)

    if not shoes_df.empty:
        with st.expander("🗃 View registered shoes", expanded=True):

            ROTATION_OPTIONS = {
                "in_service":    "In Service — wear < 3mm (rainy) / < 4mm (dry), actively monitored",
                "not_rotated":   "Not Rotated — wear ≥ 3mm (rainy) / ≥ 4mm (dry), rotation pending",
                "rotated_once":  "Rotated Once — rotation performed, second side in use",
                "rotated_twice": "Rotated Twice — both sides worn, pending replacement",
                "retired":       "Retired — removed from service",
            }
            CONDITION_OPTIONS = {
                "new":     "new — Never installed, straight from storage",
                "old":     "old — Previously used, has visible wear",
                "unknown": "unknown — Condition not yet assessed",
            }

            for _, shoe in shoes_df.iterrows():
                shoe_id   = shoe["shoe_id"]
                condition = shoe.get("condition", "unknown")
                baseline  = shoe.get("baseline_thickness_mm", 16.0)
                rot_status = shoe.get("rotation_status", "in_service")
                notes_val  = shoe.get("notes", "") or ""
                reg_at     = shoe.get("registered_at", "")
                try:
                    reg_at = pd.to_datetime(reg_at, format='ISO8601').strftime("%d %b %Y")
                except:
                    pass

                with st.container(border=True):
                    col1, col2, col3 = st.columns([4, 1, 1])
                    with col1:
                        st.markdown(f"**{shoe_id}** &nbsp;·&nbsp; {condition} &nbsp;·&nbsp; {baseline}mm baseline &nbsp;·&nbsp; Installed: {reg_at}")
                        st.caption(f"Rotation: {ROTATION_OPTIONS.get(rot_status, rot_status)}")
                    with col2:
                        edit_key = f"edit_shoe_{shoe_id}"
                        if st.button("✏️ Edit", key=f"edit_btn_{shoe_id}", use_container_width=True):
                            st.session_state[edit_key] = not st.session_state.get(edit_key, False)
                            st.rerun()
                    with col3:
                        del_key = f"del_shoe_{shoe_id}"
                        if st.button("🗑️ Delete", key=f"del_btn_{shoe_id}", use_container_width=True):
                            st.session_state[del_key] = True
                            st.rerun()

                    # ── Edit form ──────────────────────────────
                    if st.session_state.get(f"edit_shoe_{shoe_id}", False):
                        with st.form(f"edit_form_{shoe_id}"):
                            st.markdown(f"**Editing: {shoe_id}**")
                            e1, e2 = st.columns(2)

                            cond_keys = list(CONDITION_OPTIONS.keys())
                            cond_vals = list(CONDITION_OPTIONS.values())
                            cond_idx  = cond_keys.index(condition) if condition in cond_keys else 0
                            new_condition = e1.selectbox("Condition", cond_vals, index=cond_idx)
                            new_condition = cond_keys[cond_vals.index(new_condition)]

                            new_baseline = e2.number_input(
                                "Baseline Thickness (mm)",
                                min_value=0.0, max_value=100.0,
                                value=float(baseline), step=0.1
                            )

                            rot_keys = list(ROTATION_OPTIONS.keys())
                            rot_vals = list(ROTATION_OPTIONS.values())
                            rot_idx  = rot_keys.index(rot_status) if rot_status in rot_keys else 0
                            new_rot  = st.selectbox("Rotation Status", rot_vals, index=rot_idx)
                            new_rot  = rot_keys[rot_vals.index(new_rot)]

                            new_notes = st.text_area("Notes", value=notes_val, height=60)

                            s1, s2 = st.columns(2)
                            if s1.form_submit_button("💾 Save Changes", type="primary"):
                                try:
                                    supabase.table("collector_shoes").update({
                                        "condition":             new_condition,
                                        "baseline_thickness_mm": new_baseline,
                                        "rotation_status":       new_rot,
                                        "notes":                 new_notes.strip() or None,
                                    }).eq("shoe_id", shoe_id).execute()
                                    st.session_state.pop(f"edit_shoe_{shoe_id}", None)
                                    st.success(f"✅ {shoe_id} updated!")
                                    load_shoes.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Update failed: {e}")
                            if s2.form_submit_button("Cancel"):
                                st.session_state.pop(f"edit_shoe_{shoe_id}", None)
                                st.rerun()

                    # ── Delete confirmation ────────────────────
                    if st.session_state.get(f"del_shoe_{shoe_id}", False):
                        st.warning(f"⚠️ Delete **{shoe_id}**? This cannot be undone.")
                        d1, d2 = st.columns(2)
                        with d1:
                            if st.button("✅ Yes, Delete", key=f"del_confirm_{shoe_id}", type="primary"):
                                try:
                                    supabase.table("collector_shoes").delete().eq("shoe_id", shoe_id).execute()
                                    st.session_state.pop(f"del_shoe_{shoe_id}", None)
                                    st.success(f"🗑️ {shoe_id} deleted.")
                                    load_shoes.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Delete failed: {e}")
                        with d2:
                            if st.button("❌ Cancel", key=f"del_cancel_{shoe_id}"):
                                st.session_state.pop(f"del_shoe_{shoe_id}", None)
                                st.rerun()
