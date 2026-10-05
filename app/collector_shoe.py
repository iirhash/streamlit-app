# app/collector_shoe.py
# ── Collector Shoe Wear Tracking — Redesigned ─────────────────

import streamlit as st
import streamlit.components.v1 as st_components
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
    Displays a weather banner at the top of the Shoe Health Monitor page showing:
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
def _shoe_card_html(shoe_id, days, last_inspected):
    """
    Returns the HTML snippet for one mini shoe card used in the LRV diagram.
    days=-1 means no inspection data (grey/unregistered).
    """
    if days == -1:
        badge_color = "#94A3B8"
        badge_text  = "Not inspected"
        border_color = "#CBD5E1"
        bg_color     = "#F8FAFC"
        text_color   = "#94A3B8"
        ts_html = ""
    else:
        if days == 0:
            badge_color, badge_text = "#16A34A", "Today"
        elif days <= 3:
            badge_color, badge_text = "#2563EB", f"{days}d ago"
        elif days <= 7:
            badge_color, badge_text = "#D97706", f"{days}d ago"
        else:
            badge_color, badge_text = "#DC2626", f"{days}d ago ⚠️"
        border_color = badge_color
        bg_color     = "#FFFFFF"
        text_color   = "#1E293B"
        ts_html = f'<div style="font-size:9px;color:#64748B;margin-top:3px;line-height:1.2;">{last_inspected}</div>'

    # Short position label (e.g. "+A1", "-A2")
    # shoe_id format: CS-LRV00-+A1  → split on "-", take from index 2 onward and rejoin
    # For negative shoes: CS-LRV00--A2 → parts = ['CS','LRV00','','A2'] so we detect empty part
    try:
        parts = shoe_id.split("-")
        # parts[0]="CS", parts[1]="LRV00", parts[2]="+A1" or "" (for negative), parts[3]="A2" (for negative)
        if len(parts) >= 4 and parts[2] == "":
            pos_label = "-" + parts[3]   # e.g. "-A2"
        else:
            pos_label = parts[2]         # e.g. "+A1"
    except Exception:
        pos_label = shoe_id

    return f"""<div style="
        background:{bg_color};
        border:2px solid {border_color};
        border-radius:8px;
        padding:6px 8px;
        text-align:center;
        min-width:90px;
        box-shadow:0 2px 6px rgba(0,0,0,0.10);
        font-family:system-ui,sans-serif;
    ">
        <div style="font-size:9px;font-weight:700;letter-spacing:1px;color:#64748B;text-transform:uppercase;">{pos_label}</div>
        <div style="font-size:10px;font-weight:600;color:{text_color};margin:2px 0;word-break:break-all;">{shoe_id}</div>
        <div style="display:inline-block;background:{badge_color};color:white;
            border-radius:10px;padding:2px 7px;font-size:9px;font-weight:700;">{badge_text}</div>
        {ts_html}
    </div>"""


