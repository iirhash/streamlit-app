# app/wireless_station.py
# ── DJI Wireless Station — Streamlit UI ───────────────────────
# Replaces tkinter popups with Streamlit UI so the entire
# wireless inspection workflow can be operated from a phone browser.
#
# States:
#   connect   → Connect to RTMP stream
#   tips      → Capture tips (3-angle instructions)
#   setup     → Technician name + Asset ID
#   capturing → Capture 1/3, 2/3, 3/3
#   complete  → Session complete, option for new session
# ─────────────────────────────────────────────────────────────

import streamlit as st
import os
import sys
import threading
import time
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.login import get_supabase

# ── Import from wireless station ──────────────────────────────
try:
    import cv2
    from dji_wireless_station import (
        run_capture_pipeline,
        gray_world_balance,
        apply_glare_mode,
        RTMP_RECEIVE_URL,
        TEMP_DIR,
        CAPTURE_ANGLES,
    )
    CV2_AVAILABLE = True
except Exception:
    CV2_AVAILABLE = False
    RTMP_RECEIVE_URL = ""
    CAPTURE_ANGLES = [
        "Angle camera 15° to the LEFT",
        "Angle camera CENTRE (0°) — straight on",
        "Angle camera 15° to the RIGHT",
    ]

# ── LRV data (same as camera station) ─────────────────────────
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


def _build_asset_id():
    """Builds asset ID from dropdown selections."""
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        lrv_model = st.selectbox("LRV Model", list(LRV_MODELS.keys()), key="ws_model", label_visibility="collapsed")
    with c2:
        lrv_nums  = [f"LRV{n:02d}" for n in LRV_MODELS.get(lrv_model, [])]
        lrv_num   = st.selectbox("LRV Number", lrv_nums, key="ws_num", label_visibility="collapsed")
    with c3:
        cab_end   = st.selectbox("Cab End", CAB_ENDS, key="ws_cab", label_visibility="collapsed")
    with c4:
        pos_opts  = POSITIONS.get(cab_end, [1, 2])
        position  = st.selectbox("Position", pos_opts, key="ws_pos", label_visibility="collapsed")
    with c5:
        side      = st.selectbox("Side", ["Upper (+)", "Lower (-)"], key="ws_side", label_visibility="collapsed")

    side_char = "+" if "Upper" in side else "-"
    return f"CS-{lrv_num}-{side_char}{cab_end}{position}"


def _connect_to_stream():
    """Attempts to connect to RTMP stream. Returns cap or None."""
    try:
        cap = cv2.VideoCapture(RTMP_RECEIVE_URL, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FPS, 30)

        # Timeout 15 seconds
        conn_result = {"ok": False}

        def _try():
            ok = cap.isOpened()
            if ok:
                ret, _ = cap.read()
                ok = ret
            conn_result["ok"] = ok

        t = threading.Thread(target=_try, daemon=True)
        t.start()
        t.join(timeout=15)

        if t.is_alive() or not conn_result["ok"]:
            cap.release()
            return None
        return cap
    except Exception:
        return None


def _capture_frame(asset_id, capture_num):
    """Captures a frame from RTMP stream and saves locally. Returns local_path or None."""
    try:
        cap = cv2.VideoCapture(RTMP_RECEIVE_URL, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FPS, 30)

        # Flush buffer
        flush_start = time.time()
        while time.time() - flush_start < 3.0:
            cap.grab()

        for _ in range(2):
            cap.read()
            time.sleep(0.05)
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None or frame.size == 0:
            return None

        frame      = gray_world_balance(frame)
        frame      = apply_glare_mode(frame)
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        local_path = os.path.join(TEMP_DIR, f"ws_{timestamp}_cap{capture_num}.jpg")
        cv2.imwrite(local_path, frame)
        return local_path, timestamp
    except Exception as e:
        return None


def _run_yolo_on_frames(supabase, asset_id, technician_name, session_id, captured_frames):
    """Runs YOLO on all pre-captured frames and saves to Supabase."""
    results = []
    for i, (local_path, timestamp) in enumerate(captured_frames):
        try:
            cap = cv2.VideoCapture(RTMP_RECEIVE_URL, cv2.CAP_FFMPEG)
            success = run_capture_pipeline(
                supabase, cap, asset_id, technician_name,
                session_id=session_id,
                local_path=local_path,
                timestamp=timestamp,
            )
            cap.release()
            results.append(success)
        except Exception as e:
            results.append(False)
    return all(results)


