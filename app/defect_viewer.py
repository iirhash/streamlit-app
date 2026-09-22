# app/defect_viewer.py
# ── Defect Viewer Page ─────────────────────────────────────────
# Role-based tabbed interface:
#   Technician (no login): Recent Detections only
#   Management: Review Queue | Reviewed | New Detection | Recent Detections

import streamlit as st
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.login import get_supabase, is_logged_in, get_role
from core.yolo_detect import (
    detect_defects, get_model_info,
    CONFIDENCE_THRESHOLD, SCUFF_MARKS_THRESHOLD, get_status_label,
    get_capture_count, reset_capture_count,
    trigger_roboflow_retrain, RETRAIN_THRESHOLD,
    ROBOFLOW_PROJECT
)

TEMP_DIR = "temp"
SESSIONS_PER_PAGE = 5  # Number of capture sessions per page


@st.cache_data(ttl=30)
def load_defect_records(_supabase, reviewed=None, limit=200):
    """
    Cached defect records loader — TTL 30s.
    Clears automatically or when load_defect_records.clear() is called.
    """
    try:
        query = _supabase.table("defect_records") \
            .select("*, inspection_sessions(asset_id, technician_name)") \
            .order("detected_at", desc=True) \
            .limit(limit)
        if reviewed is not None:
            query = query.eq("reviewed", reviewed)
        return query.execute().data or []
    except:
        return []

# ── Singapore Time helper ──────────────────────────────────────
def _to_sgt(ts_str):
    """
    Converts a UTC ISO timestamp string from Supabase to
    Singapore Time (SGT = UTC+8) formatted for display.
    e.g. '2026-08-05T06:03:48.919588+00:00' → '05 Aug 2026, 14:03:48 SGT'
    Returns the original string if parsing fails.
    """
    if not ts_str:
        return ""
    try:
        from datetime import timezone, timedelta
        SGT = timezone(timedelta(hours=8))
        # Parse ISO format (handles both +00:00 and Z suffixes)
        dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        dt_sgt = dt.astimezone(SGT)
        return dt_sgt.strftime("%d %b %Y, %H:%M:%S SGT")
    except Exception:
        return str(ts_str)

DEFECT_EMOJI = {
    "crack":     "🔴",
    "wear":      "🔍",
    "corrosion": "🟡",
    "oxidation": "🟡",
    "arcing":    "🔥",
    "scuff marks": "🔍",
    "none":      "🟢",
    "other":     "⚪",
    "unknown":   "❓",
}

# ── Physics knowledge base ─────────────────────────────────────
PHYSICS_KB = {
    "wear": {
        "cause": (
            "The collector shoe is in constant sliding contact with the third rail during LRV "
            "operation. This continuous friction causes progressive material removal on the contact "
            "strip surface of the collector shoe. This is a normal and expected part of the "
            "collector shoe's service life — every collector shoe will show wear over time."
        ),
        "omm_action": (
            "Measure wear depth using a depth gauge on the collector shoe contact strip "
            "and take action based on the wear severity table below:"
        ),
        "minimise": [
            "Ensure contact force is within 60Nm ±2Nm during PM — incorrect force accelerates uneven wear",
            "Apply LPS1 greaseless lubricant to the power collector arms if spring action feels stiff",
            "A proper contact force prevents excessive localised wear on the collector shoe surface",
            "Check smoothness of spring action at every PM interval",
        ],
    },
    "scuff marks": {
        "cause": (
            "Localised surface abrasion on the collector shoe from uneven third rail contact, "
            "debris on the rail, or slight misalignment between the collector shoe and the rail. "
            "Unlike general wear which is uniform thinning, scuff marks appear as directional "
            "scratches concentrated in specific areas of the collector shoe surface. "
            "Scuff marks can accelerate localised wear — grooved areas have reduced material "
            "thickness and are more prone to losing consistent rail contact, which over time "
            "may lead to arcing if left unaddressed."
        ),
        "omm_action": (
            "Visually inspect the collector shoe contact strip surface. If scuff marks are deep "
            "or concentrated in one area, measure depth with a depth gauge. Check contact force "
            "and monitor at the next PM interval. No immediate removal from service required "
            "unless structural integrity is compromised."
        ),
        "minimise": [
            "Ensure contact force is within 60Nm ±2Nm — incorrect contact force causes uneven rail engagement",
            "Check spring action smoothness — apply LPS1 greaseless lubricant to the arm if stiff",
            "Inspect the third rail contact area for debris during PM",
            "Verify contact marks are within 15.50mm to 30.50mm from bottom of shoe — misaligned contact concentrates stress on specific areas",
        ],
    },
    "crack": {
        "cause": (
            "Structural fatigue on the collector shoe pan body from repeated mechanical stress "
            "cycles during third rail contact, thermal expansion and contraction, or impact from "
            "debris on the rail. Cracks on the collector shoe pan body or arm are serious — "
            "they can lead to sudden failure of the collector shoe during LRV operation."
        ),
        "omm_action": (
            "Remove the LRV from service immediately. Do not operate. Replace the collector shoe "
            "assembly. Before reinstalling, inspect the pan support, flexible conductor, split pin "
            "and lock wire for secondary damage."
        ),
        "minimise": [
            "Check torque markings at each PM — if missing or misaligned, check spring washer condition",
            "Re-torque bolts to required values: M8 = 14Nm, M10 = 27Nm, M12 = 26Nm",
            "Inspect flexible conductors and split pins for damage at every 3-month PM",
            "Visually check all power collector pan bodies and arms for cracks and deformations",
        ],
    },
    "arcing": {
        "cause": (
            "Electrical discharge between the collector shoe and the third rail during momentary "
            "loss of contact — caused by rail gaps, debris, or vibration. The high current arc "
            "burns the collector shoe contact strip surface, leaving burnt or pitted marks. "
            "Arcing is an abnormal condition and should not occur during normal operation."
        ),
        "omm_action": (
            "Visually check the collector shoe pan body and contact strip for burnt marks and "
            "pitting. If burn marks are significant or affect the structural integrity of the "
            "collector shoe, escalate to the engineer immediately. Do not return the LRV to "
            "service until the collector shoe has been cleared by an engineer."
        ),
        "minimise": [
            "Ensure rising force is within 60Nm ±2Nm — a weak spring causes the collector shoe to lose contact with the rail more frequently",
            "Apply LPS1 greaseless lubricant if the power collector arm spring action is not smooth",
            "Check torque marking alignment — misaligned marks indicate potential loss of contact force",
            "Inspect and replace flat spring washers if found flat — flat washers reduce contact force",
        ],
    },
    "corrosion": {
        "cause": (
            "Electrochemical reaction between the collector shoe aluminium surface and moisture, "
            "accelerated by Singapore's humid climate. Electric corrosion can also occur from "
            "stray currents during arcing events on the collector shoe contact strip. "
            "This is an abnormal condition requiring inspection."
        ),
        "omm_action": (
            "Clean the affected area on the collector shoe. Assess depth — surface oxidation is "
            "acceptable but deep pitting or structural corrosion on the collector shoe requires "
            "replacement. Check the insulator and base plate for stains during the 3-month PM."
        ),
        "minimise": [
            "Clean insulators and base plates during each 3-month PM",
            "Ensure no water pooling around the collector shoe assembly",
            "Inspect wiring for abrasions, burnt marks and signs of electric corrosion at every PM",
        ],
    },
    "pore": {
        "cause": (
            "Surface porosity or water staining on the collector shoe from moisture accumulation "
            "during Singapore's rainy season or during LRV washing. Water marks indicate areas "
            "where moisture has pooled and evaporated, leaving mineral deposits on the "
            "collector shoe surface."
        ),
        "omm_action": (
            "Monitor — surface marks alone are not structurally significant on the collector shoe. "
            "If pores appear deep, measure with a depth gauge to rule out subsurface material loss. "
            "Clean the collector shoe surface and re-inspect at the next PM interval."
        ),
        "minimise": [
            "Ensure proper drainage around the collector shoe assembly to prevent moisture accumulation",
            "Clean the collector shoe surface during routine PM inspections",
        ],
    },
    "water mark": {
        "cause": (
            "Water staining on the collector shoe surface from moisture accumulation during "
            "Singapore's rainy season or during LRV washing. Water marks indicate areas where "
            "moisture has pooled and evaporated, leaving mineral deposits."
        ),
        "omm_action": (
            "Monitor — water marks alone are not structurally significant. Clean the collector "
            "shoe surface and re-inspect at the next PM interval. If marks persist or appear "
            "to indicate deeper damage, measure with a depth gauge."
        ),
        "minimise": [
            "Ensure proper drainage around the collector shoe assembly",
            "Clean the collector shoe surface during routine PM inspections",
        ],
    },
    "none": {
        "cause": "No defect detected on the collector shoe surface in this image.",
        "omm_action": "No action required. Continue normal inspection schedule.",
        "minimise": [],
    },
}

# Aliases
PHYSICS_KB["oxidation"]   = PHYSICS_KB["corrosion"]
PHYSICS_KB["scuff marks"] = PHYSICS_KB["scuff marks"]

WEAR_ACTIONS = [
    ("None (0–1.9mm wear)",    "Continue normal inspection schedule — no action required"),
    ("Minor (2–3.9mm wear)",   "Increase inspection frequency and monitor closely at next PM"),
    ("Moderate (4–4.9mm wear — dry season)", "Rotate collector shoe 180° if not previously rotated (loosen 2 bolts M8×25, rotate, retighten to 14Nm). Replace if shoe has already been rotated twice"),
    ("Moderate (3–3.9mm wear — rainy season)", "Rotate collector shoe 180° — wet rails accelerate wear rate. Retighten to 14Nm after rotation"),
    ("Severe (≥5mm wear)",     "Replace collector shoe immediately. Do not return LRV to service until replaced"),
]


def _get_physics_panel(defect, confidence):
    """
    Role-gated physics panel — card-based layout with colour-coded severity.
    - Management: full panel (why + action table + minimise)
    - Others: not shown
    """
    if not is_logged_in():
        return
    if get_role() not in ("management", "supervisor", "ic"):
        return
    if defect in ("none", "unknown", None, "water mark"):
        return

    defect_lookup = {
        "oxidation":   "corrosion",
        "water mark":  "water mark",
        "pore":        "pore",
        "scuff marks": "scuff marks",
    }.get(defect, defect)

    kb       = PHYSICS_KB.get(defect_lookup, PHYSICS_KB["wear"])
    expanded = False
    role     = get_role()

    # ── Defect urgency colour ──────────────────────────────────
    URGENCY = {
        "wear":        ("#FFF7ED", "#E8920A", "🟠 Expected — Monitor"),
        "scuff marks": ("#FFF7ED", "#E8920A", "🟡 Monitor Closely"),
        "pore":        ("#F0FDF4", "#0A8A72", "🟢 Low Risk — Monitor"),
        "corrosion":   ("#FEF3C7", "#92400E", "🟠 Inspect — Escalate if Deep"),
        "oxidation":   ("#FEF3C7", "#92400E", "🟠 Inspect — Escalate if Deep"),
        "crack":       ("#FEF2F2", "#C9382A", "🔴 CRITICAL — Remove from Service"),
        "arcing":      ("#FEF2F2", "#C9382A", "🔴 CRITICAL — Escalate to Engineer"),
    }
    bg, accent, urgency_label = URGENCY.get(defect, ("#F8FAFC", "#64748B", "⚪ Unknown"))

    with st.expander(f"📖 Physics — {defect.title()} | {urgency_label}", expanded=expanded):

        # ── Urgency banner ─────────────────────────────────────
        st.markdown(
            f"""<div style="background:{bg};border-left:4px solid {accent};
            border-radius:6px;padding:10px 14px;margin-bottom:12px;">
            <span style="font-weight:700;color:{accent};font-size:14px;">
            {urgency_label}</span>
            </div>""",
            unsafe_allow_html=True
        )

        # ── Why it occurs — management only ───────────────────
        if role == "management":
            st.markdown(
                f"""<div style="background:#F8FAFC;border:1px solid #E2E8F0;
                border-radius:8px;padding:12px 16px;margin-bottom:12px;">
                <div style="font-size:12px;font-weight:700;color:#64748B;
                text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">
                WHY IT OCCURS</div>
                <div style="font-size:14px;color:#1E293B;line-height:1.6;">
                {kb["cause"]}</div>
                </div>""",
                unsafe_allow_html=True
            )

        # ── Subsequent Action ──────────────────────────────────
        st.markdown(
            f"""<div style="background:{bg};border:1px solid {accent};
            border-radius:8px;padding:12px 16px;margin-bottom:12px;">
            <div style="font-size:12px;font-weight:700;color:{accent};
            text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">
            SUBSEQUENT ACTION</div>
            <div style="font-size:14px;color:#1E293B;line-height:1.6;">
            {kb["omm_action"]}</div>
            </div>""",
            unsafe_allow_html=True
        )

        # ── Wear severity table ────────────────────────────────
        if defect == "wear":
            SEVERITY_STYLES = [
                ("#F0FDF4", "#166534", "🟢"),  # None
                ("#FEFCE8", "#854D0E", "🟡"),  # Minor
                ("#FFF7ED", "#9A3412", "🟠"),  # Moderate dry
                ("#FFF7ED", "#9A3412", "🟠"),  # Moderate rainy
                ("#FEF2F2", "#991B1B", "🔴"),  # Severe
            ]
            st.markdown(
                "<div style='font-size:12px;font-weight:700;color:#64748B;"
                "text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;'>"
                "SEVERITY TABLE</div>",
                unsafe_allow_html=True
            )
            for i, (label, action) in enumerate(WEAR_ACTIONS):
                sbg, sc, icon = SEVERITY_STYLES[i]
                st.markdown(
                    f"""<div style="background:{sbg};border:1px solid {sc};
                    border-radius:6px;padding:10px 14px;margin-bottom:6px;">
                    <div style="font-weight:700;color:{sc};font-size:13px;">
                    {icon} {label}</div>
                    <div style="font-size:13px;color:#1E293B;margin-top:4px;">
                    {action}</div>
                    </div>""",
                    unsafe_allow_html=True
                )

        # ── How to minimise — management only ─────────────────
        if role == "management" and kb["minimise"]:
            with st.expander("✅ How to Minimise", expanded=False):
                for tip in kb["minimise"]:
                    st.markdown(f"- {tip}")

        # ── Disclaimer ─────────────────────────────────────────
        st.caption(
            "⚠️ Confidence score reflects how certain the model is that a defect is present — "
            "not how physically severe it is. Physical severity can only be determined through "
            "depth gauge measurement."
        )