def _lrv_diagram_html(lrv_id, shoe_data):
    """Corner-layout diagram using pre-drawn bracket image."""
    _IMG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAqkAAAFQCAYAAACcU+eLAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAAFiUAABYlAUlSJPAAAP+lSURBVHhe7H15vCVFdf+3uu97b/YZBpBFZRGURUQBTTQm4hqNRsWNzSXu0RiXJPpziYiCoqhxQdG4x6gYRRBRXAAFXBIVFNwXBEFUdpgZhpl5793u+v1xzqk6VV3Vt+97b5g32t/53Hndp85Wp5Y+Xb0Za61Fjx49evTo0aNHjx6LCEVM6NGjR48ePXr06NFjW6NPUnv06NGjR48ePXosOvRJao8ePXr06NGjR49Fhz5J7dGjR48ePXr06LHo0CepPXr06NGjR48ePRYd+iS1R48ePXr06NGjx6JDn6T26NGjR48ePXr0WHTok9QePXr06NGjR48eiw59ktqjR48ePXr06NFj0aFPUnv06NGjR48ePXosOvRJao8ePXr06NGjR49Fhz5J7dGjR48ePXr06LHo0CepPXr06NGjR48ePRYd+iS1R48ePXr06NGjx6JDn6T26NGjR48ePXr0WHTok9QePXr06NGjR48eiw59ktqjR48ePXr06NFj0aFPUnv06NGjR48ePXosOvRJao8ePXr06NGjR49Fhz5J7dGjR48ePXr06LHoYKy1NiYuJlx44YUxqUePOWG33XbDXe5yFyxfvjwu6tGjR48ePXosMiz6JPX1r3893vCGN8TkHj3mjD322AN77LEHnvSkJ+HYY4/Fne50p5ilR48ePRYl1q1bh6uuugrr1q2Li3r0mDce/OAHx6Rtij5J7fFnjV122QXHHnssnvGMZ+A+97lPXNyjR48e2xQ33HADTjvtNJxxxhm48sor8cc//jFm6dFjQXDBBRf0SWqPHtsKv/nNb3DppZfi0ksvxWWXXYZLL70U1113HQBgzZo1OP744/Gyl70sFuvRo0ePOxw/+clP8LGPfQynnXYarr/++ri4R48FR5+k9uixyPCKV7wCb3/7293+05/+dPz3f/93wNOjR48edyS++tWv4vnPfz6uueYaAMDatWuxzz77YN9998V+++2HAw88EDvvvHMs1qPHvNEnqT16LDKcffbZeP7zn+9WK57znOfgwx/+cMzWo0ePHlsdp5xyCl760pe6/ZNOOgmvfvWrA54ePf5c0CepPXownvOc5+CjH/0oAOAzn/kMjjzyyJilR48ePbYaHvnIR+Lcc88FAOy777747Gc/i0MOOSRm69Hjzwb9e1J79GB85CMfwd/93d8BAI466ih85zvfiVl69OjRY6vgFa94hUtQX/ziF+Pyyy/vE9Qef/boV1J79FDYuHEjVq5cCQC43/3uh+9///sxS48ePXosKM466yw84QlPAAAcfPDB+NGPfhSz9OjxZ4l+JbVHD4UVK1bgs5/9LADg4osvxplnnhmz9OjRo8eC4qSTTnLbX//614OyHj3+nNEnqT16RHjKU56CZz3rWQCA0047LS7u0aNHjwXDmWeeiYsvvhgA8La3vQ077bRTzNKjx58t+iS1R48EHvKQhwAAzjjjDFxyySVxcY8ePXosCORE+OlPfzpe/vKXx8U9evxZo09Se/RI4LDDDnPbv/jFL4KyHj169FgIXHLJJTjjjDMAfrK/R48eIfoktUePBA488EDssssuAIArrrgiLu7Ro0ePeePyyy932/2T/D16NNEnqT16ZHCf+9wHAHD11VfHRT169Ogxb/z+978H+ItSBx54YFzco8efPfoktUePDO5///sDAK666qq4qEePHj3mDZlb+lXUHj3S6JPUHj169OjRYxvgyiuvBNRVmx49eoTok9QePXr06NFjG2DLli0Av5+5R48eTfRJao8ePXr06NGjR49Fhz5J7dGjR48ePXr06LHosOiTVGvlZ/mnt/tf/9t6v7AfNsv730L9UuO8y29c/j/3XyZeSNAC/oxc9jcu/0L9tpVd/evaj4mvn2P+lH7bcxv6OXixwVi7GN3yqGuLuqoBAM5RE7psLAATkAAAFnEB71vAGK/QwjJbxGuJSbRYGBjH69XRthGmCESwzmdDIjbhsNMttsWwKDZB3S2sF4Hxul05BYc9UO4Z4hRVQZis8hU+XoFm+HqBG4D9dVxBLKLAOP6IzvuBO2ERlalCY03QQo7Xxce4tqY/rpBP0VjGRm1kDU488QSceOKJOPzww3HeeedzmffX8TfiI9u6fpY8ck2oeTR0PLi+AWUUYu4o7rShyJo/tB24zwSJtidJDLweHYuAO9GvKNa8zzx+PGb4ZR/EQ1wJGedTHBMB83pVEVKxoaAYA+pL8fTpJpZEGYNKmQexeyJHerwGvxX0NaPsuHqwHA8UY9UY5rFnTe37rx6/blzy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B6k97tH4yU9+gic96Un4q7/6K0f7zne+g4WFhYCvR48ePbY3dt55Z3zjG99w509+8pPx8pe/HNdcc03A16PHPQX94/4e9zhs3rwZ3//+93HhhRfibW97G6699loAwOGHH44zzjgDe+yxRyzSo0ePHncabrrpJvzRH/0RPv/5zwP8VaqXvOQleMADHoCHPOQh2G233WKRHj3ulljzg9STTjopJvXoMRV+9rOf4cILL8Qll1wS0Ofm5nDiiSfi7W9/e0Dv0aNHj7sSr371q/GOd7wDW7ZsCeiHHHIIDj/8cNz//vcP6D16rARHH300jj766Jh8l2KHGKSefPLJMblHjxXj4IMPxrOe9SyccMIJ/Vv8PXr0WJP46U9/itNOOw0f+9jHcOmll8bJPXqsGs4777x+kDopTjrpJHzlK1+JyT16TIy99toLBx54IPbZZx/ss88+OOaYY/qN+nv06LFDYOvWrTjrrLNw+eWX44orrsAvf/lLbNy4MWbr0WNqvP71r+8HqT169OjRo0ePHj16jEP/dn+PHj169OjRo0ePNYd+kNqjR48ePXr06NFjzaEfpPbo0aNHjx49evRYc+gHqT169OjRo0ePHj3WHPpBao8ePXr06NGjR481h36Q2qNHjx49evTo0WPNoR+k9ujRo0ePHj169Fhz6AepPXr06NGjR48ePdYc+kFqjx49evTo0aNHjzWHfpDao0ePHj169OjRY82hH6T26NGjR48ePXr0WHPoB6k9evTo0aNHjx491hz6QWqPHj169OjRo0ePNYd+kNqjR48ePXr06NFjzaEfpPbo0aNHjx49evRYc+gHqT169OjRo0ePHj3WHPpBao8ePXr06NGjR481h36Q2qNHjx49evTo0WPNoR+k9ujRo0ePHj169Fhz6AepPXr06NGjR48ePdYc+kFqjx49evTo0aNHjzWHfpDao0ePHj169OjRY82hH6T26NGjR48ePXr0WHPoB6k9evTo0aNHjx491hz6QWqPHj169OjRo0ePNYd+kNqjR48ePXr06NFjzaEfpPbo0aNHjx49evRYc+gHqT169OjRo0ePHj3WHPpBao8ePXr06NGjR481h36Q2qNHjx49evTo0WPN4f8Hfzqq2fvLTrkAAAAASUVORK5CYII="

    def _card(pos):
        info = shoe_data.get(pos, {})
        sid  = info.get("shoe_id", "CS-" + lrv_id + "-" + pos)
        days = info.get("days", -1)
        ts   = info.get("last_inspected", "")
        return _shoe_card_html(sid, days, ts)

    def _pair(p1, p2):
        return (
            '<div style="display:flex;flex-direction:column;gap:6px;">'
            + _card(p1) + _card(p2) + '</div>'
        )

    lbl = 'style="font-size:9px;font-weight:700;letter-spacing:1px;color:#64748B;text-transform:uppercase;margin-bottom:4px;"'

    # Fixed px positions so cards don't shift when image size changes.
    # 22% of 380px = 84px (POS 1/3), 78% of 380px = 296px (POS 2/4)
    def _corner(pos_label, p1, p2, align):
        top_px = "84px" if pos_label in ("POS 1", "POS 3") else "296px"
        alg = "flex-start" if align == "left" else "flex-end"
        side = "left:0;" if align == "left" else "right:0;"
        return (
            '<div style="position:absolute;top:' + top_px + ';transform:translateY(-50%);'
            + side +
            'display:flex;flex-direction:column;align-items:' + alg + ';">'
            '<div ' + lbl + '>' + pos_label + '</div>'
            + _pair(p1, p2) +
            '</div>'
        )

    lrv_badge = (
        '<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);'
        'background:rgba(255,255,255,0.85);border-radius:6px;padding:2px 10px;'
        'font-size:12px;font-weight:700;font-family:monospace;color:#1E293B;'
        'border:1px solid #CBD5E1;pointer-events:none;">' + lrv_id + '</div>'
    )

    title = (
        '<div style="font-size:12px;font-weight:700;letter-spacing:1.5px;color:#475569;'
        'text-transform:uppercase;text-align:center;margin-bottom:10px;">'
        + lrv_id + ' — TOP-DOWN VIEW</div>'
    )

    rail_legend = (
        '<div style="display:flex;gap:16px;justify-content:center;margin-top:10px;'
        'font-size:10px;color:#94A3B8;">'
        '<span>&#43; Upper shoe</span><span>&#8722; Lower shoe</span></div>'
    )

    # Image container is position:relative so the side card wrappers can use
    # position:absolute to sit exactly at the line-end vertical positions.
    img_wrap = (
        '<div style="position:relative;height:380px;display:flex;align-items:center;">'
        + '<img src="' + _IMG + '" alt="LRV ' + lrv_id + '" style="width:100%;display:block;"/>'
        + lrv_badge
        + '<div style="position:absolute;top:0;left:-148px;width:144px;height:100%;">'
        + _corner("POS 1", "+A1", "-A1", "left")
        + _corner("POS 2", "+A2", "-A2", "left")
        + '</div>'
        + '<div style="position:absolute;top:0;right:-148px;width:144px;height:100%;">'
        + _corner("POS 3", "+B3", "-B3", "right")
        + _corner("POS 4", "+B4", "-B4", "right")
        + '</div>'
        + '</div>'
    )

    grid = (
        '<div style="padding:0 152px;box-sizing:border-box;">'
        + img_wrap
        + '</div>'
    )

    card = (
        '<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;'
        'padding:12px;box-shadow:0 2px 8px rgba(0,0,0,0.07);'
        'overflow:visible;contain:none;">'
        + title + grid + rail_legend + '</div>'
    )

    # Scale JS: design canvas is 900px wide. Scales to fit iframe, reports height.
    scale_and_resize_js = (
        '<script>(function(){'
        'var DESIGN_W=900;'
        'var wrap=document.getElementById("diagram-wrap");'
        'function fit(){'
        # Reset transform first to measure true unscaled height
        'wrap.style.transform="none";'
        'wrap.style.width=DESIGN_W+"px";'
        'var unscaledH=wrap.scrollHeight;'
        'var aw=document.documentElement.clientWidth||document.body.clientWidth||DESIGN_W;'
        'var sc=Math.min(1,aw/DESIGN_W);'  # never scale UP, only DOWN
        'wrap.style.transform="scale("+sc+")";'
        'wrap.style.transformOrigin="top left";'
        'var scaledH=Math.ceil(unscaledH*sc);'
        'document.body.style.height=scaledH+"px";'
        'window.parent.postMessage({type:"streamlit:setFrameHeight",height:scaledH},"*");'
        '}'
        'window.addEventListener("load",function(){setTimeout(fit,100);});'
        'window.addEventListener("resize",function(){setTimeout(fit,50);});'
        'if(window.ResizeObserver){'
        'new ResizeObserver(function(){setTimeout(fit,50);}).observe(document.documentElement);'
        '}'
        'setTimeout(fit,150);'
        '})()</script>'
    )

    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<style>'
        '*{box-sizing:border-box;margin:0;padding:0;'
        'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}'
        'html,body{background:transparent;padding:0;margin:0;overflow:visible;}'
        '#diagram-wrap{'
        'width:900px;transform-origin:top left;'
        'overflow:visible;'
        '}'
        '</style>'
        '</head><body>'
        '<div id="diagram-wrap">' + card + '</div>'
        + scale_and_resize_js + '</body></html>'
    )


