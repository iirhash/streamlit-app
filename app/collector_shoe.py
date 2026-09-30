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


@st.cache_data(ttl=60)
def load_fleet_status(_sb):
    """
    Returns a dict keyed by lrv_asset_id with:
      - shoes: list of shoe_ids
      - last_inspected: most recent detected_at or None
      - worst_defect: defect_type with highest confidence (non-none)
      - worst_confidence: that confidence value
      - status: 'monitor_carefully' | 'operational' | 'not_inspected'
    """
    try:
        # All registered shoes
        shoes_r = _sb.table("collector_shoes") \
            .select("shoe_id, lrv_asset_id").execute()
        if not shoes_r.data:
            return {}

        # Latest defect records per asset (non-none)
        det_r = _sb.table("defect_records") \
            .select("confidence, defect_type, detected_at, inspection_sessions(asset_id)") \
            .not_.is_("confidence", "null") \
            .gt("confidence", 0) \
            .execute()

        # Build detection lookup: asset_id → list of (defect_type, confidence, detected_at)
        detections = {}
        if det_r.data:
            for row in det_r.data:
                sess = row.get("inspection_sessions")
                asset = sess.get("asset_id") if isinstance(sess, dict) else None
                if not asset:
                    continue
                detections.setdefault(asset, []).append({
                    "defect_type": row["defect_type"],
                    "confidence":  row["confidence"] * 100,
                    "detected_at": row["detected_at"],
                })

        # Group shoes by LRV
        lrv_map = {}
        for row in shoes_r.data:
            lrv = row["lrv_asset_id"]
            shoe = row["shoe_id"]
            lrv_map.setdefault(lrv, []).append(shoe)

        fleet = {}
        CRITICAL_DEFECTS    = {"wear", "crack"}
        ATTENTION_DEFECTS   = {"pore", "scratch", "scuff marks", "oxidation", "water mark"}

        for lrv, shoe_ids in lrv_map.items():
            all_dets = []
            for shoe in shoe_ids:
                all_dets.extend(detections.get(shoe, []))

            if not all_dets:
                fleet[lrv] = {
                    "shoes": shoe_ids,
                    "last_inspected": None,
                    "worst_defect": None,
                    "worst_confidence": None,
                    "status": "not_inspected",
                }
                continue

            # Most recent inspection
            last = max(all_dets, key=lambda x: x["detected_at"])["detected_at"]

            # Only non-none defects for severity
            real_dets = [d for d in all_dets if d["defect_type"] != "none"]

            if not real_dets:
                fleet[lrv] = {
                    "shoes": shoe_ids,
                    "last_inspected": last,
                    "worst_defect": "none",
                    "worst_confidence": None,
                    "status": "operational",
                }
                continue

            # Worst = highest confidence non-none defect
            worst = max(real_dets, key=lambda x: x["confidence"])

            # Any non-none defect detected → monitor carefully
            status = "monitor_carefully"

            fleet[lrv] = {
                "shoes": shoe_ids,
                "last_inspected": last,
                "worst_defect": worst["defect_type"],
                "worst_confidence": round(worst["confidence"], 1),
                "status": status,
            }

        return fleet
    except Exception:
        return {}


def load_daily_selection(_sb):
    """Load today's LRV selection from daily_lrv_selection table."""
    from datetime import date
    try:
        r = _sb.table("daily_lrv_selection") \
            .select("*") \
            .eq("date", date.today().isoformat()) \
            .limit(1).execute()
        return r.data[0] if r.data else None
    except Exception:
        return None


def save_daily_selection(_sb, lrv_ids, set_by, is_override=False):
    """Insert or update today's LRV selection."""
    from datetime import date, datetime, timezone
    today = date.today().isoformat()
    payload = {
        "date":    today,
        "lrv_ids": lrv_ids,
        "set_by":  set_by,
        "set_at":  datetime.now(timezone.utc).isoformat(),
    }
    try:
        if is_override:
            _sb.table("daily_lrv_selection").update(payload).eq("date", today).execute()
        else:
            _sb.table("daily_lrv_selection").insert(payload).execute()
        return True
    except Exception as e:
        return str(e)


