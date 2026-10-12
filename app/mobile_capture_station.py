# app/mobile_capture_station.py
# ── Mobile Phone Capture Station ──────────────────────────────
# Allows technicians to use their phone camera directly in the
# browser to capture collector shoe inspection photos.
# Uses st.camera_input() to open phone camera in browser.
#
# States:
#   tips      → Capture tips (3-angle instructions)
#   setup     → Technician name + Asset ID
#   capturing → Capture 1/3, 2/3, 3/3 via phone camera
#   complete  → Session complete
# ─────────────────────────────────────────────────────────────

import streamlit as st
import os
import sys
import cv2
import numpy as np
from datetime import datetime, timezone
from PIL import Image
import io

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.login import get_supabase
from core.yolo_detect import detect_defects, CONFIDENCE_THRESHOLD, SCUFF_MARKS_THRESHOLD, get_status_label, increment_capture_count

# ── LRV data ──────────────────────────────────────────────────
LRV_MODELS = {
    "Test / Training Vehicle":  [0],
    "Non-Modified C810":        [2,3,6,8,11,14,16,17,19,20,24,29,32,37,38,39,40,41],
    "Modified C810":            [4,5,7,9,10,12,15,18,22,25,27,28,30,33,35,36],
    "New C810A":                list(range(42, 58)),
    "C810D":                    list(range(58, 70)),
}
CAB_ENDS  = ["A", "B"]
POSITIONS = {"A": [1, 2], "B": [3, 4]}
TOTAL_CAPTURES = 3
TEMP_DIR = "mobile_station_temp"
os.makedirs(TEMP_DIR, exist_ok=True)

CAPTURE_ANGLES = [
    "Angle camera 15° to the LEFT",
    "Angle camera CENTRE (0°) — straight on",
    "Angle camera 15° to the RIGHT",
]


def _apply_pipeline(image_bytes):
    """Apply greyscale + CLAHE + sharpen pipeline to uploaded image.
    Auto-rotates portrait images to landscape for consistent display."""
    nparr  = np.frombuffer(image_bytes, np.uint8)
    frame  = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        return None, None

    # Auto-rotate portrait to landscape
    h, w = frame.shape[:2]
    if h > w:
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        print(f"  → Portrait detected ({w}x{h}) — rotated to landscape (anti-clockwise)")

    # Resize to DJI-like resolution (1280x720) for consistent YOLO performance
    # Phone cameras capture at much higher resolution than DJI training data
    target_w, target_h = 1280, 720
    h, w = frame.shape[:2]
    if w != target_w or h != target_h:
        frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
        print(f"  → Resized from ({w}x{h}) to ({target_w}x{target_h}) for YOLO consistency")

    # Grey world balance
    result = frame.astype(np.float32)
    avg_b, avg_g, avg_r = (result[:, :, i].mean() for i in range(3))
    avg_gray = (avg_b + avg_g + avg_r) / 3
    result[:, :, 0] *= avg_gray / max(avg_b, 1)
    result[:, :, 1] *= avg_gray / max(avg_g, 1)
    result[:, :, 2] *= avg_gray / max(avg_r, 1)
    frame = result.clip(0, 255).astype(np.uint8)

    # Greyscale + CLAHE + Sharpen
    grey      = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    clahe     = cv2.createCLAHE(clipLimit=0.5, tileGridSize=(8, 8))
    grey_eq   = clahe.apply(grey)
    blurred   = cv2.GaussianBlur(grey_eq, (0, 0), 3)
    sharpened = cv2.addWeighted(grey_eq, 1 + 1.5, blurred, -1.5, 0)
    processed = cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)

    # Save to temp file for YOLO
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    local_path = os.path.join(TEMP_DIR, f"{timestamp}.jpg")
    cv2.imwrite(local_path, processed)
    return local_path, processed