# ── Validation helpers ─────────────────────────────────────────
def _needs_review(defect, confidence):
    """Returns True if detection needs human review based on per-defect threshold."""
    if confidence <= 0:
        return False
    threshold = SCUFF_MARKS_THRESHOLD if defect == "scuff marks" else CONFIDENCE_THRESHOLD
    return confidence < threshold


def _validate_asset_id(supabase, asset_id):
    if not asset_id:
        return False, "Please enter an Asset ID."
    if asset_id.upper().startswith("CS-"):
        try:
            result = supabase.table("collector_shoes") \
                .select("shoe_id, condition, lrv_asset_id, rotation_status") \
                .eq("shoe_id", asset_id.upper()).execute()
            if not result.data:
                return False, (
                    f"❌ **{asset_id}** is not registered. "
                    f"Please register it on the 👟 Collector Shoe page, "
                    f"or check the format (e.g. CS-LRV00-ARU)."
                )
        except Exception as e:
            return False, f"Could not verify Asset ID: {e}"
    return True, None


def _check_duplicate(supabase, asset_id):
    from datetime import date
    today = date.today().isoformat()
    try:
        result = supabase.table("inspection_sessions") \
            .select("id") \
            .eq("asset_id", asset_id) \
            .gte("created_at", f"{today}T00:00:00") \
            .execute()
        if result.data:
            return True, f"⚠️ An inspection was already submitted for **{asset_id}** today. Click again to proceed anyway."
    except:
        pass
    return False, None


# ── Signed URL ─────────────────────────────────────────────────
@st.cache_data(ttl=3300)
def _signed_url(_supabase, bucket, path, expires=3600):
    """Cached signed URL — TTL 55min to match Supabase 60min expiry.
    Avoids regenerating URLs on every rerun which wastes egress."""
    if not path:
        return None
    try:
        signed = _supabase.storage.from_(bucket).create_signed_url(path, expires)
        return signed.get("signedURL")
    except:
        return None