def _show_lrv_selector(supabase, fleet, existing, is_override=False):
    """
    Renders the LRV selector prompt.
    existing: the current daily_lrv_selection row (or None)
    is_override: True when management is overriding an existing selection
    """
    st.markdown(
        '<div class="section-header">🚃 Set Today\'s LRV Schedule</div>',
        unsafe_allow_html=True,
    )
    if is_override:
        st.info("✏️ You are overriding today's LRV schedule as management.")

    # Name input
    default_name = existing["set_by"] if existing and is_override else ""
    tech_name = st.text_input(
        "Your name",
        value=default_name,
        placeholder="e.g. Rizwan",
        key="lrv_sel_name",
    )

    # LRV multiselect — all registered LRVs
    all_lrvs = sorted(fleet.keys()) if fleet else []
    default_sel = existing["lrv_ids"] if existing and is_override else []

    st.markdown("**Select LRVs in service today (max 8):**")
    selected = st.multiselect(
        "LRVs",
        options=all_lrvs,
        default=[l for l in default_sel if l in all_lrvs],
        key="lrv_sel_multiselect",
        label_visibility="collapsed",
    )

    if len(selected) > 8:
        st.warning("⚠️ Maximum 8 LRVs allowed. Please deselect some.")

    btn_label = "✏️ Override Schedule" if is_override else "✅ Confirm Schedule"
    if st.button(btn_label, type="primary", disabled=(not tech_name.strip() or len(selected) == 0 or len(selected) > 8)):
        result = save_daily_selection(
            supabase, selected, tech_name.strip(), is_override=is_override
        )
        if result is True:
            st.session_state.pop("lrv_sel_override", None)
            load_daily_selection.clear() if hasattr(load_daily_selection, "clear") else None
            st.session_state["cs_active_tab"] = 0
            st.rerun()
        else:
            st.error(f"Could not save selection: {result}")