def _run_pipeline(supabase, image_bytes, asset_id, technician_name, session_id, local_path=None):
    """Process image through YOLO and save to Supabase.
    If local_path provided, uses pre-captured file. Otherwise processes image_bytes."""
    if local_path is None:
        local_path, processed = _apply_pipeline(image_bytes)
        if local_path is None:
            return False, "Could not process image"

    try:
        # Microseconds so 3 captures processed in the same second get unique file names
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        # Upload raw image
        raw_path = f"{asset_id}/{session_id}/{timestamp}_raw.jpg"
        with open(local_path, "rb") as f:
            supabase.storage.from_("raw-photos").upload(
                path=raw_path, file=f,
                file_options={"content-type": "image/jpeg"}
            )

        # Run YOLO
        result         = detect_defects(local_path)
        annotated_path = None

        if result.get("error"):
            # Do not log a false "No defect detected" when the AI call itself failed
            os.remove(local_path)
            return False, f"AI detection failed: {result['error']}"

        if result.get("error") is None and result.get("annotated") is not None:
            annotated_local = local_path.replace(".jpg", "_annotated.jpg")
            cv2.imwrite(annotated_local, cv2.cvtColor(result["annotated"], cv2.COLOR_RGB2BGR))
            annotated_path = f"{asset_id}/{session_id}/{timestamp}_annotated.jpg"
            with open(annotated_local, "rb") as f:
                supabase.storage.from_("annotated-photos").upload(
                    path=annotated_path, file=f,
                    file_options={"content-type": "image/jpeg"}
                )
            os.remove(annotated_local)

        # Log defect records
        SKIP_CLASSES = ("collector_shoe", "collector shoe")
        detections   = result.get("detections", [])
        valid_detections = [
            d for d in detections
            if d["label"].lower() not in SKIP_CLASSES
            and d["label"].lower() != "none"
            and d["confidence"] > 0
        ]

        if not valid_detections:
            supabase.table("defect_records").insert({
                "session_id":           session_id,
                "defect_type":          "none",
                "confidence":           0.0,
                "raw_image_path":       raw_path,
                "annotated_image_path": annotated_path,
                "reviewed":             True,
                "reviewer_notes":       "No defect detected",
            }).execute()
        else:
            from core.yolo_detect import ROBOFLOW_CLASS_MAP
            for det in valid_detections:
                label      = det["label"].lower()
                conf       = det["confidence"]
                defect     = ROBOFLOW_CLASS_MAP.get(label, "wear")
                threshold  = SCUFF_MARKS_THRESHOLD if defect == "scuff marks" else CONFIDENCE_THRESHOLD
                needs_rev  = conf < threshold
                auto_conf  = not needs_rev

                record = {
                    "session_id":           session_id,
                    "defect_type":          defect,
                    "confidence":           conf,
                    "raw_image_path":       raw_path,
                    "annotated_image_path": annotated_path,
                    "reviewed":             auto_conf,
                }
                if auto_conf:
                    record["reviewer_notes"] = f"Auto-confirmed by system — confidence {conf:.1%} meets or exceeds the {threshold:.0%} threshold. No human review required."
                    record["reviewer_verdict"] = "confirmed"
                    record["reviewed_at"] = datetime.now(timezone.utc).isoformat()

                supabase.table("defect_records").insert(record).execute()

        increment_capture_count(supabase)
        os.remove(local_path)
        return True, result

    except Exception as e:
        if os.path.exists(local_path):
            os.remove(local_path)
        return False, str(e)


def _build_asset_id():
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        lrv_model = st.selectbox("LRV Model", list(LRV_MODELS.keys()), key="mc_model", label_visibility="collapsed")
    with c2:
        lrv_nums = [f"LRV{n:02d}" for n in LRV_MODELS.get(lrv_model, [])]
        lrv_num  = st.selectbox("LRV Number", lrv_nums, key="mc_num", label_visibility="collapsed")
    with c3:
        cab_end  = st.selectbox("Cab End", CAB_ENDS, key="mc_cab", label_visibility="collapsed")
    with c4:
        pos_opts = POSITIONS.get(cab_end, [1, 2])
        position = st.selectbox("Position", pos_opts, key="mc_pos", label_visibility="collapsed")
    with c5:
        side     = st.selectbox("Side", ["Upper (+)", "Lower (-)"], key="mc_side", label_visibility="collapsed")
    side_char = "+" if "Upper" in side else "-"
    return f"CS-{lrv_num}-{side_char}{cab_end}{position}"