def show():
    st.markdown("## 📡 DJI Wireless Station (Mobile)")
    st.caption("Operate the DJI wireless inspection station from your browser — works on phone and desktop.")
    st.divider()

    # ── Check if running on cloud ──────────────────────────────
    if not CV2_AVAILABLE:
        st.warning(
            "📡 **DJI Wireless Station is not available on Streamlit Cloud.**\n\n"
            "This feature requires:\n"
            "- A local RTMP server (`rtmp_server.js`) running on your laptop\n"
            "- The DJI camera streaming to your local network\n\n"
            "Please access this feature by running the app **locally on your laptop** and connecting from your phone browser via `http://[laptop IP]:8501`."
        )
        return

    # ── Ensure current_page stays on this page during reruns ──
    st.session_state["current_page"] = "📡 DJI Wireless Station (Mobile)"

    supabase = get_supabase()

    # ── Initialise session state ───────────────────────────────
    if "ws_state" not in st.session_state:
        st.session_state["ws_state"]          = "connect"
        st.session_state["ws_session_id"]     = None
        st.session_state["ws_capture_num"]    = 1
        st.session_state["ws_asset_id"]       = None
        st.session_state["ws_tech_name"]      = None
        st.session_state["ws_results"]        = []

    state = st.session_state["ws_state"]

    # ══════════════════════════════════════════════════════════
    # STATE 1: Connect to Stream
    # ══════════════════════════════════════════════════════════
    if state == "connect":
        st.markdown("### Step 1 — Connect to DJI Stream")
        st.info(
            f"Make sure:\n"
            f"1. `rtmp_server.js` is running on the laptop\n"
            f"2. DJI Mimo is streaming to: `{RTMP_RECEIVE_URL}`\n"
            f"3. Laptop and phone are on the same network"
        )
        st.markdown(f"**RTMP URL:** `{RTMP_RECEIVE_URL}`")

        if st.button("📡 Connect to Stream", type="primary", use_container_width=True):
            with st.spinner("Connecting to stream... (timeout: 15s)"):
                cap = _connect_to_stream()
            if cap is not None:
                cap.release()  # release — will reconnect fresh per capture
                st.success("✅ Stream connected! Proceeding to capture tips...")
                st.session_state["ws_state"] = "tips"
                st.rerun()
            else:
                st.error(
                    "⏱️ Could not connect to stream.\n\n"
                    "Please check:\n"
                    "- rtmp_server.js is running\n"
                    "- DJI Mimo is actively streaming\n"
                    "- RTMP URL is correct"
                )

    # ══════════════════════════════════════════════════════════
    # STATE 2: Capture Tips
    # ══════════════════════════════════════════════════════════
    elif state == "tips":
        st.markdown("### Step 2 — Capture Tips")
        st.markdown(
            """
            Each inspection session requires **3 captures** from different angles:

            | Capture | Angle | Instructions |
            |---------|-------|--------------|
            | 1 of 3 | 15° Left | Tilt camera slightly to the LEFT of the shoe surface |
            | 2 of 3 | Centre 0° | Hold camera straight on — directly facing the shoe |
            | 3 of 3 | 15° Right | Tilt camera slightly to the RIGHT of the shoe surface |

            **Tips for best results:**
            - Hold the DJI camera steady before capturing
            - Ensure the collector shoe fills most of the frame
            - Avoid strong shadows or direct light reflections
            - Wait for the stream to stabilise before each capture
            """
        )
        st.warning("⚠️ All 3 captures are required — there is no skip option.")

        if st.button("✅ Got it — Continue to Session Setup", type="primary", use_container_width=True):
            st.session_state["ws_state"] = "setup"
            st.rerun()

        if st.button("← Back to Connect", use_container_width=True):
            st.session_state["ws_state"] = "connect"
            st.rerun()

    # ══════════════════════════════════════════════════════════
    # STATE 3: Session Setup
    # ══════════════════════════════════════════════════════════
    elif state == "setup":
        st.markdown("### Step 3 — Session Setup")

        tech_name = st.text_input(
            "Technician Name",
            placeholder="Enter your name",
            key="ws_tech_input"
        )

        st.markdown("**Asset ID**")
        asset_id = _build_asset_id()
        st.caption(f"Asset ID: **{asset_id}**")

        # Validate shoe
        if asset_id:
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
                else:
                    st.warning(f"⚠️ {asset_id} not registered. Please register it on the Collector Shoe page first.")
            except:
                pass

        if st.button("🚀 Start Inspection Session", type="primary", use_container_width=True):
            if not tech_name.strip():
                st.error("Please enter your technician name.")
            else:
                # Create shared session in Supabase
                try:
                    session_resp = supabase.table("inspection_sessions").insert({
                        "technician_name": tech_name.strip(),
                        "employee_id":     "N/A",
                        "asset_id":        asset_id,
                        "status":          "submitted",
                        "notes":           "Captured via DJI wireless station (Streamlit mobile UI) — 3-angle inspection",
                    }).execute()
                    if not session_resp.data:
                        st.error("Could not create session. Check RLS policies.")
                    else:
                        st.session_state["ws_session_id"]  = session_resp.data[0]["id"]
                        st.session_state["ws_tech_name"]   = tech_name.strip()
                        st.session_state["ws_asset_id"]    = asset_id
                        st.session_state["ws_capture_num"] = 1
                        st.session_state["ws_results"]     = []
                        st.session_state["ws_state"]       = "capturing"
                        st.rerun()
                except Exception as e:
                    st.error(f"Session creation failed: {e}")

        if st.button("← Back to Tips", use_container_width=True):
            st.session_state["ws_state"] = "tips"
            st.rerun()

    # ══════════════════════════════════════════════════════════
    # STATE 4: Capturing
    # ══════════════════════════════════════════════════════════
    elif state == "capturing":
        capture_num = st.session_state["ws_capture_num"]
        asset_id    = st.session_state["ws_asset_id"]
        tech_name   = st.session_state["ws_tech_name"]
        session_id  = st.session_state["ws_session_id"]
        angle       = CAPTURE_ANGLES[capture_num - 1]

        st.markdown(f"### Capture {capture_num} of {TOTAL_CAPTURES}")

        # Progress bar
        st.progress(capture_num / TOTAL_CAPTURES)

        # Angle instruction
        st.markdown(
            f"""<div style="background:#DBEAFE;border:2px solid #1A6FB5;border-radius:12px;
            padding:20px;text-align:center;margin:16px 0;">
            <div style="font-size:36px;">📷</div>
            <div style="font-size:18px;font-weight:700;color:#1A6FB5;margin-top:8px;">
            {angle}</div>
            <div style="font-size:13px;color:#1E293B;margin-top:6px;">
            Position the DJI camera at this angle and press Capture when ready.</div>
            </div>""",
            unsafe_allow_html=True
        )

        st.markdown(f"**Asset:** {asset_id}  |  **Technician:** {tech_name}")
        st.markdown(f"**Session ID:** `{session_id[:8]}...`")

        if st.button(f"📸 Capture {capture_num}/{TOTAL_CAPTURES}", type="primary", use_container_width=True):
            with st.spinner(f"Capturing frame... ({angle})"):
                result = _capture_frame(asset_id, capture_num)

            if result is not None:
                local_path, timestamp = result
                # Store captured frame in session state
                frames = st.session_state.get("ws_captured_frames", [])
                frames.append((local_path, timestamp))
                st.session_state["ws_captured_frames"] = frames

                if capture_num < TOTAL_CAPTURES:
                    st.session_state["ws_capture_num"] = capture_num + 1
                    st.success(f"✅ Capture {capture_num}/{TOTAL_CAPTURES} done! Proceed to next angle.")
                    time.sleep(1)
                    st.rerun()
                else:
                    # All frames captured — now run YOLO on all
                    with st.spinner(f"Running YOLO on all {TOTAL_CAPTURES} captures..."):
                        success = _run_yolo_on_frames(
                            supabase, asset_id, tech_name, session_id,
                            st.session_state.get("ws_captured_frames", [])
                        )
                    st.session_state["ws_results"].append({
                        "capture": capture_num,
                        "angle":   angle,
                        "success": success,
                    })
                    st.session_state["ws_captured_frames"] = []
                    st.session_state["ws_state"] = "complete"
                    st.rerun()
            else:
                st.error(f"❌ Capture {capture_num} failed. Check the stream and try again.")

        if st.button("❌ Cancel Session", use_container_width=True):
            st.session_state["ws_state"] = "connect"
            st.session_state["ws_session_id"] = None
            st.rerun()

    # ══════════════════════════════════════════════════════════
    # STATE 5: Session Complete
    # ══════════════════════════════════════════════════════════
    elif state == "complete":
        asset_id  = st.session_state["ws_asset_id"]
        tech_name = st.session_state["ws_tech_name"]
        results   = st.session_state["ws_results"]

        st.markdown(
            """<div style="background:#DCFCE7;border:2px solid #0A8A72;border-radius:12px;
            padding:24px;text-align:center;margin:16px 0;">
            <div style="font-size:48px;">✅</div>
            <div style="font-size:22px;font-weight:700;color:#166534;margin-top:8px;">
            Session Complete!</div>
            <div style="font-size:14px;color:#166534;margin-top:6px;">
            All 3 captures saved to Supabase successfully.</div>
            </div>""",
            unsafe_allow_html=True
        )

        st.markdown(f"**Asset:** {asset_id}  |  **Technician:** {tech_name}")

        # Results summary
        st.markdown("**Capture Summary:**")
        for r in results:
            icon = "✅" if r["success"] else "❌"
            st.markdown(f"{icon} Capture {r['capture']}/3 — {r['angle']}")

        st.markdown("---")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("📷 New Inspection Session", type="primary", use_container_width=True):
                # Reset for new session but keep stream connected
                st.session_state["ws_state"]       = "setup"
                st.session_state["ws_session_id"]  = None
                st.session_state["ws_capture_num"] = 1
                st.session_state["ws_results"]     = []
                st.rerun()
        with col2:
            if st.button("🔍 View in Defect Viewer", use_container_width=True):
                st.session_state["current_page"] = "🔍 Defect Viewer"
                if "nav_radio" in st.session_state:
                    del st.session_state["nav_radio"]
                st.rerun()