def _show_fleet_status(fleet, shoes_df, daily_sel, supabase):
    """Renders the Fleet Status badge row + summary table above shoe cards."""

    STATUS_CONF = {
        "monitor_carefully": ("🟡", "Monitor Carefully", "#FEF9C3", "#CA8A04", "#92400E"),
        "operational":       ("🟢", "Operational",       "#DCFCE7", "#16A34A", "#14532D"),
        "not_inspected":     ("⚪", "Not Inspected",     "#F1F5F9", "#64748B", "#334155"),
    }

    # ── Header + lock/override ─────────────────────────────────
    role = st.session_state.get("role", None)
    h1, h2 = st.columns([5, 1])
    with h1:
        if daily_sel:
            try:
                from datetime import datetime, timezone, timedelta
                dt = datetime.fromisoformat(daily_sel["set_at"].replace("Z", "+00:00"))
                sgt = dt + timedelta(hours=8)
                local_time = sgt.strftime("%d %b %Y %H:%M SGT")
            except Exception:
                local_time = daily_sel.get("set_at", "")[:16]
            st.markdown(
                f'<div class="section-header">🚃 Fleet Status &nbsp; '
                f'<span style="font-size:12px;font-weight:400;color:#64748B;">'
                f'🔒 Set by <b>{daily_sel["set_by"]}</b> · {local_time}</span></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="section-header">🚃 Fleet Status</div>', unsafe_allow_html=True)
    with h2:
        if daily_sel and role in ("management", "supervisor"):
            if st.button("✏️ Override", key="fleet_override_btn"):
                st.session_state["lrv_sel_override"] = True
                st.session_state["cs_active_tab"] = 0
                st.rerun()

    # ── If no selection today → show selector prompt ───────────
    if not daily_sel or st.session_state.get("lrv_sel_override", False):
        _show_lrv_selector(supabase, fleet, daily_sel,
                           is_override=bool(st.session_state.get("lrv_sel_override")))
        return

    if not fleet:
        st.info("📭 No LRVs registered yet.")
        return

    # Filter fleet to only today's selected LRVs
    selected_lrvs = daily_sel.get("lrv_ids") or []
    fleet = {k: v for k, v in fleet.items() if k in selected_lrvs}

    # Sort: monitor_carefully first, then operational, not_inspected
    order = {"monitor_carefully": 0, "operational": 1, "not_inspected": 2}
    sorted_lrvs = sorted(fleet.keys(), key=lambda x: order.get(fleet[x]["status"], 9))

    # Active filter from session state
    active_filter = st.session_state.get("fleet_filter_lrv", None)

    # Badge row
    cols = st.columns(min(len(sorted_lrvs), 6))
    for i, lrv in enumerate(sorted_lrvs):
        info = fleet[lrv]
        emoji, label, bg, border, text = STATUS_CONF[info["status"]]
        is_active = active_filter == lrv
        badge_bg     = border if is_active else bg
        badge_text   = "white" if is_active else text
        badge_border = border

        with cols[i % 6]:
            st.markdown(
                f"""<div style="background:{badge_bg};border:2px solid {badge_border};
                border-radius:10px;padding:8px 10px;text-align:center;margin-bottom:6px;">
                <div style="font-size:18px;">{emoji}</div>
                <div style="font-size:11px;font-weight:700;color:{badge_text};">{lrv}</div>
                <div style="font-size:10px;color:{badge_text};opacity:0.85;">{label}</div>
                </div>""",
                unsafe_allow_html=True,
            )
            btn_label = "✕ Clear" if is_active else "Filter"
            if st.button(btn_label, key=f"fleet_badge_{lrv}", use_container_width=True):
                if is_active:
                    st.session_state.pop("fleet_filter_lrv", None)
                else:
                    st.session_state["fleet_filter_lrv"] = lrv
                st.session_state["cs_active_tab"] = 0
                st.rerun()

    # Fleet summary table
    with st.expander("📋 Fleet Summary Table", expanded=True):
        rows = []
        for lrv in sorted_lrvs:
            info = fleet[lrv]
            emoji, label, _, _, _ = STATUS_CONF[info["status"]]
            last = "Never"
            if info["last_inspected"]:
                try:
                    from datetime import datetime, timezone, timedelta
                    dt = datetime.fromisoformat(info["last_inspected"].replace("Z", "+00:00"))
                    sgt = dt + timedelta(hours=8)
                    diff = datetime.now(timezone.utc) - dt
                    days = diff.days
                    date_str = sgt.strftime("%d-%m-%Y")
                    last = f"Today ({date_str})" if days == 0 else f"{days}d ago ({date_str})"
                except Exception:
                    last = info["last_inspected"][:10]

            defect_str = "—" if not info["worst_defect"] or info["worst_defect"] == "none" else \
                info["worst_defect"]

            rows.append({
                "LRV":              lrv,
                "Shoes Registered": len(info["shoes"]),
                "Last Inspection":  last,
                "Worst Defect":     defect_str,
                "Status":           f"{emoji} {label}",
            })

        import pandas as _pd
        st.dataframe(
            _pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()


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


def _show_inspection_comparison(supabase):
    """
    Side-by-side inspection image comparison per shoe.
    Lazy-loaded — images are only fetched when the user opens an expander.
    Default view: most recent vs second-most-recent session per shoe.
    Advanced: user can pick any two sessions to compare.
    """
    from datetime import timedelta

    st.markdown('<div class="section-header">🔍 Inspection Comparison</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-intro">Compare annotated images between any two inspection sessions per shoe. '
        'By default shows the latest vs previous session. Images are loaded only when you open a shoe.</div>',
        unsafe_allow_html=True,
    )

    # ── Load session metadata only (no images yet) ────────────────
    # Only sessions that have at least one detection record
    try:
        det_resp = supabase.table("defect_records") \
            .select("session_id") \
            .execute()
        det_rows = det_resp.data or []
        valid_session_ids = list({r["session_id"] for r in det_rows if r.get("session_id")})
    except Exception as e:
        st.error(f"Could not load detection records: {e}")
        return

    if not valid_session_ids:
        st.info("📭 No inspection sessions with detections found.")
        return

    try:
        resp = supabase.table("inspection_sessions") \
            .select("id, asset_id, started_at, technician_name") \
            .in_("id", valid_session_ids) \
            .order("started_at", desc=True) \
            .execute()
        sessions = resp.data or []
    except Exception as e:
        st.error(f"Could not load inspection sessions: {e}")
        return

    if not sessions:
        st.info("📭 No inspection sessions found.")
        return

    # Group sessions by shoe
    from collections import defaultdict
    shoe_sessions: dict = defaultdict(list)
    for s in sessions:
        shoe_sessions[s["asset_id"]].append(s)

    shoes = sorted(shoe_sessions.keys())
    if not shoes:
        st.info("📭 No shoes with inspection data.")
        return

    shoe_sel = st.selectbox("Select shoe", shoes, key="ic_shoe_sel")
    this_shoe_sessions = shoe_sessions[shoe_sel]  # already sorted desc by started_at

    if len(this_shoe_sessions) < 2:
        st.info("⚠️ At least 2 inspection sessions are needed to compare. Only 1 session found for this shoe.")
        return

    # ── Session picker ─────────────────────────────────────────────
    def _fmt_session(s):
        try:
            dt = datetime.fromisoformat(s["started_at"].replace("Z", "+00:00"))
            sgt = dt + timedelta(hours=8)
            return sgt.strftime("%d %b %Y %H:%M") + f" — {s['technician_name'] or 'Unknown'}"
        except Exception:
            return s["id"][:8]

    session_labels = [_fmt_session(s) for s in this_shoe_sessions]
    session_ids    = [s["id"] for s in this_shoe_sessions]

    col_a, col_b = st.columns(2)
    with col_a:
        st.caption("**Previous inspection**")
        prev_idx = st.selectbox(
            "Previous", options=range(len(session_labels)),
            format_func=lambda i: session_labels[i],
            index=1,  # default: second-most-recent
            key="ic_prev_sel",
        )
    with col_b:
        st.caption("**Current inspection**")
        curr_idx = st.selectbox(
            "Current", options=range(len(session_labels)),
            format_func=lambda i: session_labels[i],
            index=0,  # default: most recent
            key="ic_curr_sel",
        )

    if prev_idx == curr_idx:
        st.warning("Please select two different sessions to compare.")
        return

    prev_session_id = session_ids[prev_idx]
    curr_session_id = session_ids[curr_idx]

    # ── Lazy load: fetch detection data only when user triggers compare ──
    with st.expander("🔍 Load Comparison", expanded=False):
        try:
            def _get_session_captures(session_id):
                """
                Returns unique captures for a session.
                Each capture = one unique annotated_image_path with its defects grouped.
                """
                r = supabase.table("defect_records") \
                    .select("defect_type, confidence, annotated_image_path, raw_image_path, detected_at") \
                    .eq("session_id", session_id) \
                    .order("detected_at") \
                    .execute()
                rows = r.data or []
                if not rows:
                    return []
                # Deduplicate by annotated_image_path — group defects per image
                seen = {}
                for row in rows:
                    path = row.get("annotated_image_path") or row.get("raw_image_path") or ""
                    if path not in seen:
                        seen[path] = {"path": path, "detected_at": row["detected_at"], "defects": []}
                    seen[path]["defects"].append({
                        "defect_type": row["defect_type"],
                        "confidence":  row["confidence"],
                    })
                return list(seen.values())

            def _signed_url_ic(path, bucket="annotated-photos", expires=120):
                if not path:
                    return None
                try:
                    r = supabase.storage.from_(bucket).create_signed_url(path, expires)
                    return r.get("signedURL") or r.get("signedUrl") or None
                except Exception:
                    return None

            prev_captures = _get_session_captures(prev_session_id)
            curr_captures = _get_session_captures(curr_session_id)

            def _render_session_captures(captures, label, sess_label):
                st.markdown(f"**{label}**  \n<span style='font-size:12px;color:#64748B;'>{sess_label}</span>", unsafe_allow_html=True)
                if not captures:
                    st.info("No images found for this session.")
                    return
                for i, cap in enumerate(captures):
                    if len(captures) > 1:
                        st.caption(f"Angle {i+1} of {len(captures)}")
                    img_url = _signed_url_ic(cap["path"])
                    if img_url:
                        st.image(img_url, width="stretch")
                    else:
                        st.warning("Image not available.")
                    # List all defects detected in this image
                    non_none = [d for d in cap["defects"] if d["defect_type"] != "none"]
                    if non_none:
                        for d in sorted(non_none, key=lambda x: x["confidence"], reverse=True):
                            st.markdown(f"⚠️ **{d['defect_type']}** — {d['confidence']:.0%}")
                    else:
                        st.success("✅ No defect detected")
                    try:
                        dt  = datetime.fromisoformat(cap["detected_at"].replace("Z", "+00:00"))
                        sgt = dt + timedelta(hours=8)
                        st.caption(sgt.strftime("%d %b %Y %H:%M SGT"))
                    except Exception:
                        pass

            left_col, right_col = st.columns(2)
            with left_col:
                _render_session_captures(prev_captures, "Previous", session_labels[prev_idx])
            with right_col:
                _render_session_captures(curr_captures, "Current", session_labels[curr_idx])

        except Exception as e:
            st.error(f"Could not load comparison data: {e}")


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


# ──────────────────────────────────────────────────────────────────────────────
# Last Inspected Summary (Tab 1)
# ──────────────────────────────────────────────────────────────────────────────
def _show_last_inspected_summary(supabase):
    st.markdown('<div class="section-header">Last Inspected — Per Shoe</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-intro">Shows when each registered shoe was last captured by the camera station. '
        'Shoes not inspected in the last 7 days are flagged so nothing gets overlooked.</div>',
        unsafe_allow_html=True,
    )
    try:
        # inspection_sessions has asset_id (= shoe_id) and created_at
        rows = (
            supabase.table("inspection_sessions")
            .select("asset_id, created_at")
            .order("created_at", desc=True)
            .execute()
            .data
        )
        if not rows:
            st.info("No inspection records found yet.")
            return

        df = pd.DataFrame(rows)
        df["created_at"] = pd.to_datetime(df["created_at"], utc=True)

        # Keep only the most recent session per shoe
        latest = (
            df.sort_values("created_at", ascending=False)
            .groupby("asset_id", as_index=False)
            .first()
        )

        now = pd.Timestamp.now(tz="UTC")
        latest["days_ago"] = (now - latest["created_at"]).dt.days
        latest["last_inspected"] = (
            latest["created_at"]
            .dt.tz_convert("Asia/Singapore")
            .dt.strftime("%d %b %Y  %H:%M")
        )
        latest = latest.sort_values("asset_id")

        cols = st.columns(4)
        for idx, row in latest.reset_index(drop=True).iterrows():
            days = int(row["days_ago"])
            if days == 0:
                badge_color, badge_text = "#16A34A", "Today"
            elif days <= 3:
                badge_color, badge_text = "#2563EB", f"{days}d ago"
            elif days <= 7:
                badge_color, badge_text = "#D97706", f"{days}d ago"
            else:
                badge_color, badge_text = "#DC2626", f"{days}d ago ⚠️"

            with cols[idx % 4]:
                st.markdown(
                    f"""<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;
                        padding:14px 12px;margin-bottom:10px;text-align:center;">
                        <div style="font-size:13px;font-weight:700;color:#1E3A5F;margin-bottom:6px;">
                            {row['asset_id']}
                        </div>
                        <div style="display:inline-block;background:{badge_color};color:white;
                            border-radius:12px;padding:3px 10px;font-size:12px;font-weight:600;
                            margin-bottom:6px;">{badge_text}</div>
                        <div style="font-size:11px;color:#64748B;">{row['last_inspected']}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )

    except Exception as e:
        st.error(f"Could not load last inspected summary: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Defect Type Breakdown per Shoe (Tab 2)
# ──────────────────────────────────────────────────────────────────────────────
def _show_defect_breakdown_per_shoe(supabase):
    st.markdown('<div class="section-header">Defect Type Breakdown — Per Shoe</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-intro">Counts of each defect class detected per shoe across all inspections. '
        'Helps identify which shoe has the most varied or concentrated defect profile.</div>',
        unsafe_allow_html=True,
    )
    try:
        # Join defect_records → inspection_sessions to get asset_id (shoe_id)
        rows = (
            supabase.table("defect_records")
            .select("defect_type, inspection_sessions(asset_id)")
            .neq("defect_type", "none")
            .execute()
            .data
        )
        if not rows:
            st.info("No defect records found yet.")
            return

        # Flatten the nested join
        flat = []
        for r in rows:
            sess = r.get("inspection_sessions") or {}
            asset_id = sess.get("asset_id")
            if asset_id:
                flat.append({"shoe_id": asset_id, "defect_type": r["defect_type"]})

        if not flat:
            st.info("No defect records linked to shoes yet.")
            return

        df = pd.DataFrame(flat)
        pivot = (
            df.groupby(["shoe_id", "defect_type"])
            .size()
            .reset_index(name="count")
        )

        shoes = sorted(pivot["shoe_id"].unique())
        DEFECT_COLORS = {
            "wear":        "#E53E3E",
            "crack":       "#DD6B20",
            "pore":        "#D69E2E",
            "scratch":     "#38A169",
            "scuff marks": "#3182CE",
            "oxidation":   "#805AD5",
            "water mark":  "#319795",
        }

        # Summary cards row — top defect per shoe
        summary_cols = st.columns(len(shoes))
        for i, shoe in enumerate(shoes):
            sub = pivot[pivot["shoe_id"] == shoe].sort_values("count", ascending=False)
            top_def  = sub.iloc[0]["defect_type"] if not sub.empty else "—"
            top_cnt  = int(sub.iloc[0]["count"])  if not sub.empty else 0
            total    = int(sub["count"].sum())
            color    = DEFECT_COLORS.get(top_def, "#718096")
            with summary_cols[i]:
                st.markdown(
                    f"""<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;
                        padding:12px 10px;text-align:center;margin-bottom:10px;">
                        <div style="font-size:12px;font-weight:700;color:#1E3A5F;">{shoe}</div>
                        <div style="display:inline-block;background:{color};color:white;
                            border-radius:10px;padding:2px 9px;font-size:11px;font-weight:600;
                            margin:5px 0;">{top_def}</div>
                        <div style="font-size:11px;color:#475569;">{top_cnt} detections</div>
                        <div style="font-size:10px;color:#94A3B8;">{total} total defects</div>
                    </div>""",
                    unsafe_allow_html=True,
                )

        # Grouped bar chart — all shoes
        import plotly.graph_objects as go
        all_defect_types = sorted(pivot["defect_type"].unique())
        fig = go.Figure()
        for defect in all_defect_types:
            y_vals = []
            for shoe in shoes:
                row_val = pivot[(pivot["shoe_id"] == shoe) & (pivot["defect_type"] == defect)]
                y_vals.append(int(row_val["count"].values[0]) if not row_val.empty else 0)
            fig.add_trace(go.Bar(
                name=defect,
                x=shoes,
                y=y_vals,
                marker_color=DEFECT_COLORS.get(defect, "#A0AEC0"),
            ))

        fig.update_layout(
            barmode="group",
            height=340,
            margin=dict(l=10, r=10, t=10, b=30),
            paper_bgcolor="white",
            plot_bgcolor="white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(title="Shoe ID", tickfont=dict(size=11)),
            yaxis=dict(title="Detection Count", showgrid=True, gridcolor="#F1F5F9"),
        )
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Could not load defect breakdown: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Recent Inspection Sessions Log (Tab 3)
# ──────────────────────────────────────────────────────────────────────────────
def _show_recent_sessions_log(supabase):
    try:
        # inspection_sessions PK is "id"; shoe identifier is "asset_id";
        # technician is "technician_name"; no explicit "status" column assumed
        rows = (
            supabase.table("inspection_sessions")
            .select("id, asset_id, technician_name, created_at")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
            .data
        )
        if not rows:
            st.info("No inspection sessions recorded yet.")
            return

        sessions_df = pd.DataFrame(rows)
        sessions_df["created_at"] = pd.to_datetime(sessions_df["created_at"], utc=True)

        # Pull defect counts per session_id from defect_records
        defect_rows = (
            supabase.table("defect_records")
            .select("session_id, defect_type")
            .neq("defect_type", "none")
            .execute()
            .data
        )
        defect_counts = {}
        if defect_rows:
            for r in defect_rows:
                sid = r.get("session_id")
                if sid:
                    defect_counts[sid] = defect_counts.get(sid, 0) + 1

        sessions_df["defects_found"] = sessions_df["id"].map(
            lambda s: defect_counts.get(s, 0)
        )

        # Render as a clean table
        display_df = sessions_df[["asset_id", "technician_name", "created_at", "defects_found"]].copy()
        display_df.columns = ["Shoe ID", "Inspector", "Date & Time", "Defects Found"]
        display_df["Date & Time"] = display_df["Date & Time"].dt.strftime("%d %b %Y  %H:%M")

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Shoe ID":       st.column_config.TextColumn("Shoe ID", width="medium"),
                "Inspector":     st.column_config.TextColumn("Inspector", width="medium"),
                "Date & Time":   st.column_config.TextColumn("Date & Time", width="medium"),
                "Defects Found": st.column_config.NumberColumn("Defects Found", width="small"),
            },
        )
        st.caption(f"Showing last {len(display_df)} sessions · most recent first")

    except Exception as e:
        st.error(f"Could not load inspection sessions: {e}")


def show():
    _inject_css()
    st.markdown("## 👟 Collector Shoe Wear Tracking")

    # ── Persistent success message after registration ──────────
    if "reg_success_msg" in st.session_state:
        st.success(st.session_state.pop("reg_success_msg"))

    supabase  = get_supabase()
    shoes_df  = load_shoes(supabase)
    fleet     = load_fleet_status(supabase)
    daily_sel = load_daily_selection(supabase)

    # ── Weather banner — always above all tabs ─────────────────
    active_threshold = _show_weather_banner(supabase)

    st.divider()

    # ── Custom tab bar (persists across reruns via session_state) ─
    _TAB_LABELS = [
        "📊 Overview",
        "📈 Trends & Analysis",
        "🗃 Shoe Registry",
    ]
    if "cs_active_tab" not in st.session_state:
        st.session_state["cs_active_tab"] = 0

    # Render tab buttons
    _tab_cols = st.columns(len(_TAB_LABELS))
    for _i, _label in enumerate(_TAB_LABELS):
        _is_active = st.session_state["cs_active_tab"] == _i
        _btn_style = (
            "background:#1E3A5F;color:white;border:none;border-radius:8px 8px 0 0;"
            "padding:8px 0;font-weight:600;cursor:pointer;width:100%;"
        ) if _is_active else (
            "background:#E2E8F0;color:#475569;border:none;border-radius:8px 8px 0 0;"
            "padding:8px 0;font-weight:500;cursor:pointer;width:100%;"
        )
        if _tab_cols[_i].button(_label, key=f"_cs_tab_{_i}", use_container_width=True):
            st.session_state["cs_active_tab"] = _i
            st.rerun()

    st.markdown('<hr style="margin:0 0 16px 0;border-color:#CBD5E1;">', unsafe_allow_html=True)

    _active_tab_idx = st.session_state["cs_active_tab"]

    # Fake tab contexts using if/elif blocks
    _show_tab1 = (_active_tab_idx == 0)
    _show_tab2 = (_active_tab_idx == 1)
    _show_tab3 = (_active_tab_idx == 2)

    tab1 = _show_tab1
    tab2 = _show_tab2
    tab3 = _show_tab3

    # ══════════════════════════════════════════════════════════
    # TAB 1 — OVERVIEW
    # ══════════════════════════════════════════════════════════
    if tab1:
        # ── Fleet Status ───────────────────────────────────────
        _show_fleet_status(fleet, shoes_df, daily_sel, supabase)

        st.divider()

        # ── Last Inspected Summary ─────────────────────────────
        _show_last_inspected_summary(supabase)


    # ══════════════════════════════════════════════════════════
    # TAB 2 — TRENDS & ANALYSIS
    # ══════════════════════════════════════════════════════════
    if tab2:

        # ── YOLO Confidence Trend ──────────────────────────────
        st.markdown('<div class="section-header">Visual Wear Progression (YOLO Confidence Trend)</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-intro">Tracks YOLO detection confidence scores over time per shoe. A rising trend may indicate the defect is becoming more visually prominent. Not a direct measure of physical severity — always verify with a depth gauge.</div>', unsafe_allow_html=True)
        _show_confidence_progression(supabase)

        st.divider()

        # ── Defect Type Breakdown per Shoe ─────────────────────
        _show_defect_breakdown_per_shoe(supabase)

        st.divider()

        # ── Detection Frequency ────────────────────────────────
        _show_detection_frequency(supabase)

        st.divider()

        # ── Session Frequency ──────────────────────────────────
        _show_session_frequency(supabase)

        st.divider()

        # ── Per-LRV Defect Heatmap ─────────────────────────────
        _show_defect_heatmap(supabase)

        st.divider()

        # ── Inspection Image Comparison ────────────────────────
        _show_inspection_comparison(supabase)

    # ══════════════════════════════════════════════════════════
    # TAB 3 — SHOE REGISTRY
    # ══════════════════════════════════════════════════════════
    if tab3:
        # ── Registered shoes ───────────────────────────────────
        st.markdown('<div class="section-header">Registered Shoes</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-intro">All collector shoes currently registered in the system. Edit or delete records here.</div>', unsafe_allow_html=True)

        if not shoes_df.empty:
            ROTATION_OPTIONS = {
                "in_service":    "In Service — wear < 3mm (rainy) / < 4mm (dry), actively monitored",
                "not_rotated":   "Not Rotated — wear ≥ 3mm (rainy) / ≥ 4mm (dry), rotation pending",
                "rotated_once":  "Rotated Once — rotation performed, second side in use",
                "rotated_twice": "Rotated Twice — both sides worn, pending replacement",
                "retired":       "Retired — removed from service",
            }
            CONDITION_OPTIONS = {
                "new":    "new — Never installed, straight from storage",
                "in_use": "in_use — Currently in service",
                "old":    "old — Previously used, has visible wear",
                "unknown":"unknown — Condition not yet assessed",
            }

            for _, shoe in shoes_df.iterrows():
                shoe_id    = shoe["shoe_id"]
                condition  = shoe.get("condition", "unknown")
                baseline   = shoe.get("baseline_thickness_mm", 16.0)
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
                        if st.button("✏️ Edit", key=f"edit_btn_{shoe_id}", use_container_width=True):
                            st.session_state[f"edit_shoe_{shoe_id}"] = not st.session_state.get(f"edit_shoe_{shoe_id}", False)
                            st.session_state["cs_active_tab"] = 2
                            st.rerun()
                    with col3:
                        if st.button("🗑️ Delete", key=f"del_btn_{shoe_id}", use_container_width=True):
                            st.session_state[f"del_shoe_{shoe_id}"] = True
                            st.session_state["cs_active_tab"] = 2
                            st.rerun()

                    if st.session_state.get(f"edit_shoe_{shoe_id}", False):
                        with st.form(f"edit_form_{shoe_id}"):
                            st.markdown(f"**Editing: {shoe_id}**")
                            e1, e2 = st.columns(2)
                            cond_keys = list(CONDITION_OPTIONS.keys())
                            cond_vals = list(CONDITION_OPTIONS.values())
                            cond_idx  = cond_keys.index(condition) if condition in cond_keys else 0
                            new_condition = e1.selectbox("Condition", cond_vals, index=cond_idx)
                            new_condition = cond_keys[cond_vals.index(new_condition)]
                            new_baseline  = e2.number_input("Baseline Thickness (mm)", min_value=0.0, max_value=100.0, value=float(baseline), step=0.1)
                            rot_keys  = list(ROTATION_OPTIONS.keys())
                            rot_vals  = list(ROTATION_OPTIONS.values())
                            rot_idx   = rot_keys.index(rot_status) if rot_status in rot_keys else 0
                            new_rot   = st.selectbox("Rotation Status", rot_vals, index=rot_idx)
                            new_rot   = rot_keys[rot_vals.index(new_rot)]
                            new_notes = st.text_area("Notes", value=notes_val, height=60)
                            s1, s2 = st.columns(2)
                            if s1.form_submit_button("💾 Save Changes", type="primary"):
                                try:
                                    # Use RPC to avoid + being URL-encoded to %2B in shoe_id
                                    supabase.rpc("update_collector_shoe", {
                                        "p_shoe_id":        shoe_id,
                                        "p_condition":      new_condition,
                                        "p_baseline":       new_baseline,
                                        "p_rotation_status": new_rot,
                                        "p_notes":          new_notes.strip() or None,
                                    }).execute()
                                    st.session_state.pop(f"edit_shoe_{shoe_id}", None)
                                    st.success(f"✅ {shoe_id} updated!")
                                    load_shoes.clear()
                                    st.session_state["cs_active_tab"] = 2
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Update failed: {e}")
                            if s2.form_submit_button("Cancel"):
                                st.session_state.pop(f"edit_shoe_{shoe_id}", None)
                                st.session_state["cs_active_tab"] = 2
                                st.rerun()

                    if st.session_state.get(f"del_shoe_{shoe_id}", False):
                        st.warning(f"⚠️ Delete **{shoe_id}**? This cannot be undone.")
                        d1, d2 = st.columns(2)
                        with d1:
                            if st.button("✅ Yes, Delete", key=f"del_confirm_{shoe_id}", type="primary"):
                                try:
                                    # Use raw SQL via rpc to avoid + being URL-encoded to %2B
                                    result = supabase.rpc(
                                        "delete_collector_shoe",
                                        {"p_shoe_id": shoe_id}
                                    ).execute()
                                    st.session_state.pop(f"del_shoe_{shoe_id}", None)
                                    load_shoes.clear()
                                    st.session_state["cs_active_tab"] = 2
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Delete failed: {e}")
                        with d2:
                            if st.button("❌ Cancel", key=f"del_cancel_{shoe_id}"):
                                st.session_state.pop(f"del_shoe_{shoe_id}", None)
                                st.session_state["cs_active_tab"] = 2
                                st.rerun()
        else:
            st.info("📭 No shoes registered yet. Register a shoe via the Camera Station.")

        # ── Recent Inspection Sessions ──────────────────────────
        st.divider()
        st.markdown('<div class="section-header">Recent Inspection Sessions</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-intro">The last 20 inspection sessions logged by the camera station, including which shoe was inspected, who ran it, and what defects were found.</div>', unsafe_allow_html=True)
        _show_recent_sessions_log(supabase)
