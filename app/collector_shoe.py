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

    # Short position label (e.g. "+A1")
    try:
        pos_label = shoe_id.split("-")[-1]   # "+A1", "-B3", etc.
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
    """
    Renders one LRV top-down diagram.
    Left column:  Pos1 (top) and Pos2 (bottom) — each a +/- stacked pair
    Right column: Pos3 (top) and Pos4 (bottom) — each a +/- stacked pair
    SVG arrows overlay from bogie centre → card side.
    """
    # Embedded technical drawing (data URI injected at build time)
    _IMG = "data:image/png;base64,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"

    def _card(pos):
        info = shoe_data.get(pos, {})
        sid  = info.get("shoe_id", "CS-" + lrv_id + "-" + pos)
        days = info.get("days", -1)
        ts   = info.get("last_inspected", "")
        return _shoe_card_html(sid, days, ts)

    def _pos_label(text):
        return (
            '<div style="font-size:9px;color:#94A3B8;font-weight:600;'
            'text-align:center;letter-spacing:0.8px;text-transform:uppercase;'
            'margin-bottom:3px;">' + text + '</div>'
        )

    def _pair(pos_plus, pos_minus, label):
        return (
            '<div style="margin-bottom:6px;">'
            + _pos_label(label)
            + '<div style="display:flex;flex-direction:column;gap:4px;align-items:center;">'
            + _card(pos_plus)
            + _card(pos_minus)
            + '</div></div>'
        )

    # Left column: Pos 1 (top) + Pos 2 (bottom)
    left_col = (
        '<div style="display:flex;flex-direction:column;flex-shrink:0;min-width:105px;">'
        + _pair("+A1", "-A1", "Pos 1")
        + _pair("+A2", "-A2", "Pos 2")
        + '</div>'
    )

    # Right column: Pos 3 (top) + Pos 4 (bottom)
    right_col = (
        '<div style="display:flex;flex-direction:column;flex-shrink:0;min-width:105px;">'
        + _pair("+B3", "-B3", "Pos 3")
        + _pair("+B4", "-B4", "Pos 4")
        + '</div>'
    )

    # SVG overlay — arrows from bogie centres (% coords) to card edges
    # viewBox="0 0 100 100" preserveAspectRatio="none" → coords are % of image
    # Bogie centres (from 751×311 image):
    #   Pos1 top-left:     20.6%, 41.8%
    #   Pos2 bottom-left:  20.6%, 62.7%
    #   Pos3 top-right:    79.4%, 41.8%
    #   Pos4 bottom-right: 79.4%, 62.7%
    # Unique marker IDs per LRV to avoid DOM conflicts when multiple diagrams render
    _mid = lrv_id.replace("-", "").lower()
    _ah  = "ah-"  + _mid
    _ah2 = "ah2-" + _mid
    arrow_svg = (
        '<svg viewBox="0 0 100 100" preserveAspectRatio="none" '
        'xmlns="http://www.w3.org/2000/svg" '
        'style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;">'
        '<defs>'
        '<marker id="' + _ah + '" markerWidth="5" markerHeight="5" refX="5" refY="2.5" orient="auto">'
        '<polygon points="0 0, 5 2.5, 0 5" fill="#475569"/>'
        '</marker>'
        '<marker id="' + _ah2 + '" markerWidth="5" markerHeight="5" refX="0" refY="2.5" orient="auto">'
        '<polygon points="5 0, 0 2.5, 5 5" fill="#475569"/>'
        '</marker>'
        '</defs>'
        # Pos1: bogie → left edge upper
        '<line x1="20.6" y1="41.8" x2="1" y2="30" '
        'stroke="#475569" stroke-width="0.9" stroke-dasharray="2,1.5" marker-end="url(#' + _ah2 + ')"/>'
        # Pos2: bogie → left edge lower
        '<line x1="20.6" y1="62.7" x2="1" y2="71" '
        'stroke="#475569" stroke-width="0.9" stroke-dasharray="2,1.5" marker-end="url(#' + _ah2 + ')"/>'
        # Pos3: bogie → right edge upper
        '<line x1="79.4" y1="41.8" x2="99" y2="30" '
        'stroke="#475569" stroke-width="0.9" stroke-dasharray="2,1.5" marker-end="url(#' + _ah + ')"/>'
        # Pos4: bogie → right edge lower
        '<line x1="79.4" y1="62.7" x2="99" y2="71" '
        'stroke="#475569" stroke-width="0.9" stroke-dasharray="2,1.5" marker-end="url(#' + _ah + ')"/>'
        '</svg>'
    )

    # LRV badge centred over image
    lrv_badge = (
        '<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);'
        'background:rgba(255,255,255,0.85);border-radius:6px;padding:2px 10px;'
        'font-size:12px;font-weight:700;font-family:monospace;color:#1E293B;'
        'border:1px solid #CBD5E1;pointer-events:none;">'
        + lrv_id +
        '</div>'
    )

    vehicle_block = (
        '<div style="position:relative;flex:1;min-width:0;">'
        '<img src="' + _IMG + '" alt="LRV ' + lrv_id + ' diagram" '
        'style="width:100%;display:block;filter:opacity(0.9);"/>'
        + arrow_svg
        + lrv_badge
        + '</div>'
    )

    rail_legend = (
        '<div style="display:flex;gap:16px;justify-content:center;'
        'margin-top:10px;font-size:10px;color:#94A3B8;">'
        '<span>&#43; Upper rail (above)</span>'
        '<span>&#8722; Lower rail (below)</span>'
        '</div>'
    )

    title = (
        '<div style="font-size:12px;font-weight:700;letter-spacing:1.5px;color:#475569;'
        'text-transform:uppercase;text-align:center;margin-bottom:10px;">'
        + lrv_id + ' — Top-down View'
        + '</div>'
    )

    inner = (
        '<div style="display:flex;align-items:center;gap:10px;">'
        + left_col
        + vehicle_block
        + right_col
        + '</div>'
    )

    return (
        '<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;'
        'padding:12px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,0.07);">'
        + title
        + inner
        + rail_legend
        + '</div>'
    )

def _show_last_inspected_summary(supabase):
    st.markdown('<div class="section-header">Last Inspected — Per Shoe</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-intro">Physical layout of each LRV showing when each collector shoe was last '
        'inspected. Cards are positioned at their actual bogie locations — A End (left) positions 1 & 2, '
        'B End (right) positions 3 & 4. Upper rail (+) shown above vehicle, lower rail (−) below.</div>',
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

            st.markdown(_lrv_diagram_html(lrv_id, shoe_data), unsafe_allow_html=True)

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