def _show_last_inspected_summary(supabase):
    st.markdown('<div class="section-header">Last Inspected — Per Shoe</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-intro">Physical layout of each LRV showing when each collector shoe was last '
        'inspected. Cards are positioned at their actual bogie locations — A End (left) positions 1 & 2, '
        'B End (right) positions 3 & 4. Upper shoe (+) shown above vehicle, lower shoe (−) below.</div>',
        unsafe_allow_html=True,
    )
    try:
        # ── Registered shoes ───────────────────────────────────
        registered = (
            supabase.table("collector_shoes")
            .select("shoe_id, lrv_asset_id")
            .execute()
            .data
        )
        if not registered:
            st.info("No collector shoes registered yet.")
            return

        registered_ids = {r["shoe_id"] for r in registered}

        # Group shoe_ids by LRV
        from collections import defaultdict
        lrv_shoes: dict = defaultdict(list)
        for r in registered:
            lrv_shoes[r["lrv_asset_id"]].append(r["shoe_id"])

        # ── Latest inspection per shoe ─────────────────────────
        rows = (
            supabase.table("inspection_sessions")
            .select("asset_id, created_at")
            .order("created_at", desc=True)
            .execute()
            .data
        )

        # Build lookup: shoe_id → {days, last_inspected}
        shoe_latest: dict = {}
        if rows:
            df = pd.DataFrame(rows)
            df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
            df = df[df["asset_id"].isin(registered_ids)]
            if not df.empty:
                latest = (
                    df.sort_values("created_at", ascending=False)
                    .groupby("asset_id", as_index=False)
                    .first()
                )
                now = pd.Timestamp.now(tz="UTC")
                latest["days_ago"] = (now - latest["created_at"]).dt.days
                latest["ts_sgt"] = (
                    latest["created_at"]
                    .dt.tz_convert("Asia/Singapore")
                    .dt.strftime("%d %b %Y %H:%M")
                )
                for _, row in latest.iterrows():
                    shoe_latest[row["asset_id"]] = {
                        "days": int(row["days_ago"]),
                        "last_inspected": row["ts_sgt"],
                    }

        # ── Render one diagram per LRV ─────────────────────────
        # All 8 possible position suffixes
        ALL_POS = ["+A1", "-A1", "+A2", "-A2", "+B3", "-B3", "+B4", "-B4"]

        sorted_lrvs = sorted(lrv_shoes.keys())

        # Legend
        st.markdown("""
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px;font-size:11px;">
          <span style="background:#16A34A;color:white;padding:3px 10px;border-radius:10px;font-weight:600;">Today</span>
          <span style="background:#2563EB;color:white;padding:3px 10px;border-radius:10px;font-weight:600;">≤ 3d ago</span>
          <span style="background:#D97706;color:white;padding:3px 10px;border-radius:10px;font-weight:600;">≤ 7d ago</span>
          <span style="background:#DC2626;color:white;padding:3px 10px;border-radius:10px;font-weight:600;">&gt; 7d ⚠️</span>
          <span style="background:#94A3B8;color:white;padding:3px 10px;border-radius:10px;font-weight:600;">Not inspected</span>
        </div>
        """, unsafe_allow_html=True)

        for lrv_id in sorted_lrvs:
            shoe_ids = lrv_shoes[lrv_id]

            # Build shoe_data dict keyed by position suffix
            shoe_data = {}
            for sid in shoe_ids:
                # Extract position suffix from shoe_id: "CS-LRV00-+A1" → "+A1"
                try:
                    prefix = f"CS-{lrv_id}-"
                    pos = sid[len(prefix):]
                except Exception:
                    pos = sid[-3:]
                info = shoe_latest.get(sid, {})
                shoe_data[pos] = {
                    "shoe_id": sid,
                    "days": info.get("days", -1),
                    "last_inspected": info.get("last_inspected", ""),
                }

            # Use st_components.html() to avoid st.markdown() truncation on large base64 payloads
            html_content = _lrv_diagram_html(lrv_id, shoe_data)
            # Initial height is a fallback; the JS inside resizes to actual content height
            st_components.html(html_content, height=500, scrolling=False)

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
    st.markdown("## 👟 Shoe Health Monitor")

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
        if st.button("🔄 Refresh Registry", key="refresh_registry"):
            load_shoes.clear()
            load_fleet_status.clear()
            st.session_state["cs_active_tab"] = 2
            st.rerun()
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