def _discard_local_frames():
    """Deletes any locally saved captures from an unfinished session."""
    for lp in st.session_state.get("mc_captured_frames", []) or []:
        try:
            os.remove(lp)
        except OSError:
            pass
    st.session_state["mc_captured_frames"] = []


def _commit_session(supabase, asset_id, tech_name):
    """Runs the deferred Supabase writes once all captures are taken:
    shoe registration (Case A), rotation confirmation (Case C) and the
    inspection session. Returns the new session id, or None on failure."""
    pending = st.session_state.get("mc_pending") or {}

    reg = pending.get("register")
    if reg:
        try:
            from datetime import date
            supabase.table("collector_shoes").insert(
                {**reg, "registered_at": date.today().isoformat()}
            ).execute()
        except Exception as e:
            if "duplicate" not in str(e).lower() and "unique" not in str(e).lower():
                st.error(f"Registration failed: {e}")
                return None

    if pending.get("confirm_rotation"):
        try:
            # RPC — anon cannot UPDATE collector_shoes directly (RLS)
            rot_resp = supabase.rpc("confirm_shoe_rotation", {"p_shoe_id": asset_id}).execute()
            if rot_resp.data is not True:
                st.warning("⚠️ Rotation was not recorded — the shoe may no longer be pending rotation. Please inform your IC.")
        except Exception as e:
            st.error(f"Could not update rotation status: {e}")
            return None

    try:
        session_resp = supabase.table("inspection_sessions").insert({
            "technician_name": tech_name,
            "employee_id":     "N/A",
            "asset_id":        asset_id,
            "status":          "submitted",
            "notes":           "Captured via Mobile Capture Station (phone camera) — 3-angle inspection",
        }).execute()
    except Exception as e:
        st.error(f"Session creation failed: {e}")
        return None
    if not session_resp.data:
        st.error("Could not create session. Check RLS policies.")
        return None

    st.session_state["mc_pending"] = None
    return session_resp.data[0]["id"]