# ── Detection pipeline ─────────────────────────────────────────
def _run_detection_pipeline(supabase, asset_id, uploaded):
    os.makedirs(TEMP_DIR, exist_ok=True)
    local_path = os.path.join(TEMP_DIR, uploaded.name)
    with open(local_path, "wb") as f:
        f.write(uploaded.getbuffer())

    session_resp = supabase.table("inspection_sessions").insert({
        "technician_name": st.session_state.get("full_name", "Unknown"),
        "employee_id":     st.session_state.get("sap_number", "N/A"),
        "asset_id":        asset_id,
        "status":          "submitted",
        "submitted_by":    st.session_state.get("user_id"),
        "notes":           "Photo uploaded via Defect Viewer",
    }).execute()
    session_id = session_resp.data[0]["id"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path  = f"{asset_id}/{session_id}/{timestamp}_{uploaded.name}"
    with open(local_path, "rb") as f:
        supabase.storage.from_("raw-photos").upload(
            path=raw_path, file=f,
            file_options={"content-type": uploaded.type or "image/jpeg"},
        )

    result         = detect_defects(local_path)
    annotated_path = None

    if result.get("error") is None and result.get("annotated") is not None:
        import cv2
        annotated_local = os.path.join(TEMP_DIR, f"annotated_{uploaded.name}")
        cv2.imwrite(annotated_local, cv2.cvtColor(result["annotated"], cv2.COLOR_RGB2BGR))
        annotated_path = f"{asset_id}/{session_id}/{timestamp}_annotated.jpg"
        with open(annotated_local, "rb") as f:
            supabase.storage.from_("annotated-photos").upload(
                path=annotated_path, file=f,
                file_options={"content-type": "image/jpeg"},
            )
        os.remove(annotated_local)

    # Insert one defect record per detection
    SKIP_CLASSES = ("collector_shoe", "collector shoe")
    detections   = result.get("detections", [])
    valid_detections = [
        d for d in detections
        if d["label"].lower() not in SKIP_CLASSES
        and d["label"].lower() != "none"
        and d["confidence"] > 0
    ]

    # Fallback to single record if no valid detections
    if not valid_detections:
        valid_detections = [{
            "label":      result.get("defect", "none"),
            "confidence": result.get("confidence", 0.0),
        }]

    from core.yolo_detect import ROBOFLOW_CLASS_MAP
    for det in valid_detections:
        defect_type = ROBOFLOW_CLASS_MAP.get(det["label"].lower(), det["label"].lower())
        supabase.table("defect_records").insert({
            "session_id":           session_id,
            "defect_type":          defect_type,
            "confidence":           det["confidence"],
            "raw_image_path":       raw_path,
            "annotated_image_path": annotated_path,
            "reviewed":             False,
        }).execute()

    os.remove(local_path)
    return result


# ── Delete record ──────────────────────────────────────────────
def _delete_record(supabase, rec_id, raw_path, annotated_path, session_id):
    """
    Deletes a defect record and its associated images from Supabase.
    Also deletes the parent inspection session if no other records
    reference it. Role-gated — management/supervisor only.
    Steps:
      1. Delete raw image from raw-photos storage
      2. Delete annotated image from annotated-photos storage
      3. Delete defect_record row
      4. Check if session has any remaining records — if not, delete session
    """
    errors = []

    # 1. Delete raw image
    if raw_path:
        try:
            supabase.storage.from_("raw-photos").remove([raw_path])
        except Exception as e:
            errors.append(f"Raw image: {e}")

    # 2. Delete annotated image
    if annotated_path:
        try:
            supabase.storage.from_("annotated-photos").remove([annotated_path])
        except Exception as e:
            errors.append(f"Annotated image: {e}")

    # 3. Delete defect record
    try:
        supabase.table("defect_records").delete().eq("id", rec_id).execute()
    except Exception as e:
        errors.append(f"Defect record: {e}")
        return False, errors

    # 4. Clean up orphaned session if no other records reference it
    if session_id:
        try:
            remaining = supabase.table("defect_records") \
                .select("id", count="exact") \
                .eq("session_id", session_id) \
                .execute()
            if (remaining.count or 0) == 0:
                supabase.table("inspection_sessions") \
                    .delete().eq("id", session_id).execute()
        except:
            pass  # non-critical — session cleanup is best-effort

    return True, errors
    """⚠️ Human Review Queue tab"""
    try:
        records = supabase.table("defect_records") \
            .select("*, inspection_sessions(asset_id, technician_name)") \
            .gt("confidence", 0) \
            .eq("reviewed", False) \
            .order("detected_at", desc=True) \
            .execute()

        if not records.data:
            st.success("✅ No detections currently need review — all results are above the confidence threshold or have been reviewed.")
            return

        # Filter by per-defect threshold
        filtered_data = [
            r for r in records.data
            if _needs_review(r.get("defect_type", ""), r.get("confidence", 0))
        ]
        if not filtered_data:
            st.success("✅ No detections currently need review — all results are above the confidence threshold or have been reviewed.")
            return
        st.caption(f"{len(filtered_data)} detection(s) pending review")
        for rec in filtered_data:
            session_info = rec.get("inspection_sessions") or {}
            asset_id  = session_info.get("asset_id", "Unknown")
            tech_name = session_info.get("technician_name", "Unknown")
            defect    = rec.get("defect_type", "none")
            conf      = rec.get("confidence", 0)
            timestamp = _to_sgt(rec.get("detected_at", ""))
            rec_id    = rec.get("id")

            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(
                        f"**Asset:** {asset_id}  |  **Technician:** {tech_name}  \n"
                        f"{DEFECT_EMOJI.get(defect, '🔍')} `{defect}` at **{conf:.0%}** confidence  \n"
                        f"🕐 {timestamp}"
                    )
                with col2:
                    st.markdown(
                        f"""<div style="background:#FEF3C7;border:1px solid #F59E0B;
                        border-radius:8px;padding:8px 12px;text-align:center;">
                        <div style="font-size:11px;font-weight:700;color:#92400E;">NEEDS REVIEW</div>
                        <div style="font-size:20px;font-weight:700;color:#B45309;">{conf:.0%}</div>
                        <div style="font-size:10px;color:#92400E;">confidence</div>
                        </div>""", unsafe_allow_html=True
                    )

                # Lazy load images
                show_key = f"show_images_tech_{rec_id}"
                if not st.session_state.get(show_key, False):
                    if st.button("🖼️ View Images", key=f"view_img_tech_{rec_id}", use_container_width=True):
                        st.session_state[show_key] = True
                        st.rerun()
                else:
                    img1, img2 = st.columns(2)
                    with img1:
                        st.caption("Original")
                        raw_url = _signed_url(supabase, "raw-photos", rec.get("raw_image_path"))
                        if raw_url: st.image(raw_url)
                        else: st.caption("No image")
                    with img2:
                        st.caption("YOLO Annotated")
                        ann_url = _signed_url(supabase, "annotated-photos", rec.get("annotated_image_path"))
                        if ann_url: st.image(ann_url)
                        else: st.caption("No annotation")

                _get_physics_panel(defect, conf)

                st.markdown("---")
                review_key = f"show_review_form_{rec_id}_old"
                if not st.session_state.get(review_key, False):
                    b1, b2 = st.columns([2, 1])
                    with b1:
                        st.caption("Once verified, mark as reviewed.")
                    with b2:
                        if st.button("🔍 Start Review", key=f"review_old_{rec_id}", type="primary"):
                            st.session_state[review_key] = True
                            st.rerun()
                else:
                    st.markdown("**📝 Review Decision**")
                    verdict = st.radio(
                        "Verdict",
                        options=["confirmed", "false_positive", "uncertain"],
                        format_func=lambda x: {
                            "confirmed":      "✅ Confirmed defect — defect is real",
                            "false_positive": "❌ False positive — no defect present",
                            "uncertain":      "⚠️ Uncertain — needs physical inspection",
                        }[x],
                        key=f"verdict_old_{rec_id}",
                    )
                    notes = st.text_area(
                        "Reviewer Notes (optional)",
                        placeholder="e.g. Confirmed wear, depth gauge measurement pending.",
                        height=80,
                        key=f"notes_old_{rec_id}",
                    )
                    r1, r2 = st.columns(2)
                    with r1:
                        if st.button("💾 Submit Review", key=f"submit_old_{rec_id}", type="primary"):
                            try:
                                supabase.table("defect_records").update({
                                    "reviewed":         True,
                                    "reviewed_by":      st.session_state.get("user_id"),
                                    "reviewed_at":      datetime.now().isoformat(),
                                    "reviewer_verdict": verdict,
                                    "reviewer_notes":   notes.strip() or None,
                                }).eq("id", rec_id).execute()
                                st.session_state.pop(review_key, None)
                                st.session_state["review_success_msg"] = f"✅ Review submitted — {verdict.replace('_', ' ').title()}"
                                load_defect_records.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Could not submit review: {e}")
                    with r2:
                        if st.button("Cancel", key=f"cancel_old_{rec_id}"):
                            st.session_state.pop(review_key, None)
                            st.rerun()

    except Exception as e:
        st.error(f"Could not load review queue: {e}")


# ── Tab content functions ──────────────────────────────────────
def _tab_review_queue(supabase):
    """⚠️ Human Review Queue tab"""
    try:
        records = supabase.table("defect_records") \
            .select("*, inspection_sessions(asset_id, technician_name)") \
            .gt("confidence", 0) \
            .eq("reviewed", False) \
            .order("detected_at", desc=True) \
            .execute()

        if not records.data:
            st.success("✅ No detections currently need review — all results are above the confidence threshold or have been reviewed.")
            return

        # Filter by per-defect threshold
        filtered_data = [
            r for r in records.data
            if _needs_review(r.get("defect_type", ""), r.get("confidence", 0))
        ]
        if not filtered_data:
            st.success("✅ No detections currently need review — all results are above the confidence threshold or have been reviewed.")
            return
        st.caption(f"{len(filtered_data)} detection(s) pending review")
        for rec in filtered_data:
            session_info = rec.get("inspection_sessions") or {}
            asset_id  = session_info.get("asset_id", "Unknown")
            tech_name = session_info.get("technician_name", "Unknown")
            defect    = rec.get("defect_type", "none")
            conf      = rec.get("confidence", 0)
            timestamp = _to_sgt(rec.get("detected_at", ""))
            rec_id    = rec.get("id")

            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(
                        f"**Asset:** {asset_id}  |  **Technician:** {tech_name}  \n"
                        f"{DEFECT_EMOJI.get(defect, '🔍')} `{defect}` at **{conf:.0%}** confidence  \n"
                        f"🕐 {timestamp}"
                    )
                with col2:
                    st.markdown(
                        f"""<div style="background:#FEF3C7;border:1px solid #F59E0B;
                        border-radius:8px;padding:8px 12px;text-align:center;">
                        <div style="font-size:11px;font-weight:700;color:#92400E;">NEEDS REVIEW</div>
                        <div style="font-size:20px;font-weight:700;color:#B45309;">{conf:.0%}</div>
                        <div style="font-size:10px;color:#92400E;">confidence</div>
                        </div>""", unsafe_allow_html=True
                    )

                # Lazy load images
                show_key = f"show_images_rq_{rec_id}"
                if not st.session_state.get(show_key, False):
                    if st.button("🖼️ View Images", key=f"view_img_rq_{rec_id}", use_container_width=True):
                        st.session_state[show_key] = True
                        st.rerun()
                else:
                    img1, img2 = st.columns(2)
                    with img1:
                        st.caption("Original")
                        raw_url = _signed_url(supabase, "raw-photos", rec.get("raw_image_path"))
                        if raw_url: st.image(raw_url)
                        else: st.caption("No image")
                    with img2:
                        st.caption("YOLO Annotated")
                        ann_url = _signed_url(supabase, "annotated-photos", rec.get("annotated_image_path"))
                        if ann_url: st.image(ann_url)
                        else: st.caption("No annotation")

                _get_physics_panel(defect, conf)

                st.markdown("---")
                # ── Reviewer verdict + notes form ──────────────
                review_key = f"show_review_form_{rec_id}"
                if not st.session_state.get(review_key, False):
                    b1, b2 = st.columns([2, 1])
                    with b1:
                        st.caption("Once verified, mark as reviewed.")
                    with b2:
                        if st.button("🔍 Start Review", key=f"review_{rec_id}", type="primary"):
                            st.session_state[review_key] = True
                            st.rerun()
                else:
                    st.markdown("**📝 Review Decision**")
                    verdict = st.radio(
                        "Verdict",
                        options=["confirmed", "false_positive", "uncertain"],
                        format_func=lambda x: {
                            "confirmed":      "✅ Confirmed defect — defect is real",
                            "false_positive": "❌ False positive — no defect present",
                            "uncertain":      "⚠️ Uncertain — needs physical inspection",
                        }[x],
                        key=f"verdict_{rec_id}",
                        horizontal=False,
                    )
                    notes = st.text_area(
                        "Reviewer Notes (optional)",
                        placeholder="e.g. Confirmed wear, depth gauge measurement pending. Rotation scheduled for next PM.",
                        height=80,
                        key=f"notes_{rec_id}",
                    )
                    r1, r2 = st.columns(2)
                    with r1:
                        if st.button("💾 Submit Review", key=f"submit_review_{rec_id}", type="primary"):
                            try:
                                supabase.table("defect_records").update({
                                    "reviewed":         True,
                                    "reviewed_by":      st.session_state.get("user_id"),
                                    "reviewed_at":      datetime.now().isoformat(),
                                    "reviewer_verdict": verdict,
                                    "reviewer_notes":   notes.strip() or None,
                                }).eq("id", rec_id).execute()
                                st.session_state.pop(review_key, None)
                                st.session_state["review_success_msg"] = f"✅ Review submitted — {verdict.replace('_', ' ').title()}"
                                load_defect_records.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Could not submit review: {e}")
                    with r2:
                        if st.button("Cancel", key=f"cancel_review_{rec_id}"):
                            st.session_state.pop(review_key, None)
                            st.rerun()

                # ── Delete button — management/supervisor only ─
                if is_logged_in() and get_role() in ("management", "supervisor", "ic"):
                    confirm_key = f"confirm_delete_queue_{rec_id}"
                    st.markdown("---")
                    if not st.session_state.get(confirm_key, False):
                        if st.button("🗑️ Delete Record", key=f"del_queue_{rec_id}"):
                            st.session_state[confirm_key] = True
                            st.rerun()
                    else:
                        st.warning("⚠️ This will permanently delete the record and its images. Are you sure?")
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("✅ Yes, Delete", key=f"confirm_yes_queue_{rec_id}", type="primary"):
                                success, errors = _delete_record(
                                    supabase, rec_id,
                                    rec.get("raw_image_path"),
                                    rec.get("annotated_image_path"),
                                    rec.get("session_id"),
                                )
                                st.session_state.pop(confirm_key, None)
                                if success:
                                    st.success("🗑️ Record deleted.")
                                    load_defect_records.clear()
                                    import time; time.sleep(0.5)
                                    st.rerun()
                                else:
                                    st.error(f"Delete failed: {errors}")
                        with c2:
                            if st.button("❌ Cancel", key=f"confirm_no_queue_{rec_id}"):
                                st.session_state.pop(confirm_key, None)
                                st.rerun()

    except Exception as e:
        st.error(f"Could not load review queue: {e}")


def _tab_reviewed(supabase):
    """✅ Reviewed Detections tab — paginated by session (5 per page)"""
    # Date filter
    days = min(st.session_state.get("reviewed_days", 30), 365)
    col_info, col_btn = st.columns([3, 1])
    with col_info:
        st.caption(f"Showing reviewed records from the last {days} day(s). Images load on demand.")
    with col_btn:
        if days < 365:
            if st.button("📅 Load older", key="load_older_reviewed"):
                st.session_state["reviewed_days"] = days + 30
                st.session_state["reviewed_page"] = 0
                st.rerun()
        else:
            st.caption("📅 Showing max 365 days")

    from datetime import datetime, timezone, timedelta
    from collections import defaultdict
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    try:
        records = supabase.table("defect_records") \
            .select("*, inspection_sessions(asset_id, technician_name)") \
            .eq("reviewed", True) \
            .gte("reviewed_at", cutoff) \
            .order("reviewed_at", desc=True) \
            .limit(500) \
            .execute()

        if not records.data:
            if days >= 365:
                st.info("📭 No reviewed detections found in the last 365 days — this is the maximum search range.")
            else:
                st.info(f"📭 No reviewed detections in the last {days} day(s). Click '📅 Load older' to see older records.")
            return

        # Group by session
        sessions      = defaultdict(list)
        session_order = []
        for rec in records.data:
            sid = rec.get("session_id")
            if sid not in sessions:
                session_order.append(sid)
            sessions[sid].append(rec)

        total_sessions = len(session_order)
        total_pages    = max(1, (total_sessions + SESSIONS_PER_PAGE - 1) // SESSIONS_PER_PAGE)
        page           = st.session_state.get("reviewed_page", 0)
        page           = max(0, min(page, total_pages - 1))

        # Pagination controls — top
        p1, p2, p3 = st.columns([1, 2, 1])
        with p1:
            if st.button("← Previous", key="rev_prev", disabled=page == 0):
                st.session_state["reviewed_page"] = page - 1
                st.rerun()
        with p2:
            st.markdown(f"<div style='text-align:center;padding-top:6px;'>Page {page+1} of {total_pages} &nbsp;·&nbsp; {total_sessions} capture(s)</div>", unsafe_allow_html=True)
        with p3:
            if st.button("Next →", key="rev_next", disabled=page >= total_pages - 1):
                st.session_state["reviewed_page"] = page + 1
                st.rerun()

        st.markdown("---")

        # Show current page sessions
        start_idx = page * SESSIONS_PER_PAGE
        end_idx   = min(start_idx + SESSIONS_PER_PAGE, total_sessions)
        page_sessions = session_order[start_idx:end_idx]

        VERDICT_DISPLAY = {
            "confirmed":      "✅ Confirmed defect",
            "false_positive": "❌ False positive",
            "uncertain":      "⚠️ Uncertain — needs physical inspection",
        }

        for sid in page_sessions:
            recs = sessions[sid]
            recs.sort(key=lambda r: r.get("confidence", 0), reverse=True)

            first        = recs[0]
            session_info = first.get("inspection_sessions") or {}
            asset_id     = session_info.get("asset_id", "Unknown")
            tech_name    = session_info.get("technician_name", "Unknown")
            reviewed_at  = _to_sgt(first.get("reviewed_at", ""))

            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"**Asset:** {asset_id}  |  **Technician:** {tech_name}")
                    for r in recs:
                        defect  = r.get("defect_type", "none")
                        conf    = r.get("confidence", 0)
                        verdict = r.get("reviewer_verdict", None)
                        notes   = r.get("reviewer_notes", None)
                        st.markdown(
                            f"{DEFECT_EMOJI.get(defect, '🔍')} `{defect}` at **{conf:.0%}** confidence"
                        )
                        if verdict:
                            st.markdown(f"**Verdict:** {VERDICT_DISPLAY.get(verdict, verdict)}")
                        if notes:
                            st.caption(notes)
                    st.caption(f"✅ Reviewed: {reviewed_at}")
                with col2:
                    st.markdown(
                        """<div style="background:#DCFCE7;border:1px solid #0A8A72;
                        border-radius:6px;padding:6px 10px;text-align:center;font-size:11px;">
                        <b style="color:#166534;">✅ REVIEWED</b></div>""",
                        unsafe_allow_html=True
                    )

                # Lazy load images — show all unique captures in session
                show_key = f"show_images_rev_{sid}"
                if not st.session_state.get(show_key, False):
                    if st.button("🖼️ View Images", key=f"view_img_rev_{sid}", use_container_width=True):
                        st.session_state[show_key] = True
                        st.rerun()
                else:
                    seen_paths = set()
                    unique_captures = []
                    for r in sorted(recs, key=lambda x: x.get("detected_at", "")):
                        raw_path = r.get("raw_image_path")
                        if raw_path and raw_path not in seen_paths:
                            seen_paths.add(raw_path)
                            unique_captures.append(r)

                    for i, capture in enumerate(unique_captures):
                        if len(unique_captures) > 1:
                            st.caption(f"**Capture {i+1} of {len(unique_captures)}**")
                        img1, img2 = st.columns(2)
                        with img1:
                            st.caption("Original")
                            raw_url = _signed_url(supabase, "raw-photos", capture.get("raw_image_path"))
                            if raw_url: st.image(raw_url)
                            else: st.caption("No image")
                        with img2:
                            st.caption("YOLO Annotated")
                            ann_url = _signed_url(supabase, "annotated-photos", capture.get("annotated_image_path"))
                            if ann_url: st.image(ann_url)
                            else: st.caption("No annotation")

                if is_logged_in() and get_role() in ("management", "supervisor", "ic"):
                    confirm_key = f"confirm_delete_session_{sid}"
                    st.markdown("---")
                    if not st.session_state.get(confirm_key, False):
                        if st.button("🗑️ Delete All Records for this Capture", key=f"del_session_{sid}"):
                            st.session_state[confirm_key] = True
                            st.rerun()
                    else:
                        st.warning(f"⚠️ This will delete all {len(recs)} record(s) for this capture. Are you sure?")
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("✅ Yes, Delete All", key=f"confirm_yes_session_{sid}", type="primary"):
                                all_success = True
                                for r in recs:
                                    success, errors = _delete_record(
                                        supabase, r.get("id"),
                                        r.get("raw_image_path"),
                                        r.get("annotated_image_path"),
                                        r.get("session_id"),
                                    )
                                    if not success:
                                        all_success = False
                                st.session_state.pop(confirm_key, None)
                                if all_success:
                                    st.success("🗑️ All records deleted.")
                                    load_defect_records.clear()
                                    st.rerun()
                                else:
                                    st.error("Some records could not be deleted.")
                        with c2:
                            if st.button("❌ Cancel", key=f"cancel_session_{sid}"):
                                st.session_state.pop(confirm_key, None)
                                st.rerun()

        # Pagination controls — bottom
        st.markdown("---")
        b1, b2, b3 = st.columns([1, 2, 1])
        with b1:
            if st.button("← Previous", key="rev_prev_bot", disabled=page == 0):
                st.session_state["reviewed_page"] = page - 1
                st.rerun()
        with b2:
            st.markdown(f"<div style='text-align:center;padding-top:6px;'>Page {page+1} of {total_pages}</div>", unsafe_allow_html=True)
        with b3:
            if st.button("Next →", key="rev_next_bot", disabled=page >= total_pages - 1):
                st.session_state["reviewed_page"] = page + 1
                st.rerun()

    except Exception as e:
        st.error(f"Could not load reviewed records: {e}")

def _fetch_recent_defects(_supabase, limit=50, days=7):
    """Fetch recent defect records — defaults to last 7 days to reduce egress.
    Images are lazy-loaded separately only when user requests them."""
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    response = _supabase.table("defect_records") \
        .select("id, session_id, defect_type, confidence, detected_at, reviewed, reviewer_verdict, reviewer_notes, raw_image_path, annotated_image_path, inspection_sessions(asset_id, technician_name)") \
        .gte("detected_at", cutoff) \
        .order("detected_at", desc=True) \
        .limit(limit) \
        .execute()
    return response.data



def _tab_recent(supabase):
    """🖼️ Recent Detections tab — paginated by session (5 per page)"""
    days = min(st.session_state.get("recent_days", 7), 365)
    col_info, col_btn = st.columns([3, 1])
    with col_info:
        st.caption(f"Showing records from the last {days} day(s). Images load on demand to save bandwidth.")
    with col_btn:
        if days < 365:
            if st.button("📅 Load older", key="load_older_recent"):
                st.session_state["recent_days"] = days + 7
                st.session_state["recent_page"] = 0
                st.rerun()
        else:
            st.caption("📅 Showing max 365 days")

    records = _fetch_recent_defects(supabase, days=days)

    if not records:
        if days >= 365:
            st.info("📭 No captures found in the last 365 days — this is the maximum search range.")
        else:
            st.info(f"📭 No captures in the last {days} day(s). Launch the camera station to begin inspecting, or click '📅 Load older' to see older records.")
        return

    # Group by session
    from collections import defaultdict
    sessions      = defaultdict(list)
    session_order = []
    for rec in records:
        sid = rec.get("session_id")
        if sid not in sessions:
            session_order.append(sid)
        sessions[sid].append(rec)

    total_sessions = len(session_order)
    total_pages    = max(1, (total_sessions + SESSIONS_PER_PAGE - 1) // SESSIONS_PER_PAGE)
    page           = st.session_state.get("recent_page", 0)
    page           = max(0, min(page, total_pages - 1))

    # Pagination controls — top
    p1, p2, p3 = st.columns([1, 2, 1])
    with p1:
        if st.button("← Previous", key="rec_prev", disabled=page == 0):
            st.session_state["recent_page"] = page - 1
            st.rerun()
    with p2:
        st.markdown(f"<div style='text-align:center;padding-top:6px;'>Page {page+1} of {total_pages} &nbsp;·&nbsp; {total_sessions} capture(s)</div>", unsafe_allow_html=True)
    with p3:
        if st.button("Next →", key="rec_next", disabled=page >= total_pages - 1):
            st.session_state["recent_page"] = page + 1
            st.rerun()

    st.markdown("---")

    # Show current page sessions
    start_idx = page * SESSIONS_PER_PAGE
    end_idx   = min(start_idx + SESSIONS_PER_PAGE, total_sessions)
    page_sessions = session_order[start_idx:end_idx]

    for sid in page_sessions:
        recs = sessions[sid]
        recs.sort(key=lambda r: r.get("confidence", 0), reverse=True)

        first        = recs[0]
        session_info = first.get("inspection_sessions") or {}
        asset_id     = session_info.get("asset_id", "Unknown")
        tech_name    = session_info.get("technician_name", "Unknown")
        timestamp    = _to_sgt(first.get("detected_at", ""))

        any_needs_review = any(
            r.get("confidence", 0) > 0 and
            r.get("confidence", 0) < (SCUFF_MARKS_THRESHOLD if r.get("defect_type") == "scuff marks" else CONFIDENCE_THRESHOLD)
            for r in recs
        )
        all_reviewed = all(r.get("reviewed", False) for r in recs)

        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(
                    f"**Asset:** {asset_id}  |  **Technician:** {tech_name}  |  **Detected:** {timestamp}"
                )
                for r in recs:
                    defect       = r.get("defect_type", "none")
                    conf         = r.get("confidence", 0)
                    needs_review = conf > 0 and conf < (SCUFF_MARKS_THRESHOLD if defect == "scuff marks" else CONFIDENCE_THRESHOLD)
                    status       = get_status_label(needs_review, defect, conf)
                    st.markdown(f"{DEFECT_EMOJI.get(defect, '🔍')} {status}")
            with col2:
                if all_reviewed:
                    st.markdown(
                        """<div style="background:#DCFCE7;border:1px solid #0A8A72;
                        border-radius:6px;padding:6px 10px;text-align:center;font-size:11px;">
                        <b style="color:#166534;">✅ REVIEWED</b></div>""",
                        unsafe_allow_html=True
                    )
                elif any_needs_review:
                    st.markdown(
                        """<div style="background:#FEF3C7;border:1px solid #F59E0B;
                        border-radius:6px;padding:6px 10px;text-align:center;font-size:11px;">
                        <b style="color:#92400E;">⚠️ REVIEW</b></div>""",
                        unsafe_allow_html=True
                    )

            # Lazy load images — show all unique captures in session
            show_key = f"show_images_{sid}"
            if not st.session_state.get(show_key, False):
                if st.button("🖼️ View Images", key=f"view_img_{sid}", use_container_width=True):
                    st.session_state[show_key] = True
                    st.rerun()
            else:
                # Get unique image pairs per capture (deduplicate by raw_image_path)
                seen_paths = set()
                unique_captures = []
                for r in sorted(recs, key=lambda x: x.get("detected_at", "")):
                    raw_path = r.get("raw_image_path")
                    if raw_path and raw_path not in seen_paths:
                        seen_paths.add(raw_path)
                        unique_captures.append(r)

                for i, capture in enumerate(unique_captures):
                    if len(unique_captures) > 1:
                        st.caption(f"**Capture {i+1} of {len(unique_captures)}**")
                    img1, img2 = st.columns(2)
                    with img1:
                        st.caption("Original")
                        raw_url = _signed_url(supabase, "raw-photos", capture.get("raw_image_path"))
                        if raw_url: st.image(raw_url)
                        else: st.caption("No image available")
                    with img2:
                        st.caption("YOLO Annotated")
                        ann_url = _signed_url(supabase, "annotated-photos", capture.get("annotated_image_path"))
                        if ann_url: st.image(ann_url)
                        else: st.caption("No annotation available")

            # Show physics panel for each unique defect type in session
            shown_defects = set()
            for r in recs:
                defect = r.get("defect_type", "none")
                conf   = r.get("confidence", 0)
                if defect not in shown_defects and defect not in ("none", "unknown"):
                    _get_physics_panel(defect, conf)
                    shown_defects.add(defect)

            if is_logged_in() and get_role() in ("management", "supervisor", "ic"):
                st.markdown("---")
                st.caption("🗑️ Select records to delete:")

                selected_ids = []
                for r in recs:
                    rec_id  = r.get("id")
                    defect  = r.get("defect_type", "none")
                    conf    = r.get("confidence", 0)
                    checked = st.checkbox(
                        f"{DEFECT_EMOJI.get(defect, '🔍')} {defect} ({conf:.0%})",
                        key=f"chk_recent_{rec_id}"
                    )
                    if checked:
                        selected_ids.append((rec_id, r.get("raw_image_path"), r.get("annotated_image_path"), r.get("session_id")))

                if selected_ids:
                    confirm_key = f"confirm_mass_delete_{sid}"
                    if not st.session_state.get(confirm_key, False):
                        if st.button(f"🗑️ Delete {len(selected_ids)} selected record(s)", key=f"mass_del_{sid}", type="primary", use_container_width=True):
                            st.session_state[confirm_key] = True
                            st.rerun()
                    else:
                        st.warning(f"⚠️ This will permanently delete {len(selected_ids)} record(s) and their images. Are you sure?")
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("✅ Yes, Delete", key=f"confirm_mass_yes_{sid}", type="primary"):
                                all_success = True
                                for rec_id, raw_path, ann_path, session_id in selected_ids:
                                    success, errors = _delete_record(supabase, rec_id, raw_path, ann_path, session_id)
                                    if not success:
                                        all_success = False
                                st.session_state.pop(confirm_key, None)
                                if all_success:
                                    st.success(f"🗑️ {len(selected_ids)} record(s) deleted.")
                                    load_defect_records.clear()
                                    st.rerun()
                                else:
                                    st.error("Some records could not be deleted.")
                        with c2:
                            if st.button("❌ Cancel", key=f"cancel_mass_{sid}"):
                                st.session_state.pop(confirm_key, None)
                                st.rerun()

    # Pagination controls — bottom
    st.markdown("---")
    b1, b2, b3 = st.columns([1, 2, 1])
    with b1:
        if st.button("← Previous", key="rec_prev_bot", disabled=page == 0):
            st.session_state["recent_page"] = page - 1
            st.rerun()
    with b2:
        st.markdown(f"<div style='text-align:center;padding-top:6px;'>Page {page+1} of {total_pages}</div>", unsafe_allow_html=True)
    with b3:
        if st.button("Next →", key="rec_next_bot", disabled=page >= total_pages - 1):
            st.session_state["recent_page"] = page + 1
            st.rerun()


def _tab_new_detection(supabase):
    """📷 Manual Upload — IC backup when DJI camera is unavailable"""

    # ── Context banner ─────────────────────────────────────────
    st.info(
        "📋 **When to use this tab:**\n\n"
        "Use this as a **backup** when the DJI wired or wireless camera station "
        "is unavailable. ICs can take a photo using their phone and upload it here "
        "for YOLO detection and record saving.\n\n"
        "For best results: photograph the collector shoe surface front-on with even "
        "lighting, no glare, and the shoe filling most of the frame."
    )

    # ── LRV data ───────────────────────────────────────────────
    LRV_MODELS = {
        "Test / Training Vehicle":  [0],
        "Non-Modified C810":        [2,3,6,8,11,14,16,17,19,20,24,29,32,37,38,39,40,41],
        "Modified C810":            [4,5,7,9,10,12,15,18,22,25,27,28,30,33,35,36],
        "New C810A":                list(range(42, 58)),
        "C810D":                    list(range(58, 70)),
    }
    CAB_ENDS  = ["A", "B"]
    POSITIONS = {"A": [1, 2], "B": [3, 4]}

    st.markdown("**Asset ID**")

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        lrv_model = st.selectbox("LRV Model", list(LRV_MODELS.keys()), key="mu_model", label_visibility="collapsed")
    with c2:
        lrv_nums  = [f"LRV{n:02d}" for n in LRV_MODELS.get(lrv_model, [])]
        lrv_num   = st.selectbox("LRV Number", lrv_nums, key="mu_num", label_visibility="collapsed")
    with c3:
        cab_end   = st.selectbox("Cab End", CAB_ENDS, key="mu_cab", label_visibility="collapsed")
    with c4:
        pos_opts  = POSITIONS.get(cab_end, [1, 2])
        position  = st.selectbox("Position", pos_opts, key="mu_pos", label_visibility="collapsed")
    with c5:
        side      = st.selectbox("Side", ["Upper (+)", "Lower (-)"], key="mu_side", label_visibility="collapsed")

    side_char = "+" if "Upper" in side else "-"
    asset_id  = f"CS-{lrv_num}-{side_char}{cab_end}{position}"
    st.caption(f"Asset ID: **{asset_id}**")

    # ── Shoe info ───────────────────────────────────────────────
    if asset_id:
        is_valid, error_msg = _validate_asset_id(supabase, asset_id)
        if not is_valid:
            st.error(error_msg)
        elif asset_id.upper().startswith("CS-"):
            try:
                result = supabase.table("collector_shoes") \
                    .select("shoe_id, condition, lrv_asset_id, rotation_status") \
                    .eq("shoe_id", asset_id.upper()).execute()
                if result.data:
                    shoe = result.data[0]
                    st.success(
                        f"✅ **{shoe['shoe_id']}** — "
                        f"LRV: {shoe['lrv_asset_id']} | "
                        f"Condition: {shoe['condition']} | "
                        f"Rotation: {shoe['rotation_status'].replace('_', ' ')}"
                    )
            except:
                pass

        has_dup, dup_msg = _check_duplicate(supabase, asset_id)
        if has_dup:
            st.warning(dup_msg)

    st.markdown("---")

    # ── File uploader ───────────────────────────────────────────
    st.markdown("**Upload Inspection Photo**")
    st.caption("Accepted formats: JPG, JPEG, PNG, BMP, WEBP · Max 200MB")
    uploaded = st.file_uploader(
        "Upload inspection photo",
        type=["jpg", "jpeg", "png", "bmp", "webp"],
        label_visibility="collapsed"
    )

    # Preview — only show thumbnail to save egress
    if uploaded:
        st.image(uploaded, caption="Preview", width=320)

    # ── Empty state ─────────────────────────────────────────────
    if not uploaded:
        st.markdown(
            """<div style="background:#F8FAFC;border:2px dashed #CBD5E1;border-radius:12px;
            padding:32px;text-align:center;color:#64748B;margin:16px 0;">
            <div style="font-size:36px;">📸</div>
            <div style="font-size:15px;font-weight:600;margin:8px 0;">No photo uploaded yet</div>
            <div style="font-size:13px;">Upload a photo of the collector shoe surface above to run YOLO detection</div>
            </div>""",
            unsafe_allow_html=True
        )
        return

    # ── Run detection ───────────────────────────────────────────
    if st.button("🚀 Run Detection & Save", type="primary", use_container_width=True):
        is_valid, error_msg = _validate_asset_id(supabase, asset_id)
        if not is_valid:
            st.error(error_msg)
            return

        has_dup, dup_msg = _check_duplicate(supabase, asset_id)
        if has_dup:
            if not st.session_state.get(f"confirm_dup_{asset_id}", False):
                st.warning(f"{dup_msg}")
                st.session_state[f"confirm_dup_{asset_id}"] = True
                return
            else:
                st.session_state[f"confirm_dup_{asset_id}"] = False

        with st.spinner("Running YOLO detection..."):
            try:
                result = _run_detection_pipeline(supabase, asset_id, uploaded)
                if result.get("needs_review"):
                    st.warning(
                        f"⚠️ Detection saved but flagged for review — "
                        f"confidence {result.get('confidence', 0):.0%} is below {CONFIDENCE_THRESHOLD:.0%}."
                    )
                else:
                    st.success(
                        f"✅ **{result.get('defect', 'none')}** detected at "
                        f"**{result.get('confidence', 0):.0%}** confidence."
                    )
                load_defect_records.clear()
            except Exception as e:
                st.error(f"Something went wrong: {e}")


def _generate_word_report(supabase, records_df, date_from, date_to, progress_bar, status_text):
    """
    Generates a Word (.docx) inspection report grouped by Asset ID then session.
    Shows all detections per session and all unique capture images.
    """
    import requests
    import io
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()

    # ── Page setup ─────────────────────────────────────────────
    section = doc.sections[0]
    section.page_width    = Cm(21)
    section.page_height   = Cm(29.7)
    section.top_margin    = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin   = Cm(2.5)
    section.right_margin  = Cm(2.5)

    def set_cell_bg(cell, hex_color):
        tc   = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd  = OxmlElement("w:shd")
        shd.set(qn("w:val"),   "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"),  hex_color)
        tcPr.append(shd)

    def add_horizontal_rule(doc):
        p   = doc.add_paragraph()
        pPr = p._p.get_or_add_pPr()
        pb  = OxmlElement("w:pBdr")
        bot = OxmlElement("w:bottom")
        bot.set(qn("w:val"),   "single")
        bot.set(qn("w:sz"),    "6")
        bot.set(qn("w:space"), "1")
        bot.set(qn("w:color"), "C8D0D8")
        pb.append(bot)
        pPr.append(pb)

    # ── Cover page ─────────────────────────────────────────────
    status_text.text("Building report cover page...")
    progress_bar.progress(5)

    title = doc.add_heading("LRT Collector Shoe", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if title.runs:
        title.runs[0].font.size = Pt(24)
        title.runs[0].font.color.rgb = RGBColor(0x0A, 0x8A, 0x72)

    sub = doc.add_heading("Visual Inspection Report", level=2)
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if sub.runs:
        sub.runs[0].font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)

    doc.add_paragraph()

    meta = doc.add_table(rows=5, cols=2)
    meta.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_data = [
        ("Report Period",   f"{date_from} to {date_to}"),
        ("Generated",       _to_sgt(datetime.utcnow().isoformat() + "+00:00")),
        ("Total Captures",  str(records_df["Session ID"].nunique())),
        ("Total Records",   str(len(records_df))),
        ("Shoes Inspected", str(records_df["Asset ID"].nunique())),
    ]
    for i, (label, value) in enumerate(meta_data):
        row = meta.rows[i]
        row.cells[0].text = label
        row.cells[1].text = value
        set_cell_bg(row.cells[0], "F0FDF4")
        if row.cells[0].paragraphs[0].runs:
            row.cells[0].paragraphs[0].runs[0].font.bold = True

    doc.add_page_break()

    # ── Summary ────────────────────────────────────────────────
    status_text.text("Adding summary statistics...")
    progress_bar.progress(10)

    doc.add_heading("Summary", level=1)
    abnormal_count    = len(records_df[records_df["Abnormal Defect"] == "YES"])
    avg_conf          = records_df["Confidence (%)"].mean()
    confirmed_df      = records_df[records_df["Verdict"] == "Confirmed"]
    auto_confirmed    = len(confirmed_df[confirmed_df["Reviewer Notes"].str.startswith("Auto-confirmed", na=False)])
    manually_reviewed = len(confirmed_df[~confirmed_df["Reviewer Notes"].str.startswith("Auto-confirmed", na=False)])

    summary_data = [
        ("Total Captures",      str(records_df["Session ID"].nunique())),
        ("Total Records",       str(len(records_df))),
        ("Shoes Inspected",     str(records_df["Asset ID"].nunique())),
        ("Average Confidence",  f"{avg_conf:.1f}%"),
        ("Abnormal Defects",    str(abnormal_count)),
        ("Auto-Confirmed",      f"{auto_confirmed} (system ≥85% threshold)"),
        ("Manually Reviewed",   f"{manually_reviewed} (human verification)"),
    ]

    summary_table = doc.add_table(rows=len(summary_data), cols=2)
    summary_table.style = "Table Grid"
    for i, (label, value) in enumerate(summary_data):
        row = summary_table.rows[i]
        row.cells[0].text = label
        row.cells[1].text = value
        set_cell_bg(row.cells[0], "F8FAFC")
        if row.cells[0].paragraphs[0].runs:
            row.cells[0].paragraphs[0].runs[0].font.bold = True
        if label == "Abnormal Defects" and int(value.split()[0]) > 0:
            if row.cells[1].paragraphs[0].runs:
                row.cells[1].paragraphs[0].runs[0].font.color.rgb = RGBColor(0xC9, 0x38, 0x2A)
            set_cell_bg(row.cells[1], "FEE2E2")
        if label == "Auto-Confirmed":
            set_cell_bg(row.cells[1], "F0FDF4")
        if label == "Manually Reviewed":
            set_cell_bg(row.cells[1], "DBEAFE")

    doc.add_page_break()

    # ── Inspection frequency ───────────────────────────────────
    doc.add_heading("Inspection Frequency", level=1)
    freq_df = records_df.groupby("Asset ID").agg(
        Inspections=("Session ID", "nunique"),
        Last_Raw=("_detected_raw", "max"),
    ).reset_index()
    freq_df["Last Inspection (SGT)"] = freq_df["Last_Raw"].apply(_to_sgt)

    freq_table = doc.add_table(rows=len(freq_df)+1, cols=3)
    freq_table.style = "Table Grid"
    headers = ["Asset ID", "Inspections", "Last Inspection (SGT)"]
    for j, h in enumerate(headers):
        freq_table.rows[0].cells[j].text = h
        set_cell_bg(freq_table.rows[0].cells[j], "F0FDF4")
        if freq_table.rows[0].cells[j].paragraphs[0].runs:
            freq_table.rows[0].cells[j].paragraphs[0].runs[0].font.bold = True
    for i, row_data in freq_df.iterrows():
        freq_table.rows[i+1].cells[0].text = str(row_data["Asset ID"])
        freq_table.rows[i+1].cells[1].text = str(row_data["Inspections"])
        freq_table.rows[i+1].cells[2].text = str(row_data["Last Inspection (SGT)"])

    doc.add_page_break()

    # ── Records grouped by Asset ID then session ───────────────
    grouped = records_df.groupby("Asset ID")
    total_assets = len(grouped)
    asset_count  = 0

    for asset_id, asset_df in grouped:
        asset_count += 1
        progress_pct = 10 + int((asset_count / total_assets) * 80)
        status_text.text(f"Processing {asset_id} ({asset_count}/{total_assets})...")
        progress_bar.progress(progress_pct)

        doc.add_heading(f"Asset: {asset_id}", level=1)

        asset_df = asset_df.copy().sort_values("_detected_raw")
        asset_df["Session ID"] = asset_df["Session ID"].fillna(asset_df["_detected_raw"])
        session_groups = asset_df.groupby("Session ID", sort=False)

        for session_id, session_df in session_groups:
            if session_df.empty:
                continue
            first_rec = session_df.iloc[0]
            doc.add_heading(f"{first_rec['Detected (SGT)']}", level=2)

            for _, rec in session_df.iterrows():
                details = [
                    ("Technician",    rec["Technician"]),
                    ("Defect Type",   rec["Defect Type"].title()),
                    ("Abnormal",      rec["Abnormal Defect"]),
                    ("Confidence",    f"{rec['Confidence (%)']:.0f}%"),
                    ("Status",        rec["Status"]),
                    ("Verdict",       rec["Verdict"]),
                    ("Reviewed (SGT)",rec["Reviewed (SGT)"]),
                ]

                det_table = doc.add_table(rows=len(details), cols=2)
                det_table.style = "Table Grid"
                for i, (label, value) in enumerate(details):
                    row = det_table.rows[i]
                    row.cells[0].text = label
                    row.cells[1].text = str(value)
                    set_cell_bg(row.cells[0], "F8FAFC")
                    if row.cells[0].paragraphs[0].runs:
                        row.cells[0].paragraphs[0].runs[0].font.bold = True
                    if label == "Abnormal" and value == "YES":
                        if row.cells[1].paragraphs[0].runs:
                            row.cells[1].paragraphs[0].runs[0].font.color.rgb = RGBColor(0xC9, 0x38, 0x2A)
                        set_cell_bg(row.cells[1], "FEE2E2")
                    if label == "Verdict" and value == "Confirmed":
                        if row.cells[1].paragraphs[0].runs:
                            row.cells[1].paragraphs[0].runs[0].font.color.rgb = RGBColor(0x0A, 0x8A, 0x72)

                if rec["Reviewer Notes"]:
                    doc.add_paragraph()
                    note_p = doc.add_paragraph()
                    note_p.add_run("Reviewer Notes: ").bold = True
                    note_p.add_run(str(rec["Reviewer Notes"]))

                if rec["Physics Action"]:
                    pa_p = doc.add_paragraph()
                    pa_p.add_run("Physics Action: ").bold = True
                    pa_p.add_run(str(rec["Physics Action"]))

                doc.add_paragraph()

            # Show all unique annotated images per session
            seen_paths = set()
            unique_images = []
            for _, rec in session_df.sort_values("_detected_raw").iterrows():
                ann_path = rec.get("_annotated_path", "")
                if ann_path and ann_path not in seen_paths:
                    seen_paths.add(ann_path)
                    unique_images.append(ann_path)

            for img_idx, ann_path in enumerate(unique_images):
                try:
                    signed  = supabase.storage.from_("annotated-photos").create_signed_url(ann_path, 60)
                    img_url = signed.get("signedURL") or signed.get("signed_url", "")
                    if img_url:
                        img_resp = requests.get(img_url, timeout=10)
                        if img_resp.status_code == 200:
                            img_bytes = io.BytesIO(img_resp.content)
                            if len(unique_images) > 1:
                                cap_label = f"Figure: YOLO Annotated Image — Capture {img_idx+1} of {len(unique_images)}"
                            else:
                                cap_label = "Figure: YOLO Annotated Image"
                            img_p = doc.add_paragraph()
                            img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            img_p.add_run().add_picture(img_bytes, width=Inches(5.5))
                            cap = doc.add_paragraph(cap_label)
                            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            cap.runs[0].font.size = Pt(9)
                            cap.runs[0].font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
                except Exception:
                    doc.add_paragraph(f"[Annotated image {img_idx+1} unavailable]")

            add_horizontal_rule(doc)

        doc.add_page_break()

    # ── Detection Frequency Chart ───────────────────────────────
    status_text.text("Adding detection frequency chart...")
    progress_bar.progress(88)

    doc.add_heading("Detection Frequency by Defect Type", level=1)
    doc.add_paragraph(
        "Shows how often each defect type has been detected across all inspections. "
        "Useful for identifying which defects are most common across the fleet."
    ).runs[0].font.size = Pt(10)

    try:
        import plotly.express as _px
        freq_df = records_df.groupby("Defect Type").size().reset_index(name="Count")
        freq_df = freq_df.sort_values("Count", ascending=False)
        color_map = {
            "wear": "#E8920A", "scuff marks": "#1A6FB5",
            "crack": "#C9382A", "corrosion": "#6B21A8", "arcing": "#DC2626",
        }
        colors = [color_map.get(d.lower(), "#64748B") for d in freq_df["Defect Type"]]
        fig_freq = _px.bar(
            freq_df, x="Defect Type", y="Count",
            color="Defect Type", color_discrete_sequence=colors,
        )
        fig_freq.update_layout(
            height=300, width=600, showlegend=False,
            plot_bgcolor="white", paper_bgcolor="white",
            margin=dict(l=60, r=20, t=30, b=60),
            xaxis=dict(title=dict(text="Defect Type", standoff=15)),
            yaxis=dict(title=dict(text="Number of Detections", standoff=15)),
        )
        img_bytes_freq = io.BytesIO(fig_freq.to_image(format="png", scale=2))
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(img_bytes_freq, width=Inches(5.5))

        # Summary
        top_defect = freq_df.iloc[0]["Defect Type"] if not freq_df.empty else "none"
        top_count  = int(freq_df.iloc[0]["Count"]) if not freq_df.empty else 0
        total_det  = int(freq_df["Count"].sum())
        summary_p  = doc.add_paragraph()
        summary_p.add_run(f"Total Detections: {total_det}  ·  Most Frequent: {top_defect} ({top_count} detections)").bold = True
        note_p = doc.add_paragraph(
            "⚠️ Defect frequency reflects how often each defect type was detected — not physical severity."
        )
        note_p.runs[0].font.size = Pt(9)
        note_p.runs[0].font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
    except Exception as e:
        doc.add_paragraph(f"[Detection frequency chart unavailable: {e}]")

    doc.add_page_break()

    # ── Session Frequency Chart ─────────────────────────────────
    status_text.text("Adding session frequency chart...")
    progress_bar.progress(91)

    doc.add_heading("Inspection Session Frequency", level=1)
    doc.add_paragraph(
        "Tracks how often inspections were conducted over the report period. "
        "Regular inspections indicate good maintenance compliance."
    ).runs[0].font.size = Pt(10)

    try:
        import pandas as pd
        import plotly.express as _px
        if "_detected_raw" in records_df.columns:
            sess_df = records_df.drop_duplicates(subset=["Session ID"]).copy()
            sess_df["_detected_raw"] = pd.to_datetime(sess_df["_detected_raw"])
            sess_df["Week"] = sess_df["_detected_raw"].dt.to_period("W").apply(lambda x: x.start_time)
            sess_week = sess_df.groupby("Week").size().reset_index(name="Sessions")
            sess_week["Week"] = pd.to_datetime(sess_week["Week"])
            fig_sess = _px.line(
                sess_week, x="Week", y="Sessions", markers=True,
                color_discrete_sequence=["#0A8A72"],
            )
            fig_sess.update_layout(
                height=300, width=600,
                plot_bgcolor="white", paper_bgcolor="white",
                margin=dict(l=60, r=20, t=30, b=60),
                xaxis=dict(title=dict(text="Week", standoff=15)),
                yaxis=dict(title=dict(text="Number of Sessions", standoff=15)),
            )
            img_bytes_sess = io.BytesIO(fig_sess.to_image(format="png", scale=2))
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(img_bytes_sess, width=Inches(5.5))

            # Summary
            total_sess    = len(sess_df)
            avg_per_week  = round(sess_week["Sessions"].mean(), 1)
            most_active   = sess_week.loc[sess_week["Sessions"].idxmax(), "Week"].strftime("Week of %d %b %Y")
            most_active_n = int(sess_week["Sessions"].max())
            summary_s = doc.add_paragraph()
            summary_s.add_run(
                f"Total Sessions: {total_sess}  ·  Avg per Week: {avg_per_week}  ·  "
                f"Most Active: {most_active} ({most_active_n} sessions)"
            ).bold = True
            note_s = doc.add_paragraph(
                "⚠️ Each session represents one 3-angle inspection. Regular sessions indicate good inspection compliance."
            )
            note_s.runs[0].font.size = Pt(9)
            note_s.runs[0].font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
    except Exception as e:
        doc.add_paragraph(f"[Session frequency chart unavailable: {e}]")

    doc.add_page_break()

    # ── Per-LRV Defect Heatmap ──────────────────────────────────
    status_text.text("Adding defect heatmap...")
    progress_bar.progress(94)

    doc.add_heading("Per-LRV Defect Heatmap", level=1)
    doc.add_paragraph(
        "Fleet-wide overview showing the most severe defect detected per shoe position. "
        "— indicates the shoe has not been inspected during the report period."
    ).runs[0].font.size = Pt(10)

    try:
        import pandas as pd
        SEVERITY_RANK = {
            "none": 0, "scuff marks": 1, "wear": 2,
            "corrosion": 3, "crack": 3, "arcing": 4,
        }
        SEVERITY_LABEL = {
            0: "None", 1: "Scuff Marks", 2: "Wear",
            3: "Crack/Corrosion", 4: "Arcing",
        }
        SEVERITY_COLOR = {
            0: (0xDC, 0xFC, 0xE7), 1: (0xFE, 0xF9, 0xC3),
            2: (0xFE, 0xD7, 0xAA), 3: (0xFE, 0xCA, 0xCA), 4: (0xDC, 0x26, 0x26),
        }

        def extract_lrv_pos(asset_id):
            try:
                parts = asset_id.split("-")
                lrv   = parts[1]
                pos   = asset_id[len(f"CS-{lrv}-"):]
                return lrv, pos
            except:
                return None, None

        hm_df = records_df.copy()
        hm_df[["lrv", "position"]] = hm_df["Asset ID"].apply(
            lambda x: pd.Series(extract_lrv_pos(x))
        )
        hm_df = hm_df.dropna(subset=["lrv", "position"])
        hm_df["severity_rank"] = hm_df["Defect Type"].apply(
            lambda x: SEVERITY_RANK.get(x.lower(), 0) if isinstance(x, str) else 0
        )
        worst = hm_df.groupby(["lrv", "position"])["severity_rank"].max().reset_index()

        lrvs      = sorted(worst["lrv"].unique().tolist())
        positions = ["+A1", "-A1", "+A2", "-A2", "+B3", "-B3", "+B4", "-B4"]

        hm_table = doc.add_table(rows=len(lrvs)+1, cols=len(positions)+1)
        hm_table.style = "Table Grid"

        # Header row
        hm_table.rows[0].cells[0].text = "LRV"
        set_cell_bg(hm_table.rows[0].cells[0], "E2E8F0")
        for j, pos in enumerate(positions):
            hm_table.rows[0].cells[j+1].text = pos
            set_cell_bg(hm_table.rows[0].cells[j+1], "E2E8F0")
            if hm_table.rows[0].cells[j+1].paragraphs[0].runs:
                hm_table.rows[0].cells[j+1].paragraphs[0].runs[0].font.bold = True

        # Data rows
        for i, lrv in enumerate(lrvs):
            hm_table.rows[i+1].cells[0].text = lrv
            if hm_table.rows[i+1].cells[0].paragraphs[0].runs:
                hm_table.rows[i+1].cells[0].paragraphs[0].runs[0].font.bold = True
            for j, pos in enumerate(positions):
                match = worst[(worst["lrv"] == lrv) & (worst["position"] == pos)]
                cell = hm_table.rows[i+1].cells[j+1]
                if not match.empty:
                    rank  = int(match.iloc[0]["severity_rank"])
                    label = SEVERITY_LABEL.get(rank, "—")
                    r, g, b = SEVERITY_COLOR.get(rank, (0xF8, 0xFA, 0xFC))
                    cell.text = label
                    set_cell_bg(cell, f"{r:02X}{g:02X}{b:02X}")
                else:
                    cell.text = "—"
                    set_cell_bg(cell, "F8FAFC")
                if cell.paragraphs[0].runs:
                    cell.paragraphs[0].runs[0].font.size = Pt(8)

        for row in hm_table.rows:
            for cell in row.cells:
                if cell.paragraphs[0].runs:
                    cell.paragraphs[0].runs[0].font.size = Pt(8)

        # Legend
        legend_p = doc.add_paragraph()
        legend_p.add_run("Legend:  ").bold = True
        legend_items = [
            ("None", "DCFCE7"),
            ("Scuff Marks", "FEF9C3"),
            ("Wear", "FED7AA"),
            ("Crack / Corrosion", "FECACA"),
            ("Arcing", "DC2626"),
            ("— Not inspected", "F8FAFC"),
        ]
        for label, _ in legend_items:
            legend_p.add_run(f"{label}  ")

        note_hm = doc.add_paragraph(
            "⚠️ Heatmap shows most severe defect per shoe position. "
            "Physical depth gauge measurement required for accurate severity assessment."
        )
        note_hm.runs[0].font.size = Pt(9)
        note_hm.runs[0].font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
    except Exception as e:
        doc.add_paragraph(f"[Defect heatmap unavailable: {e}]")

    doc.add_page_break()

    # ── Disclaimer ─────────────────────────────────────────────
    doc.add_heading("Disclaimer", level=1)
    disclaimer = doc.add_paragraph(
        "This report is generated automatically by the LRT Collector Shoe Visual Inspection System. "
        "Confidence scores reflect the YOLO v11 model's visual assessment and should be verified "
        "against physical depth gauge measurements before maintenance decisions are made. "
        "Physical measurements remain the ground truth for wear severity classification."
    )
    disclaimer.runs[0].font.size = Pt(9)
    disclaimer.runs[0].font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    # ── Save ───────────────────────────────────────────────────
    status_text.text("Finalising report...")
    progress_bar.progress(95)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    progress_bar.progress(100)
    status_text.text("✅ Report ready!")
    return buf.read()


def _tab_export(supabase):
    """📥 Export / Report tab — engineering report with meaningful metrics"""
    st.markdown("#### 📥 Export Defect Records")
    st.caption("Engineering report — inspection compliance, wear severity progression, defect type breakdown and audit trail.")

    # ── Filters ────────────────────────────────────────────────
    with st.expander("🔍 Filters", expanded=True):
        f1, f2 = st.columns(2)
        f3, f4 = st.columns(2)
        from datetime import date
        date_from     = f1.date_input("From Date", value=date(2026, 1, 1))
        date_to       = f2.date_input("To Date",   value=date.today())
        defect_filter = f3.selectbox("Defect Type", ["All", "wear", "crack", "corrosion", "arcing", "none"])
        asset_filter  = f4.text_input("Asset ID (optional)", placeholder="e.g. CS-LRV00-+A1")

    # ── Fetch records ──────────────────────────────────────────
    try:
        import pandas as pd

        all_data = supabase.table("defect_records") \
            .select("*, inspection_sessions(asset_id, technician_name)") \
            .gt("confidence", 0) \
            .gte("detected_at", f"{date_from}T00:00:00") \
            .lte("detected_at", f"{date_to}T23:59:59") \
            .order("detected_at", desc=True) \
            .execute()

        all_records = all_data.data or []

        if not all_records:
            st.info("📭 No records found for the selected date range. Try expanding the date range or adjusting the filters.")
            return

        # ── Build dataframe ────────────────────────────────────
        rows = []
        for rec in all_records:
            session_info = rec.get("inspection_sessions") or {}
            asset_id     = session_info.get("asset_id", "Unknown")
            tech_name    = session_info.get("technician_name", "Unknown")
            defect       = rec.get("defect_type", "none")
            conf         = rec.get("confidence", 0.0)
            detected_at  = _to_sgt(rec.get("detected_at", ""))
            reviewed_at  = _to_sgt(rec.get("reviewed_at", "")) if rec.get("reviewed_at") else "N/A"
            verdict      = rec.get("reviewer_verdict", "not reviewed") or "not reviewed"
            notes        = rec.get("reviewer_notes", "") or ""
            detected_raw = rec.get("detected_at", "")

            if rec.get("reviewed"):
                status = "Reviewed"
            elif conf < CONFIDENCE_THRESHOLD:
                status = f"Flagged (<{CONFIDENCE_THRESHOLD*100:.0f}%)"
            else:
                status = f"High Confidence (>={CONFIDENCE_THRESHOLD*100:.0f}%)"

            # Only flag structurally concerning defects as abnormal
            # Wear and scuff marks are normal from sliding contact — not abnormal
            is_abnormal = defect not in ("wear", "scuff marks", "none", "unknown")

            # Physics action
            physics_action = ""
            if defect in PHYSICS_KB and defect not in ("none", "unknown"):
                kb = PHYSICS_KB.get(defect)
                if kb and kb.get("omm_action"):
                    physics_action = kb["omm_action"].strip()

            rows.append({
                "Session ID":        rec.get("session_id", ""),
                "Asset ID":          asset_id,
                "Technician":        tech_name,
                "Defect Type":       defect,
                "Abnormal Defect":   "YES" if is_abnormal else "No",
                "Confidence (%)":    round(conf * 100, 1),
                "Status":            status,
                "Verdict":           verdict.replace("_", " ").title(),
                "Reviewer Notes":    notes,
                "Physics Action":    physics_action,
                "Detected (SGT)":    detected_at,
                "Reviewed (SGT)":    reviewed_at,
                "_detected_raw":     detected_raw,
                "_annotated_path":   rec.get("annotated_image_path", ""),
            })

        df = pd.DataFrame(rows)

        # Apply filters
        if defect_filter != "All":
            df = df[df["Defect Type"] == defect_filter]
        if asset_filter.strip():
            df = df[df["Asset ID"].str.contains(asset_filter.strip(), case=False)]

        if df.empty:
            st.info("No records match the selected filters.")
            return

        # ── SECTION 1: Summary Metrics ─────────────────────────
        st.markdown("---")
        st.markdown("**📊 Summary**")
        total_sessions = df["Session ID"].nunique()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Inspections",   total_sessions,
                  help="Number of unique capture sessions")
        m2.metric("Shoes Inspected",     df["Asset ID"].nunique())
        m3.metric("⚠️ Abnormal Defects", len(df[df["Abnormal Defect"] == "YES"]),
                  help="Non-wear defects (crack, corrosion, arcing) — require immediate attention")
        m4.metric("Avg Confidence",      f"{df['Confidence (%)'].mean():.1f}%")

        # ── SECTION 2: Inspection Compliance ──────────────────
        st.markdown("---")
        st.markdown("**🗓️ Inspection Frequency per Shoe**")
        st.caption("Shows how many times each shoe was inspected in the selected period and days since last inspection.")

        freq_df = df.groupby("Asset ID").agg(
            Inspections=("Session ID", "nunique"),
            Last_Inspection=("_detected_raw", "max"),
        ).reset_index()

        freq_df["Last Inspection (SGT)"] = freq_df["Last_Inspection"].apply(_to_sgt)
        try:
            freq_df["Days Since Last"] = (
                pd.Timestamp.now(tz="UTC") -
                pd.to_datetime(freq_df["Last_Inspection"], format='ISO8601')
            ).dt.days
        except:
            freq_df["Days Since Last"] = "—"

        freq_df = freq_df[["Asset ID", "Inspections", "Last Inspection (SGT)", "Days Since Last"]]
        st.dataframe(freq_df, hide_index=True)

        # ── SECTION 3: Defect Type Breakdown ──────────────────
        st.markdown("---")
        st.markdown("**🔍 Defect Type Breakdown**")
        st.caption("Wear and scuff marks are expected (constant rail contact). Crack, corrosion and arcing are abnormal and require immediate attention.")

        breakdown = df.groupby("Defect Type").agg(
            Count=("Asset ID", "count"),
            Avg_Confidence=("Confidence (%)", "mean"),
        ).reset_index()
        breakdown["Avg Confidence (%)"] = breakdown["Avg_Confidence"].round(1)
        breakdown["Abnormal"] = breakdown["Defect Type"].apply(
            lambda x: "Immediate attention required" if x not in ("wear", "scuff marks", "none", "unknown") else "Expected"
        )
        breakdown = breakdown[["Defect Type", "Count", "Avg Confidence (%)", "Abnormal"]]
        st.dataframe(breakdown, hide_index=True)

        # Alert for abnormal defects
        abnormal_df = df[df["Abnormal Defect"] == "YES"]
        if not abnormal_df.empty:
            st.error(
                f"⚠️ **{len(abnormal_df)} abnormal defect(s) detected** — "
                f"{', '.join(abnormal_df['Asset ID'].unique().tolist())} require immediate engineering inspection."
            )

        # ── SECTION 4: Full Audit Trail ────────────────────────
        st.markdown("---")
        st.markdown("**📋 Full Audit Trail**")
        st.caption("Complete inspection log — technician, timestamp, defect, confidence, verdict and reviewer notes.")

        display_cols = [
            "Asset ID", "Technician", "Defect Type", "Abnormal Defect",
            "Confidence (%)", "Status", "Verdict", "Reviewer Notes", "Detected (SGT)"
        ]
        st.dataframe(df[display_cols], hide_index=True, height=300)

        # ── Download CSV ───────────────────────────────────────
        st.markdown("---")
        export_df = df.drop(columns=["_detected_raw", "_annotated_path"])
        csv_data  = export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            label="⬇️ Download CSV Report",
            data=csv_data,
            file_name=f"defect_report_{date_from}_to_{date_to}.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.markdown("---")
        st.markdown("**📄 Word Report (with annotated images)**")
        st.caption("Generates a formatted Word document grouped by Asset ID, including annotated inspection images.")
        if st.button("📄 Generate Word Report", type="primary", use_container_width=True):
            progress_bar = st.progress(0)
            status_text  = st.empty()
            try:
                word_bytes = _generate_word_report(
                    supabase, df, date_from, date_to, progress_bar, status_text
                )
                st.download_button(
                    label="⬇️ Download Word Report",
                    data=word_bytes,
                    file_name=f"inspection_report_{date_from}_to_{date_to}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    type="primary",
                    use_container_width=True,
                )
            except Exception as e:
                import traceback
                progress_bar.empty()
                status_text.empty()
                st.error(f"Could not generate Word report: {e}")
                st.code(traceback.format_exc())

    except Exception as e:
        st.error(f"Could not load export data: {e}")