def show():
    st.markdown("## 📱 Mobile Capture Station")
    st.caption("Use your phone camera to capture collector shoe inspection photos directly in the browser.")
    st.divider()

    # ── Keep current page stable ───────────────────────────────
    st.session_state["current_page"] = "📱 Mobile Capture Station"

    supabase = get_supabase()

    # ── Initialise session state ───────────────────────────────
    if "mc_state" not in st.session_state:
        st.session_state["mc_state"]       = "tips"
        st.session_state["mc_session_id"]  = None
        st.session_state["mc_capture_num"] = 1
        st.session_state["mc_asset_id"]    = None
        st.session_state["mc_tech_name"]   = None
        st.session_state["mc_results"]     = []

    state = st.session_state["mc_state"]

    # ══════════════════════════════════════════════════════════
    # STATE 1: Capture Tips
    # ══════════════════════════════════════════════════════════
    if state == "tips":
        st.markdown("### Step 1 — Capture Tips")
        st.markdown(
            """
            Each inspection session requires **3 captures** from different angles:

            | Capture | Angle | Instructions |
            |---------|-------|--------------|
            | 1 of 3 | 15° Left | Tilt phone slightly to the LEFT of the shoe surface |
            | 2 of 3 | Centre 0° | Hold phone straight on — directly facing the shoe |
            | 3 of 3 | 15° Right | Tilt phone slightly to the RIGHT of the shoe surface |

            **Tips for best results:**
            - Hold the phone steady before capturing
            - **Rotate phone to landscape** with the charging port facing **right**
            - Ensure the collector shoe fills most of the frame
            - Avoid strong shadows or direct light reflections
            - Use the rear camera for best quality
            """
        )
        st.warning("⚠️ All 3 captures are required — there is no skip option.")
        st.info("📷 Your phone camera will open directly in the browser — no app needed.")

        if st.button("✅ Got it — Continue to Session Setup", type="primary", use_container_width=True):
            st.session_state["mc_state"] = "setup"
            st.rerun()

    # ══════════════════════════════════════════════════════════
    # STATE 2: Session Setup
    # ══════════════════════════════════════════════════════════
    elif state == "setup":
        st.markdown("### Step 2 — Session Setup")

        tech_name = st.text_input(
            "Technician Name",
            placeholder="Enter your name",
            key="mc_tech_input"
        )

        st.markdown("**Asset ID**")
        asset_id = _build_asset_id()
        st.caption(f"Asset ID: **{asset_id}**")

        # ── Shoe registration status check ─────────────────────
        if asset_id:
            # Check Supabase for this shoe
            shoe_rec = None
            try:
                r = supabase.table("collector_shoes") \
                    .select("shoe_id, rotation_status, condition") \
                    .eq("shoe_id", asset_id) \
                    .execute()
                shoe_rec = r.data[0] if r.data else None
            except:
                pass

            start_disabled = False

            if shoe_rec is None:
                # ── CASE A: Not registered ──────────────────────
                st.markdown(
                    """<div style="background:#FFF7ED;border:1px solid #F59E0B;
                    border-radius:8px;padding:10px 14px;margin:8px 0;">
                    <b>🆕 Shoe Not Registered</b><br>
                    <span style="font-size:13px;color:#78350F;">
                    This shoe has not been registered yet. Answer the questions below to register it before starting.
                    </span></div>""",
                    unsafe_allow_html=True
                )
                condition = st.radio(
                    "Is the shoe at this position a new shoe or already in-use?",
                    options=["🟢 New", "🔵 In-use"],
                    key=f"reg_condition_{asset_id}",
                    horizontal=True,
                )
                rotation_status = "in_service"
                if "In-use" in condition:
                    rotated = st.radio(
                        "Has the shoe at this position been rotated before?",
                        options=["No", "Yes"],
                        key=f"reg_rotated_{asset_id}",
                        horizontal=True,
                    )
                    rotation_status = "rotated_once" if rotated == "Yes" else "in_service"

            else:
                rot_status = shoe_rec.get("rotation_status", "in_service")
                condition  = None
                rotation_status = rot_status

                if rot_status == "in_service":
                    # ── CASE B ───────────────────────────────────
                    st.markdown(
                        """<div style="background:#F0FDF4;border:1px solid #0A8A72;
                        border-radius:8px;padding:10px 14px;margin:8px 0;">
                        <b>✅ Status: In Service</b><br>
                        <span style="font-size:13px;color:#166534;">
                        This shoe is registered and actively monitored. Proceed with inspection.
                        </span></div>""",
                        unsafe_allow_html=True
                    )

                elif rot_status == "not_rotated":
                    # ── CASE C ───────────────────────────────────
                    st.markdown(
                        """<div style="background:#FFF7ED;border:1px solid #F59E0B;
                        border-radius:8px;padding:10px 14px;margin:8px 0;">
                        <b>🔄 Status: Pending Rotation</b><br>
                        <span style="font-size:13px;color:#78350F;">
                        This shoe has been flagged for rotation by a supervisor.
                        </span></div>""",
                        unsafe_allow_html=True
                    )
                    rotation_confirm = st.radio(
                        "Has this shoe been rotated since it was last flagged?",
                        options=["No, not yet", "Yes, just done"],
                        key=f"rot_confirm_{asset_id}",
                        horizontal=True,
                    )
                    if rotation_confirm == "Yes, just done":
                        rotation_status = "rotated_once"

                elif rot_status == "rotated_once":
                    # ── CASE D ───────────────────────────────────
                    st.markdown(
                        """<div style="background:#F0FDF4;border:1px solid #0A8A72;
                        border-radius:8px;padding:10px 14px;margin:8px 0;">
                        <b>✅ Status: Rotated Once — second side in use</b><br>
                        <span style="font-size:13px;color:#166534;">
                        Shoe is on its second side. Proceed with inspection.
                        </span></div>""",
                        unsafe_allow_html=True
                    )

                elif rot_status == "retired":
                    # ── CASE E ───────────────────────────────────
                    st.markdown(
                        """<div style="background:#FEE2E2;border:1px solid #EF4444;
                        border-radius:8px;padding:10px 14px;margin:8px 0;">
                        <b>🚫 This shoe has been retired.</b><br>
                        <span style="font-size:13px;color:#991B1B;">
                        This shoe is no longer in service. Do not inspect.
                        Please check the position for a replacement shoe.
                        </span></div>""",
                        unsafe_allow_html=True
                    )
                    start_disabled = True

            # ── Start Session button ────────────────────────────
            if st.button("▶ Start Inspection", type="primary",
                         disabled=start_disabled,
                         use_container_width=True):
                if not tech_name.strip():
                    st.error("Please enter your technician name.")
                else:
                    # Nothing is written to Supabase yet — registration, rotation
                    # confirmation and the inspection session are saved only when
                    # all 3 captures are done. Cancelling therefore leaves no trace.
                    pending_reg = None
                    if shoe_rec is None and condition is not None:
                        pending_reg = {
                            "shoe_id":               asset_id,
                            "condition":             "new" if "New" in condition else "in_use",
                            "lrv_asset_id":          asset_id.split("-")[1] if "-" in asset_id else asset_id,
                            "baseline_thickness_mm": 16.0,
                            "rotation_status":       rotation_status,
                            "notes":                 f"Registered at first inspection by {tech_name.strip()}",
                        }
                    confirm_rot = bool(
                        shoe_rec and shoe_rec.get("rotation_status") == "not_rotated"
                        and rotation_status == "rotated_once"
                    )
                    st.session_state["mc_pending"]         = {"register": pending_reg, "confirm_rotation": confirm_rot}
                    st.session_state["mc_session_id"]      = None
                    st.session_state["mc_tech_name"]       = tech_name.strip()
                    st.session_state["mc_asset_id"]        = asset_id
                    st.session_state["mc_capture_num"]     = 1
                    st.session_state["mc_results"]         = []
                    st.session_state["mc_captured_frames"] = []
                    st.session_state["mc_camera_ready"]    = True
                    st.session_state["mc_cam_retry"]       = 0
                    st.session_state["mc_state"]           = "capturing"
                    st.rerun()

        if st.button("← Back to Tips", use_container_width=True):
            st.session_state["mc_state"] = "tips"
            st.rerun()

    # ══════════════════════════════════════════════════════════
    # STATE 3: Capturing
    # ══════════════════════════════════════════════════════════
    elif state == "capturing":
        capture_num = st.session_state["mc_capture_num"]
        asset_id    = st.session_state["mc_asset_id"]
        tech_name   = st.session_state["mc_tech_name"]
        session_id  = st.session_state["mc_session_id"]
        angle       = CAPTURE_ANGLES[capture_num - 1]

        st.markdown(f"### Capture {capture_num} of {TOTAL_CAPTURES}")
        st.progress(capture_num / TOTAL_CAPTURES)

        # Angle instruction card
        st.markdown(
            f"""<div style="background:#DCFCE7;border:2px solid #0A8A72;border-radius:12px;
            padding:20px;text-align:center;margin:16px 0;">
            <div style="font-size:36px;">📷</div>
            <div style="font-size:18px;font-weight:700;color:#0A8A72;margin-top:8px;">
            {angle}</div>
            <div style="font-size:13px;color:#1E293B;margin-top:6px;">
            Position your phone at this angle and take the photo below.</div>
            <div style="font-size:12px;color:#065f52;margin-top:8px;font-weight:600;">
            📱 Hold phone in landscape — charging port facing right</div>
            </div>""",
            unsafe_allow_html=True
        )

        st.markdown(f"**Asset:** {asset_id}  |  **Technician:** {tech_name}")

        # Pause between angles so the browser fully releases the previous
        # camera before a new one opens (opening too fast froze the camera
        # and triggered the browser permission prompt).
        if not st.session_state.get("mc_camera_ready", True):
            st.success(f"✅ Capture {capture_num - 1}/{TOTAL_CAPTURES} saved.")
            st.info("Move the phone to the angle shown above, then tap **Open Camera**.")
            if st.button(f"📷 Open Camera — Capture {capture_num}/{TOTAL_CAPTURES}",
                         type="primary", use_container_width=True):
                st.session_state["mc_camera_ready"] = True
                st.rerun()
            photo = None
        else:
            retry = st.session_state.get("mc_cam_retry", 0)
            photo = st.camera_input(
                f"📸 Take photo — Capture {capture_num}/{TOTAL_CAPTURES}",
                key=f"mc_camera_{capture_num}_{retry}"
            )
            if photo is None:
                if st.button("🔄 Camera frozen or asking for permission? Tap to retry",
                             use_container_width=True):
                    st.session_state["mc_cam_retry"] = retry + 1
                    st.rerun()

        if photo is not None:
            if st.button(f"✅ Use this photo — Capture {capture_num}/{TOTAL_CAPTURES}", type="primary", use_container_width=True):
                # Save image locally first — no YOLO yet
                with st.spinner(f"Saving capture {capture_num}/{TOTAL_CAPTURES}..."):
                    image_bytes = photo.getvalue()
                    local_path, processed = _apply_pipeline(image_bytes)

                if local_path:
                    # Store in session state
                    frames = st.session_state.get("mc_captured_frames", [])
                    frames.append(local_path)
                    st.session_state["mc_captured_frames"] = frames

                    if capture_num < TOTAL_CAPTURES:
                        st.session_state["mc_capture_num"]  = capture_num + 1
                        st.session_state["mc_camera_ready"] = False
                        st.session_state["mc_cam_retry"]    = 0
                        st.rerun()
                    else:
                        # All captures done — now save registration / rotation / session
                        session_id = _commit_session(supabase, asset_id, tech_name)
                        if session_id is None:
                            st.stop()  # error already shown; photos kept so they can retry
                        st.session_state["mc_session_id"] = session_id
                        # Run YOLO on all captures
                        with st.spinner(f"Running YOLO on all {TOTAL_CAPTURES} captures..."):
                            all_success = True
                            errors = []
                            for i, lp in enumerate(st.session_state.get("mc_captured_frames", [])):
                                success, result = _run_pipeline(
                                    supabase, None, asset_id, tech_name, session_id,
                                    local_path=lp
                                )
                                if not success:
                                    all_success = False
                                    errors.append(f"Capture {i+1}: {result}")
                        st.session_state["mc_errors"] = errors
                        st.session_state["mc_captured_frames"] = []
                        st.session_state["mc_results"].append({
                            "capture": capture_num,
                            "angle":   angle,
                            "success": all_success,
                        })
                        st.session_state["mc_state"] = "complete"
                        st.rerun()
                else:
                    st.error(f"❌ Could not process image. Please try again.")

        if st.button("❌ Cancel Session", use_container_width=True):
            _discard_local_frames()
            st.session_state["mc_state"]      = "tips"
            st.session_state["mc_session_id"] = None
            st.session_state["mc_pending"]    = None
            st.rerun()
        st.caption("Cancelling discards the photos taken so far. Nothing is saved until all 3 captures are done.")

    # ══════════════════════════════════════════════════════════
    # STATE 4: Session Complete
    # ══════════════════════════════════════════════════════════
    elif state == "complete":
        asset_id  = st.session_state["mc_asset_id"]
        tech_name = st.session_state["mc_tech_name"]
        results   = st.session_state["mc_results"]
        errors    = st.session_state.get("mc_errors", [])
        if errors:
            st.error("⚠️ Some captures were not processed by the AI:\n\n" + "\n\n".join(errors))

        st.markdown(
            """<div style="background:#DCFCE7;border:2px solid #0A8A72;border-radius:12px;
            padding:24px;text-align:center;margin:16px 0;">
            <div style="font-size:48px;">✅</div>
            <div style="font-size:22px;font-weight:700;color:#166534;margin-top:8px;">
            Session Complete!</div>
            <div style="font-size:14px;color:#166534;margin-top:6px;">
            All 3 captures saved to Supabase.</div>
            </div>""",
            unsafe_allow_html=True
        )

        st.markdown(f"**Asset:** {asset_id}  |  **Technician:** {tech_name}")
        st.markdown("**Capture Summary:**")
        for r in results:
            icon = "✅" if r["success"] else "❌"
            st.markdown(f"{icon} Capture {r['capture']}/3 — {r['angle']}")

        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📷 New Inspection Session", type="primary", use_container_width=True):
                st.session_state["mc_state"]       = "setup"
                st.session_state["mc_session_id"]  = None
                st.session_state["mc_capture_num"] = 1
                st.session_state["mc_results"]     = []
                st.session_state["mc_pending"]     = None
                st.rerun()
        with col2:
            if st.button("🔍 View in Defect Viewer", use_container_width=True):
                st.session_state["current_page"] = "🔍 Defect Viewer"
                st.rerun()