def _tab_retrain(supabase):
    """🔄 Auto-Retrain tab — management only"""
    st.markdown("#### 🔄 Auto-Retrain Pipeline")
    st.caption(
        "Tracks new captures since the last Roboflow retraining. "
        f"Retraining is suggested after every {RETRAIN_THRESHOLD} new captures."
    )

    # ── Current status ─────────────────────────────────────────
    count = get_capture_count(supabase)

    pct   = min(int((count / RETRAIN_THRESHOLD) * 100), 100)

    if count >= RETRAIN_THRESHOLD:
        st.markdown(
            f"""<div style="background:#FEF3C7;border:1px solid #F59E0B;
            border-radius:12px;padding:16px 20px;margin-bottom:16px;">
            <div style="font-size:16px;font-weight:700;color:#92400E;">
            🔔 Retrain Recommended</div>
            <div style="font-size:14px;color:#78350F;margin-top:6px;">
            <b>{count}</b> new captures collected since last retrain — 
            threshold of {RETRAIN_THRESHOLD} reached.</div>
            </div>""",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f"""<div style="background:#F0FDF4;border:1px solid #0A8A72;
            border-radius:12px;padding:16px 20px;margin-bottom:16px;">
            <div style="font-size:16px;font-weight:700;color:#166534;">
            ✅ Model Up to Date</div>
            <div style="font-size:14px;color:#166534;margin-top:6px;">
            <b>{count}</b> of {RETRAIN_THRESHOLD} new captures collected 
            since last retrain.</div>
            </div>""",
            unsafe_allow_html=True
        )

    # Progress bar
    st.progress(pct)
    st.caption(f"{count}/{RETRAIN_THRESHOLD} captures — {pct}% to next retrain")

    st.markdown("---")

    # ── Retrain steps ──────────────────────────────────────────
    st.markdown("**📋 Retrain Workflow**")
    st.markdown(
        "1. New captures are automatically tracked from both wired and wireless stations\n"
        f"2. When {RETRAIN_THRESHOLD} new captures are collected, retraining is recommended\n"
        "3. Upload and annotate new images in Roboflow (review auto-labels)\n"
        "4. Click **Trigger Retrain** below to start training\n"
        "5. Once training completes, update `MODEL_PATH` in `yolo_detect.py` to the new version\n"
        "6. Capture count resets automatically"
    )

    st.markdown("---")

    # ── Trigger retrain button ─────────────────────────────────
    st.markdown("**🚀 Trigger Retraining**")
    st.caption(
        "Make sure you have reviewed and approved annotations in Roboflow before triggering. "
        "Training typically takes 10-30 minutes."
    )

    confirm_key = "confirm_retrain"
    if not st.session_state.get(confirm_key, False):
        if st.button(
            "🔄 Trigger Roboflow Retrain",
            type="primary",
            use_container_width=True,
            disabled=count == 0
        ):
            st.session_state[confirm_key] = True
            st.rerun()
    else:
        st.warning(
            f"⚠️ This will reset the capture counter and log a retrain event. "
            "Make sure all new images are annotated and approved in Roboflow before proceeding."
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Yes, Proceed", type="primary"):
                with st.spinner("Processing..."):
                    success, msg = trigger_roboflow_retrain(
                        supabase,
                        triggered_by=st.session_state.get("user_id", "management")
                    )
                st.session_state.pop(confirm_key, None)
                if success:
                    st.success(f"✅ {msg}")
                    st.info(
                        "Training has started on Roboflow. Check your Roboflow dashboard "
                        "for progress. Once complete, update `MODEL_PATH` in `yolo_detect.py`."
                    )
                else:
                    # Free plan limitation — reset counter manually and log
                    try:
                        reset_capture_count(
                            supabase,
                            triggered_by=st.session_state.get("user_id", "management"),
                            version_note="manual"
                        )
                        counter_reset = True
                    except Exception as reset_err:
                        counter_reset = False
                        st.error(f"Counter reset failed: {reset_err}")

                    st.warning(
                        "⚠️ **Roboflow API training not available on free plan.**\n\n"
                        f"{'✅ Capture counter has been reset to 0.' if counter_reset else '❌ Counter reset failed — please reset manually in Supabase.'} "
                        "Please train manually in Roboflow:"
                    )
                    st.markdown(
                        f"👉 [Open Roboflow Project](https://app.roboflow.com/iman-irhash/{ROBOFLOW_PROJECT}) "
                        "→ Select latest version → Click **Train**"
                    )
                    st.info(
                        "Once training completes, update `MODEL_PATH` in `core/yolo_detect.py` "
                        "to the new version number."
                    )
                    import time; time.sleep(1)
                    st.rerun()
        with c2:
            if st.button("❌ Cancel"):
                st.session_state.pop(confirm_key, None)
                st.rerun()

    st.markdown("---")

    # ── Retrain history ────────────────────────────────────────
    st.markdown("**📜 Retrain History**")
    try:
        history = supabase.table("retrain_history") \
            .select("*") \
            .order("triggered_at", desc=True) \
            .limit(10) \
            .execute()
        if history.data:
            import pandas as pd
            hist_df = pd.DataFrame(history.data)
            hist_df["triggered_at"] = hist_df["triggered_at"].apply(_to_sgt)
            st.dataframe(
                hist_df[["triggered_at", "image_count", "roboflow_version", "status", "notes"]],
                hide_index=True
            )
        else:
            st.info("No retrain history yet.")
    except Exception as e:
        st.error(f"Could not load retrain history: {e}")


# ── Main show() ────────────────────────────────────────────────
def show():
    st.markdown("## 🔍 Defect Viewer")

    # ── Persistent success message after review submission ─────
    if "review_success_msg" in st.session_state:
        st.success(st.session_state.pop("review_success_msg"))

    # ── Model info banner ──────────────────────────────────────
    model_info = get_model_info()
    trained    = model_info.get("trained", False)
    model_name = model_info.get("name", "Unknown")
    version    = model_info.get("version", "")

    if trained:
        st.success(f"🤖 Active model: **{model_name}** (v{version}) — Custom trained LRT model")
    else:
        st.warning(
            f"⚠️ Active model: **{model_name}** — Generic pre-trained weights. "
            f"Defect classifications may be unreliable until custom LRT model is trained."
        )

    # ── Manual refresh button ──────────────────────────────────
    if st.button("🔄 Refresh Page", use_container_width=True):
        load_defect_records.clear()
        st.rerun()

    supabase = get_supabase()

    # ── Retrain notification banner (management only) ──────────
    if is_logged_in() and get_role() in ("management", "supervisor", "ic"):
        count = get_capture_count(supabase)
        if count >= RETRAIN_THRESHOLD:
            st.warning(
                f"🔔 **Retrain Recommended** — {count} new captures collected since last retrain. "
                f"Go to the **🔄 Retrain** tab to review and trigger retraining."
            )

    st.divider()

    # ── Technician view (no login) ─────────────────────────────
    if not is_logged_in():
        # ── Launch Camera Station button ───────────────────────
        st.markdown(
            """
            <style>
            .camera-btn-container {
                display: flex;
                justify-content: center;
                margin-bottom: 20px;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        col_left, col_right = st.columns(2)

        # ── Wired camera card ──────────────────────────────────
        with col_left:
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
                "🚀 Launch Wired Station",
                type="primary",
                use_container_width=True,
                key="launch_camera"
            ):
                import subprocess
                import sys
                try:
                    subprocess.Popen(
                        [sys.executable, "dji_camera_station.py"],
                        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    )
                    st.info(
                        "📷 Wired camera station is starting. "
                        "A setup window will appear on your desktop shortly. "
                        "If nothing appears, check that the DJI camera is plugged in and switched on."
                    )
                except Exception as e:
                    st.error(f"❌ Could not launch wired camera station: {e}")

            st.markdown(
                """<div style="text-align:center;margin-top:4px;">
                <span style="font-size:11px;color:#64748B;">or</span>
                </div>""",
                unsafe_allow_html=True
            )
            if st.button(
                "📱 Mobile Capture Station",
                use_container_width=True,
                key="launch_mobile_capture"
            ):
                st.session_state["current_page"] = "📱 Mobile Capture Station"
                st.rerun()

        # ── Wireless camera card ───────────────────────────────
        with col_right:
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
                "🚀 Launch Wireless Station",
                type="primary",
                use_container_width=True,
                key="launch_wireless"
            ):
                import subprocess
                import sys
                try:
                    subprocess.Popen(
                        [sys.executable, "dji_wireless_station.py"],
                        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    )
                    st.info(
                        "📡 Wireless camera station is starting. "
                        "Make sure rtmp_server.js is running and DJI Mimo is streaming "
                        "before clicking Connect in the setup window."
                    )
                except Exception as e:
                    st.error(f"❌ Could not launch wireless camera station: {e}")

            st.markdown(
                """<div style="text-align:center;margin-top:4px;">
                <span style="font-size:11px;color:#64748B;">or</span>
                </div>""",
                unsafe_allow_html=True
            )
            if st.button(
                "📱 Launch Wireless Station on Mobile",
                use_container_width=True,
                key="launch_wireless_mobile"
            ):
                st.session_state["current_page"] = "📡 DJI Wireless Station (Mobile)"
                st.rerun()

        st.divider()
        st.info("👷 Technician View — items marked ⚠️ REVIEW need management verification.")

        supabase_anon = get_supabase()

        # Count pending reviews — unique sessions not individual records
        try:
            pending = supabase_anon.table("defect_records") \
                .select("session_id, defect_type, confidence") \
                .gt("confidence", 0) \
                .eq("reviewed", False) \
                .execute()
            # Filter by per-defect threshold
            pending_recs = [
                r for r in (pending.data or [])
                if _needs_review(r.get("defect_type", ""), r.get("confidence", 0))
            ]
            unique_sessions = len(set(r["session_id"] for r in pending_recs))
            tech_pending = unique_sessions
        except:
            tech_pending = 0

        review_label = f"⚠️ Needs Review ({tech_pending})" if tech_pending > 0 else "⚠️ Needs Review"

        tech_tab1, tech_tab2 = st.tabs([review_label, "🖼️ Recent Detections"])

        with tech_tab1:
            try:
                review_records = supabase_anon.table("defect_records") \
                    .select("*, inspection_sessions(asset_id, technician_name)") \
                    .lt("confidence", CONFIDENCE_THRESHOLD) \
                    .gt("confidence", 0) \
                    .eq("reviewed", False) \
                    .order("detected_at", desc=True) \
                    .execute()

                if not review_records.data:
                    st.success("✅ No detections currently need management review.")
                else:
                    # Group by session_id
                    from collections import defaultdict
                    rev_sessions      = defaultdict(list)
                    rev_session_order = []
                    for rec in review_records.data:
                        sid = rec.get("session_id")
                        if sid not in rev_sessions:
                            rev_session_order.append(sid)
                        rev_sessions[sid].append(rec)

                    st.caption(f"{len(rev_session_order)} capture(s) awaiting management verification")

                    for sid in rev_session_order:
                        recs = rev_sessions[sid]
                        recs.sort(key=lambda r: r.get("confidence", 0), reverse=True)
                        first_rec    = recs[0]
                        session_info = first_rec.get("inspection_sessions") or {}
                        asset_id     = session_info.get("asset_id", "Unknown")
                        tech_name    = session_info.get("technician_name", "Unknown")
                        timestamp    = _to_sgt(first_rec.get("detected_at", ""))

                        with st.container(border=True):
                            col1, col2 = st.columns([4, 1])
                            with col1:
                                st.markdown(
                                    f"**Asset:** {asset_id}  |  **Technician:** {tech_name}  |  **Detected:** {timestamp}"
                                )
                                for r in recs:
                                    defect = r.get("defect_type", "none")
                                    conf   = r.get("confidence", 0)
                                    st.markdown(f"{DEFECT_EMOJI.get(defect, '🔍')} `{defect}` at **{conf:.0%}** confidence")
                            with col2:
                                st.markdown(
                                    """<div style="background:#FEF3C7;border:1px solid #F59E0B;
                                    border-radius:6px;padding:6px 10px;text-align:center;font-size:11px;">
                                    <b style="color:#92400E;">⚠️ REVIEW</b><br>
                                    <span style="font-size:10px;color:#92400E;">Inform management</span>
                                    </div>""", unsafe_allow_html=True
                                )

                            # Lazy load — show all unique images in session
                            show_key = f"show_images_needs_{sid}"
                            if not st.session_state.get(show_key, False):
                                if st.button("🖼️ View Images", key=f"view_img_needs_{sid}", use_container_width=True):
                                    st.session_state[show_key] = True
                                    st.rerun()
                            else:
                                seen_paths = set()
                                unique_captures = []
                                for r in sorted(recs, key=lambda x: x.get("detected_at", "")):
                                    raw_path = r.get("raw_image_path")
                                    if raw_path and raw_path not in seen_paths:
                                        seen_paths.add(raw_path)
                                        unique_captures.append(r)

                                for i, capture in enumerate(unique_captures):
                                    if len(unique_captures) > 1:
                                        st.caption(f"**Capture {i+1} of {len(unique_captures)}**")
                                    img1, img2 = st.columns(2)
                                    with img1:
                                        st.caption("Original")
                                        raw_url = _signed_url(supabase_anon, "raw-photos", capture.get("raw_image_path"))
                                        if raw_url: st.image(raw_url)
                                        else: st.caption("No image available")
                                    with img2:
                                        st.caption("YOLO Annotated")
                                        ann_url = _signed_url(supabase_anon, "annotated-photos", capture.get("annotated_image_path"))
                                        if ann_url: st.image(ann_url)
                                        else: st.caption("No annotation available")
            except Exception as e:
                st.error(f"Could not load review items: {e}")

        with tech_tab2:
            _tab_recent(supabase_anon)

        return

    # ── Management view (logged in) ────────────────────────────
    # Count pending reviews
    try:
        pending = supabase.table("defect_records") \
            .select("session_id, defect_type, confidence") \
            .gt("confidence", 0) \
            .eq("reviewed", False) \
            .execute()
        # Filter by per-defect threshold
        pending_recs = [
            r for r in (pending.data or [])
            if _needs_review(r.get("defect_type", ""), r.get("confidence", 0))
        ]
        unique_sessions = len(set(r["session_id"] for r in pending_recs))
        pending_count = unique_sessions
    except:
        pending_count = 0

    # ── Blinking review button + inline panel ──────────────────
    col_left, col_right = st.columns([8, 2])

    with col_left:
        st.markdown("") # spacer

    with col_right:
        if pending_count > 0:
            st.markdown(
                f"""
                <style>
                @keyframes pulse {{
                    0%   {{ opacity: 1; box-shadow: 0 0 0 0 rgba(245,158,11,0.7); }}
                    50%  {{ opacity: 0.75; box-shadow: 0 0 0 8px rgba(245,158,11,0); }}
                    100% {{ opacity: 1; box-shadow: 0 0 0 0 rgba(245,158,11,0); }}
                }}
                .review-badge {{
                    animation: pulse 1.5s infinite;
                    background: #F59E0B;
                    color: white;
                    border-radius: 8px;
                    padding: 8px 14px;
                    font-size: 13px;
                    font-weight: 700;
                    display: inline-block;
                    width: 100%;
                    text-align: center;
                }}
                </style>
                <div class="review-badge">⚠️ {pending_count} Needs Review</div>
                """,
                unsafe_allow_html=True
            )
            # Toggle button below the badge
            if st.button(
                "Open / Close",
                key="toggle_review_panel",
                use_container_width=True,
            ):
                st.session_state["show_review_panel"] = not st.session_state.get("show_review_panel", False)
        else:
            st.markdown(
                """<div style="background:#DCFCE7;color:#166534;border-radius:8px;
                padding:6px 14px;font-size:13px;font-weight:600;text-align:center;">
                ✅ All reviewed</div>""",
                unsafe_allow_html=True
            )
            st.session_state["show_review_panel"] = False

    # ── Inline review panel ─────────────────────────────────────
    if st.session_state.get("show_review_panel", False) and pending_count > 0:
        with st.container(border=True):
            st.markdown(f"#### ⚠️ Review Queue ({pending_count})")
            st.caption(f"Detections below {CONFIDENCE_THRESHOLD:.0%} confidence needing verification.")
            _tab_review_queue(supabase)
        st.divider()

    # ── Main tabs ───────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "✅ Reviewed",
        "📷 Manual Upload",
        "🖼️ Recent Detections",
        "📥 Export / Report",
        "🔄 Retrain",
    ])

    with tab1:
        _tab_reviewed(supabase)

    with tab2:
        _tab_new_detection(supabase)

    with tab3:
        _tab_recent(supabase)

    with tab4:
        _tab_export(supabase)

    with tab5:
        _tab_retrain(supabase)
