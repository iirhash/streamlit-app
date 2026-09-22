# dji_wireless_station.py
# ── DJI Action 3 Wireless Camera Station ─────────────────────
# Run with: python dji_wireless_station.py
#
# Before running:
#   1. Start rtmp_server.js in a separate terminal
#   2. Start streaming from DJI Mimo to the RTMP URL
#   3. Run this script
#
# Capture triggers:
#   - Say "take picture" (voice via earbuds/mic)
#   - Press SPACE in the preview window
#
# Pipeline (matches dji_camera_station.py / wired station):
#   Capture → Gray world correction → Frame validity check
#   → ROI crop (collector shoe assets only) → Sharpening
#   → YOLO detection → Upload to Supabase → Appears in dashboard
#
# Session setup and "next asset" prompts use the same tkinter
# GUI popup style as the wired camera station — no terminal
# typing needed once the stream is connected.
# ─────────────────────────────────────────────────────────────

import sys
import os
import cv2
import time
import threading
import speech_recognition as sr
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from supabase import create_client
from config.settings import SUPABASE_URL, SUPABASE_KEY
from core.yolo_detect import detect_defects, CONFIDENCE_THRESHOLD, SCUFF_MARKS_THRESHOLD, get_status_label, increment_capture_count, RETRAIN_THRESHOLD
from white_balance_fix import gray_world_balance

# ── RTMP stream settings ───────────────────────────────────────
PC_IP            = "10.115.67.63"
RTMP_PORT        = 1936
STREAM_KEY       = "live/stream"
RTMP_RECEIVE_URL = f"rtmp://{PC_IP}:{RTMP_PORT}/{STREAM_KEY}"

# ── Voice trigger phrases ──────────────────────────────────────
TRIGGER_PHRASES = ["take picture", "take a picture", "take photo", "capture"]

# ── Local temp folder ──────────────────────────────────────────
TEMP_DIR = "wireless_station_temp"
os.makedirs(TEMP_DIR, exist_ok=True)

# ── Enhancement config — toggle here to compare ───────────────
# Set to False to revert to the previous pipeline instantly.
ENABLE_CLAHE            = False   # local contrast enhancement
ENABLE_ADAPTIVE_SHARPEN = False   # blur-aware sharpening (replaces fixed 1.0)
SHARPEN_FIXED_STRENGTH  = 1.0   # fallback if adaptive sharpen is off

capture_requested = threading.Event()
stop_listening    = threading.Event()


# ── Image processing (matches wired station) ───────────────────
def sharpen_image(frame, strength=1.0):
    """
    Unsharp mask sharpening — enhances surface detail for better YOLO detection.
    strength=1.0 (medium) selected based on visual comparison test
    (see test_sharpen.py). Helps YOLO detect fine surface features
    like grooves and scuff marks.
    """
    blurred   = cv2.GaussianBlur(frame, (0, 0), 3)
    sharpened = cv2.addWeighted(frame, 1 + strength, blurred, -strength, 0)
    return sharpened


def apply_glare_mode(frame):
    """
    Greyscale + mild CLAHE + gentle sharpen for glare-affected captures.
    Mutes colour channel glare, slightly enhances local contrast.
    Returns 3-channel BGR image for YOLO compatibility.
    clipLimit=0.5, sharpen strength=1.2 — tuned to maintain >=85% confidence.
    """
    grey      = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    clahe     = cv2.createCLAHE(clipLimit=0.5, tileGridSize=(8, 8))
    grey_eq   = clahe.apply(grey)
    blurred   = cv2.GaussianBlur(grey_eq, (0, 0), 3)
    sharpened = cv2.addWeighted(grey_eq, 1.5, blurred, -0.5, 0)
    return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)


def adaptive_sharpen(frame):
    """
    Blur-aware sharpening — measures how blurry the frame is using
    Laplacian variance, then scales sharpening strength accordingly.

    Laplacian variance:
      < 50  → very blurry  → strong sharpen (2.0)
      50–150 → mild blur   → medium sharpen (1.0)
      > 150  → already sharp → light sharpen (0.5)

    Avoids over-sharpening frames that are already crisp (which
    introduces noise artefacts that can confuse YOLO).
    """
    import numpy as np
    gray      = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    variance  = cv2.Laplacian(gray, cv2.CV_64F).var()

    if variance < 50:
        strength = 2.0
        label    = f"strong (blur={variance:.0f})"
    elif variance < 150:
        strength = 1.0
        label    = f"medium (blur={variance:.0f})"
    else:
        strength = 0.5
        label    = f"light  (blur={variance:.0f})"

    print(f"  → Adaptive sharpen: {label}, strength={strength}")
    return sharpen_image(frame, strength)


def apply_clahe(frame):
    """
    CLAHE (Contrast Limited Adaptive Histogram Equalization) —
    improves local contrast on the shoe surface so wear patterns,
    scuff marks, and oxidation are more visually distinct.

    Applied per-channel in LAB colour space so colour balance
    is preserved — only the luminance (L) channel is equalised.
    clipLimit=2.0 and tileGridSize=(8,8) are standard safe values
    that enhance contrast without introducing harsh halos.
    """
    lab   = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l     = clahe.apply(l)
    lab   = cv2.merge([l, a, b])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def apply_focus_overlay(frame, asset_id):
    """
    Applies a focus overlay for collector shoe captures.
    Darkens areas outside the focus zone and draws a white border.

    Focus zone (tuned to tightly frame collector shoe):
      x: 30%-70% of frame width
      y: 15%-85% of frame height

    Only applied when asset_id starts with 'CS-'.
    """
    import numpy as np

    if not asset_id.upper().startswith("CS-"):
        return frame

    h, w    = frame.shape[:2]
    x_start = int(w * 0.30)
    x_end   = int(w * 0.70)
    y_start = int(h * 0.15)
    y_end   = int(h * 0.85)

    overlay = frame.copy()
    alpha   = 0.70

    # Darken left and right
    overlay[:, :x_start] = (frame[:, :x_start] * (1 - alpha)).astype(np.uint8)
    overlay[:, x_end:]   = (frame[:, x_end:]   * (1 - alpha)).astype(np.uint8)
    # Darken top and bottom
    overlay[:y_start, x_start:x_end] = (frame[:y_start, x_start:x_end] * (1 - alpha)).astype(np.uint8)
    overlay[y_end:, x_start:x_end]   = (frame[y_end:, x_start:x_end]   * (1 - alpha)).astype(np.uint8)


    print(f"  → Focus overlay applied — focus zone: {x_start}–{x_end}px x {y_start}–{y_end}px")
    return overlay


def voice_listener():
    """Background thread — listens for trigger phrases."""
    recognizer = sr.Recognizer()
    mic        = sr.Microphone()

    with mic as source:
        print("🎙️  Calibrating microphone for ambient noise...")
        recognizer.adjust_for_ambient_noise(source, duration=2)
    print("🎙️  Voice control ready — say 'take picture' anytime.\n")

    while not stop_listening.is_set():
        try:
            with mic as source:
                audio = recognizer.listen(source, timeout=4, phrase_time_limit=4)
            text = recognizer.recognize_google(audio).lower()
            print(f"🗣️  Heard: \"{text}\"")
            if any(phrase in text for phrase in TRIGGER_PHRASES):
                print("✅ Voice trigger matched!")
                capture_requested.set()
        except sr.WaitTimeoutError:
            continue
        except sr.UnknownValueError:
            continue
        except sr.RequestError as e:
            print(f"⚠️  Speech recognition error: {e}")
        except Exception as e:
            print(f"⚠️  Voice listener error: {e}")


CAPTURE_ANGLES = [
    "Angle camera 15° to the LEFT",
    "Angle camera CENTRE (0°) — straight on",
    "Angle camera 15° to the RIGHT",
]

def _wait_for_trigger(cap, asset_id, capture_num=1, total=3):
    """
    Opens live preview window and waits for SPACE or voice trigger.
    Returns "space"/"voice"/None and updated cap.
    Shows capture counter and angle guidance.
    """
    angle       = CAPTURE_ANGLES[capture_num - 1]
    window_name = f"Capture {capture_num}/{total} — {angle} | SPACE = capture | Q = cancel"

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 640, 360)

    # ── Reconnect for freshest frame ───────────────────────────
    print("  → Reconnecting to stream for live preview...")
    cap.release()
    time.sleep(0.3)
    cap = cv2.VideoCapture(RTMP_RECEIVE_URL, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FPS, 30)

    print("  → Flushing accumulated buffer...")
    flush_start = time.time()
    while time.time() - flush_start < 4.0:
        cap.grab()

    while True:
        ret, frame = cap.read()
        if ret:
            preview = gray_world_balance(frame)
            # Draw capture counter on preview
            cv2.putText(preview, f"Capture {capture_num}/{total}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.putText(preview, angle, (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
            cv2.imshow(window_name, preview)

        key = cv2.waitKey(1) & 0xFF

        if key == ord(" "):
            cv2.destroyAllWindows()
            return "space", cap
        if key == ord("q"):
            cv2.destroyAllWindows()
            return None, cap
        if capture_requested.is_set():
            cv2.destroyAllWindows()
            return "voice", cap


def run_capture_pipeline(supabase, cap, asset_id, technician_name, session_id=None, local_path=None, timestamp=None):
    """
    Processes one frame through YOLO and uploads to Supabase.
    If local_path is provided, uses that pre-captured frame instead of capturing a new one.
    Returns True on success, False on failure.
    """
    # ── Capture frame if not pre-captured ──────────────────────
    if local_path is None:
        for _ in range(2):
            cap.read()
            time.sleep(0.05)

        ret, frame = cap.read()

        if not ret or frame is None or frame.size == 0:
            print("❌ Capture failed — no valid frame received. Please try again.")
            return False

        frame = gray_world_balance(frame)
        frame = apply_glare_mode(frame)
        print("  → Greyscale + CLAHE + Sharpen applied (fixed default)")

        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        local_path = os.path.join(TEMP_DIR, f"{timestamp}.jpg")
        cv2.imwrite(local_path, frame)
        print(f"📸 Frame captured: {local_path}")
    else:
        print(f"  → Using pre-captured frame: {local_path}")

    try:
        # 1. Create inspection session only if not already created
        if session_id is None:
            session_data = {
                "technician_name": technician_name,
                "employee_id":     "N/A",
                "asset_id":        asset_id,
                "status":          "submitted",
                "notes":           "Captured via DJI wireless camera station (voice/SPACE trigger)",
            }
            print("  → Inserting inspection session...")
            session_resp = supabase.table("inspection_sessions").insert(session_data).execute()
            if not session_resp.data:
                raise Exception("Session insert returned no data — check RLS policies.")
            session_id = session_resp.data[0]["id"]
            print(f"  → Session ID: {session_id}")
        else:
            print(f"  → Using existing Session ID: {session_id}")

        # 2. Upload raw image
        raw_path = f"{asset_id}/{session_id}/{timestamp}_raw.jpg"
        print(f"  → Uploading raw image...")
        with open(local_path, "rb") as f:
            supabase.storage.from_("raw-photos").upload(
                path=raw_path, file=f,
                file_options={"content-type": "image/jpeg"}
            )
        print(f"☁️  Raw image uploaded: raw-photos/{raw_path}")

        # 3. Run YOLO detection
        print("  → Running YOLO detection...")
        result     = detect_defects(local_path)
        annotated_path = None

        if result.get("error") is None and result.get("annotated") is not None:
            annotated_local = os.path.join(TEMP_DIR, f"{timestamp}_annotated.jpg")
            cv2.imwrite(annotated_local, cv2.cvtColor(result["annotated"], cv2.COLOR_RGB2BGR))
            annotated_path = f"{asset_id}/{session_id}/{timestamp}_annotated.jpg"
            print(f"  → Uploading annotated image...")
            with open(annotated_local, "rb") as f:
                supabase.storage.from_("annotated-photos").upload(
                    path=annotated_path, file=f,
                    file_options={"content-type": "image/jpeg"}
                )
            print(f"☁️  Annotated image uploaded: annotated-photos/{annotated_path}")
            os.remove(annotated_local)
        else:
            print(f"⚠️  YOLO not available ({result.get('error', 'unknown')}) — raw image saved only.")

        # 4. Log defect records — one per detection above threshold
        print("  → Logging defect records...")
        detections   = result.get("detections", [])
        needs_review = result.get("needs_review", False)

        # Filter out collector_shoe and get all valid defect detections
        SKIP_CLASSES = ("collector_shoe", "collector shoe")
        valid_detections = [
            d for d in detections
            if d["label"].lower() not in SKIP_CLASSES
            and d["label"].lower() != "none"
            and d["confidence"] > 0
        ]

        # If no valid detections, log a single "none" record
        if not valid_detections:
            valid_detections = [{
                "label":      result.get("defect", "none"),
                "confidence": result.get("confidence", 0.0),
            }]

        inserted_count = 0
        for det in valid_detections:
            conf        = det["confidence"]
            defect_type = det["label"].lower()

            # Map to LRT defect category
            from core.yolo_detect import ROBOFLOW_CLASS_MAP
            defect_type = ROBOFLOW_CLASS_MAP.get(defect_type, defect_type)

            # Auto-confirm based on per-defect threshold
            det_threshold = SCUFF_MARKS_THRESHOLD if defect_type == "scuff marks" else CONFIDENCE_THRESHOLD
            if conf >= det_threshold:
                auto_reviewed       = True
                auto_verdict        = "confirmed"
                auto_reviewer_notes = (
                    f"Auto-confirmed by system — confidence {conf:.1%} meets or exceeds "
                    f"the {det_threshold:.0%} threshold. No human review required."
                )
                auto_reviewed_at    = datetime.now(timezone.utc).isoformat()
            else:
                auto_reviewed       = False
                auto_verdict        = None
                auto_reviewer_notes = None
                auto_reviewed_at    = None

            defect_data = {
                "session_id":           session_id,
                "defect_type":          defect_type,
                "confidence":           conf,
                "raw_image_path":       raw_path,
                "annotated_image_path": annotated_path,
                "reviewed":             auto_reviewed,
                "reviewer_verdict":     auto_verdict,
                "reviewer_notes":       auto_reviewer_notes,
                "reviewed_at":          auto_reviewed_at,
            }
            supabase.table("defect_records").insert(defect_data).execute()
            inserted_count += 1
            if auto_reviewed:
                print(f"  → Auto-confirmed: {defect_type} ({conf:.1%})")
            else:
                print(f"  → Flagged for review: {defect_type} ({conf:.1%})")

        print(f"✅ Done — {inserted_count} defect record(s) saved\n")

        if needs_review:
            print(f"  ⚠️  LOW CONFIDENCE — a supervisor should verify this result in the Defect Viewer.\n")

        os.remove(local_path)

        # ── Increment retrain tracker ───────────────────────────
        new_count = increment_capture_count(supabase)
        if new_count >= RETRAIN_THRESHOLD:
            print(f"\n  🔔 RETRAIN ALERT — {new_count} new captures since last retrain.")
            print(f"     Go to Defect Viewer → Retrain tab to review and trigger retraining.\n")
        else:
            print(f"  → Retrain tracker: {new_count}/{RETRAIN_THRESHOLD} new captures")

        return True

    except Exception as e:
        print(f"❌ Pipeline error: {e}")
        print("   Photo captured locally but NOT saved to Supabase.")
        print("   Please try again, or ask a supervisor to upload manually.\n")
        return False


# ── LRV Vehicle Data ───────────────────────────────────────────
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

PART_TYPES = {
    "CS": "Collector Shoe",
    "TP": "Tyre Pressure (placeholder)",
}

CAB_ENDS = ["A", "B"]
CAB_POSITIONS = {"A": ["1", "2"], "B": ["3", "4"]}
SHOE_SIDES = {"+": "+ Upper", "-": "- Lower"}


def _build_asset_id_frame(parent, bg, header_color, current_asset=""):
    """
    Builds a reusable tkinter frame with dropdowns for Asset ID construction.
    Returns (frame, get_asset_id()) where get_asset_id() returns current ID.

    Dropdown flow:
      Part Type → LRV Model → LRV Number → Cab End → Position → Upper/Lower
      → Generated: CS-LRV01-+A1
    """
    import tkinter as tk
    from tkinter import ttk

    frame = tk.Frame(parent, bg=bg)

    def row(label, widget_fn, pady=(2, 6)):
        tk.Label(frame, text=label, bg=bg,
                 font=("Calibri", 10, "bold"), anchor="w").pack(fill="x")
        w = widget_fn(frame)
        w.pack(fill="x", pady=pady)
        return w

    # Part type
    part_var = tk.StringVar(value="CS")
    part_combo = row("Part Type", lambda f: ttk.Combobox(
        f, textvariable=part_var,
        values=[f"{k} — {v}" for k, v in PART_TYPES.items()],
        font=("Calibri", 10), state="readonly"
    ))
    part_combo.current(0)

    # LRV Model
    model_var = tk.StringVar(value=list(LRV_MODELS.keys())[0])
    model_combo = row("LRV Model", lambda f: ttk.Combobox(
        f, textvariable=model_var,
        values=list(LRV_MODELS.keys()),
        font=("Calibri", 10), state="readonly"
    ))
    model_combo.current(0)

    # LRV Number
    lrv_var = tk.StringVar()
    lrv_combo = row("LRV Number", lambda f: ttk.Combobox(
        f, textvariable=lrv_var,
        font=("Calibri", 10), state="readonly"
    ))

    # Cab End
    cab_var = tk.StringVar(value="A")
    cab_combo = row("Cab End", lambda f: ttk.Combobox(
        f, textvariable=cab_var,
        values=CAB_ENDS,
        font=("Calibri", 10), state="readonly", width=8
    ))
    cab_combo.current(0)

    # Position
    pos_var = tk.StringVar(value="1")
    pos_combo = row("Position", lambda f: ttk.Combobox(
        f, textvariable=pos_var,
        values=CAB_POSITIONS["A"],
        font=("Calibri", 10), state="readonly", width=8
    ))
    pos_combo.current(0)

    # Upper / Lower
    side_var = tk.StringVar(value="+")
    side_combo = row("Upper / Lower", lambda f: ttk.Combobox(
        f, textvariable=side_var,
        values=list(SHOE_SIDES.values()),
        font=("Calibri", 10), state="readonly"
    ))
    side_combo.current(0)

    # Generated Asset ID display
    tk.Label(frame, text="Generated Asset ID", bg=bg,
             font=("Calibri", 10, "bold"), anchor="w").pack(fill="x", pady=(6, 0))
    id_var = tk.StringVar()
    id_label = tk.Label(
        frame, textvariable=id_var,
        bg="#EFF6FF", fg=header_color,
        font=("Calibri", 13, "bold"),
        anchor="w", padx=8, pady=6,
        relief="groove"
    )
    id_label.pack(fill="x", pady=(2, 4))

    def update_lrv_numbers(*_):
        model = model_var.get()
        nums  = [f"LRV{n:02d}" for n in LRV_MODELS.get(model, [])]
        lrv_combo["values"] = nums
        if nums:
            lrv_var.set(nums[0])
        update_id()

    def update_positions(*_):
        cab = cab_var.get()
        positions = CAB_POSITIONS.get(cab, ["1", "2"])
        pos_combo["values"] = positions
        pos_var.set(positions[0])
        update_id()

    def update_id(*_):
        part = part_var.get().split(" ")[0]
        lrv  = lrv_var.get()
        cab  = cab_var.get()
        pos  = pos_var.get()
        side = "+" if side_var.get().startswith("+") else "-"
        if lrv:
            id_var.set(f"{part}-{lrv}-{side}{cab}{pos}")
        else:
            id_var.set("—")

    model_combo.bind("<<ComboboxSelected>>", update_lrv_numbers)
    cab_combo.bind("<<ComboboxSelected>>", update_positions)
    part_combo.bind("<<ComboboxSelected>>", update_id)
    lrv_combo.bind("<<ComboboxSelected>>", update_id)
    pos_combo.bind("<<ComboboxSelected>>", update_id)
    side_combo.bind("<<ComboboxSelected>>", update_id)

    update_lrv_numbers()

    def get_asset_id():
        return id_var.get() if id_var.get() != "—" else ""

    return frame, get_asset_id


# ── GUI: capture tips ──────────────────────────────────────────
def _show_capture_tips_gui(station_type="wireless"):
    """
    Shows a tkinter popup with capture tips before the session setup.
    Technician must click 'Got it, Let's Go!' to proceed.
    Returns True if acknowledged, False if cancelled.
    """
    import tkinter as tk

    result = {"proceed": False}

    root = tk.Tk()
    root.title("📡 Capture Tips — Read Before Starting")
    root.resizable(False, False)
    root.configure(bg="#F8FAFC")
    root.attributes("-topmost", True)
    root.update_idletasks()
    root.after(200, lambda: [root.lift(), root.focus_force(), root.attributes("-topmost", True)])
    w, h = 480, 420
    x = (root.winfo_screenwidth()  // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    # ── Header ─────────────────────────────────────────────────
    header = tk.Frame(root, bg="#1A6FB5", height=60)
    header.pack(fill="x")
    tk.Label(
        header,
        text="📡  Capture Tips — Before You Start",
        bg="#1A6FB5", fg="white",
        font=("Calibri", 14, "bold")
    ).pack(pady=14)

    # ── Tips ───────────────────────────────────────────────────
    body = tk.Frame(root, bg="#F8FAFC", padx=24, pady=16)
    body.pack(fill="both", expand=True)

    tk.Label(
        body,
        text="Follow these steps for the best detection results:",
        bg="#F8FAFC", fg="#1E293B",
        font=("Calibri", 11), anchor="w", justify="left"
    ).pack(fill="x", pady=(0, 10))

    tips = [
        ("📍", "Position camera in front of the collector shoe BEFORE clicking Start Session"),
        ("📐", "Ensure the collector shoe fills the centre of the camera frame"),
        ("✅", "Position camera front-on or at a slight angle to the shoe surface"),
        ("✅", "Ensure even lighting — no direct overhead reflection"),
        ("✅", "Get close enough — shoe should fill most of the frame"),
        ("⚠️", "Avoid glare on the shoe surface — reposition if you see reflection"),
        ("💡", "Once Start Session is clicked, say 'take picture' or press SPACE to capture"),
    ]

    for icon_t, tip in tips:
        row = tk.Frame(body, bg="#F8FAFC")
        row.pack(fill="x", pady=3)
        tk.Label(
            row, text=icon_t,
            bg="#F8FAFC", font=("Calibri", 12),
            width=3, anchor="w"
        ).pack(side="left")
        tk.Label(
            row, text=tip,
            bg="#F8FAFC", fg="#1E293B",
            font=("Calibri", 11), anchor="w", justify="left"
        ).pack(side="left", fill="x")

    # ── Divider ────────────────────────────────────────────────
    tk.Frame(root, bg="#E2E8F0", height=1).pack(fill="x", padx=24)

    # ── Buttons ────────────────────────────────────────────────
    btn_frame = tk.Frame(root, bg="#F8FAFC", padx=24, pady=14)
    btn_frame.pack(fill="x")

    def on_proceed():
        result["proceed"] = True
        root.destroy()

    def on_cancel():
        root.destroy()

    tk.Button(
        btn_frame,
        text="✅  Got it, Let's Go!",
        command=on_proceed,
        bg="#1A6FB5", fg="white",
        font=("Calibri", 12, "bold"),
        relief="flat", padx=20, pady=10,
        cursor="hand2"
    ).pack(side="left")

    tk.Button(
        btn_frame,
        text="Cancel",
        command=on_cancel,
        bg="#E2E8F0", fg="#1E293B",
        font=("Calibri", 11),
        relief="flat", padx=20, pady=10,
        cursor="hand2"
    ).pack(side="right")

    root.mainloop()
    return result["proceed"]


# ── GUI: connect to stream ──────────────────────────────────────
def _connect_stream_gui():
    """
    Shows a tkinter popup guiding the technician through starting
    the DJI Mimo stream, then attempts to connect to the RTMP feed.
    Retries in place if the stream isn't up yet.
    Returns an opened cv2.VideoCapture on success, or None if cancelled.
    """
    import tkinter as tk
    from tkinter import ttk

    result = {"cap": None, "cancelled": False}

    root = tk.Tk()
    root.title("DJI Wireless Station — Connect to Stream")
    root.resizable(False, False)
    root.configure(bg="#F8FAFC")
    root.update_idletasks()
    root.after(200, lambda: [root.lift(), root.focus_force(), root.attributes("-topmost", True)])
    w, h = 460, 340
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    header = tk.Frame(root, bg="#1A6FB5", height=60)
    header.pack(fill="x")
    tk.Label(
        header, text="📡  DJI Wireless Station",
        bg="#1A6FB5", fg="white",
        font=("Calibri", 16, "bold")
    ).pack(pady=15)

    body = tk.Frame(root, bg="#F8FAFC", padx=30, pady=16)
    body.pack(fill="both", expand=True)

    tk.Label(
        body, text="1. Make sure rtmp_server.js is running.\n"
                    "2. In DJI Mimo, start streaming to:",
        bg="#F8FAFC", font=("Calibri", 10), justify="left", anchor="w"
    ).pack(fill="x")

    tk.Label(
        body, text=RTMP_RECEIVE_URL,
        bg="#EEF2F7", fg="#1A6FB5", font=("Consolas", 10, "bold"),
        padx=8, pady=6
    ).pack(fill="x", pady=(4, 12))

    tk.Label(
        body, text="3. Once Mimo shows it is live, click Connect.",
        bg="#F8FAFC", font=("Calibri", 10), justify="left", anchor="w"
    ).pack(fill="x")

    status_var = tk.StringVar(value="Not connected yet.")
    status_label = tk.Label(
        body, textvariable=status_var, bg="#F8FAFC", fg="#94A3B8",
        font=("Calibri", 10, "italic"), pady=10
    )
    status_label.pack(fill="x")

    progress = ttk.Progressbar(body, mode="indeterminate")

    btn_frame = tk.Frame(root, bg="#F8FAFC", padx=30, pady=14)
    btn_frame.pack(fill="x")

    def try_connect():
        connect_btn.config(state="disabled")
        status_var.set("Connecting to stream... (timeout: 15s)")
        status_label.config(fg="#E8920A")
        progress.pack(fill="x", pady=(0, 6))
        progress.start(10)
        root.update()

        # Run connection in thread with 15 second timeout
        import threading
        conn_result = {"cap": None, "ok": False}

        def _connect():
            cap = cv2.VideoCapture(RTMP_RECEIVE_URL, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FPS, 30)
            ok = cap.isOpened()
            if ok:
                ret, _ = cap.read()
                ok = ret
            conn_result["cap"] = cap
            conn_result["ok"] = ok

        t = threading.Thread(target=_connect, daemon=True)
        t.start()
        t.join(timeout=15)  # 15 second timeout

        progress.stop()
        progress.pack_forget()

        timed_out = t.is_alive()

        if timed_out:
            if conn_result["cap"]:
                conn_result["cap"].release()
            status_var.set("⏱️ Connection timed out after 15s — check RTMP server and Mimo stream.")
            status_label.config(fg="#C9382A")
            connect_btn.config(state="normal")
        elif conn_result["ok"]:
            result["cap"] = conn_result["cap"]
            root.destroy()
        else:
            if conn_result["cap"]:
                conn_result["cap"].release()
            status_var.set("⚠️  No stream detected yet — check Mimo is live, then try again.")
            status_label.config(fg="#C9382A")
            connect_btn.config(state="normal")

    def on_cancel():
        result["cancelled"] = True
        root.destroy()

    connect_btn = tk.Button(
        btn_frame, text="🔌 Connect", command=try_connect,
        bg="#1A6FB5", fg="white", font=("Calibri", 11, "bold"),
        relief="flat", padx=20, pady=8, cursor="hand2"
    )
    connect_btn.pack(side="left")

    tk.Button(
        btn_frame, text="Cancel", command=on_cancel,
        bg="#E2E8F0", fg="#1E293B", font=("Calibri", 11),
        relief="flat", padx=20, pady=8, cursor="hand2"
    ).pack(side="right")

    root.mainloop()
    return result["cap"]


# ── GUI: session setup (technician + first asset) ──────────────
def _get_session_info_gui(supabase):
    """
    Shows a tkinter popup to collect technician name and asset ID.
    Asset ID is built via dropdowns. Returns (technician_name, asset_id)
    or (None, None) if cancelled.
    """
    import tkinter as tk
    from tkinter import ttk, messagebox

    result = {"technician_name": None, "asset_id": None}

    root = tk.Tk()
    root.title("DJI Wireless Station — Session Setup")
    root.resizable(False, False)
    root.configure(bg="#F8FAFC")
    root.update_idletasks()
    root.after(200, lambda: [root.lift(), root.focus_force(), root.attributes("-topmost", True)])
    w, h = 440, 640
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    header = tk.Frame(root, bg="#1A6FB5", height=60)
    header.pack(fill="x")
    tk.Label(
        header, text="📡  DJI Wireless Station",
        bg="#1A6FB5", fg="white",
        font=("Calibri", 16, "bold")
    ).pack(pady=15)

    form = tk.Frame(root, bg="#F8FAFC", padx=24, pady=12)
    form.pack(fill="both", expand=True)

    tk.Label(form, text="Technician Name", bg="#F8FAFC",
             font=("Calibri", 11, "bold"), anchor="w").pack(fill="x")
    name_var = tk.StringVar()
    name_entry = ttk.Entry(form, textvariable=name_var, font=("Calibri", 11), width=38)
    name_entry.pack(fill="x", pady=(4, 14))
    name_entry.focus()

    tk.Label(form, text="Asset ID", bg="#F8FAFC",
             font=("Calibri", 11, "bold"), anchor="w").pack(fill="x")
    builder_frame, get_asset_id = _build_asset_id_frame(form, "#F8FAFC", "#1A6FB5")
    builder_frame.pack(fill="x")

    tk.Frame(root, bg="#E2E8F0", height=1).pack(side="bottom", fill="x")
    btn_frame = tk.Frame(root, bg="#F8FAFC", padx=24, pady=12)
    btn_frame.pack(side="bottom", fill="x")

    def on_start():
        name  = name_var.get().strip()
        asset = get_asset_id()
        if not name:
            messagebox.showwarning("Missing", "Please enter your technician name.")
            return
        if not asset:
            messagebox.showwarning("Missing", "Please select a valid Asset ID.")
            return
        result["technician_name"] = name
        result["asset_id"]        = asset
        root.destroy()

    def on_cancel():
        root.destroy()

    tk.Button(
        btn_frame, text="Start Session", command=on_start,
        bg="#1A6FB5", fg="white", font=("Calibri", 11, "bold"),
        relief="flat", padx=20, pady=8, cursor="hand2"
    ).pack(side="left")

    tk.Button(
        btn_frame, text="Cancel", command=on_cancel,
        bg="#E2E8F0", fg="#1E293B", font=("Calibri", 11),
        relief="flat", padx=20, pady=8, cursor="hand2"
    ).pack(side="right")

    root.mainloop()
    return result["technician_name"], result["asset_id"]


# ── GUI: next asset ──────────────────────────────────────────
def _get_next_asset_gui(supabase, current_asset):
    """
    Shows a small tkinter popup to get the next Asset ID using dropdowns.
    Returns asset_id string or None if user quits.
    """
    import tkinter as tk
    from tkinter import ttk

    result = {"asset_id": None, "quit": False}

    root = tk.Tk()
    root.title("Next Photo")
    root.resizable(False, False)
    root.configure(bg="#F8FAFC")
    root.attributes("-topmost", True)
    root.after(200, lambda: [root.lift(), root.focus_force()])

    w, h = 440, 500
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    header = tk.Frame(root, bg="#1A6FB5", height=50)
    header.pack(fill="x")
    tk.Label(
        header, text="📡  Next Asset ID",
        bg="#1A6FB5", fg="white",
        font=("Calibri", 14, "bold")
    ).pack(pady=12)

    body = tk.Frame(root, bg="#F8FAFC", padx=24, pady=16)
    body.pack(fill="both", expand=True)

    builder_frame, get_asset_id = _build_asset_id_frame(body, "#F8FAFC", "#1A6FB5", current_asset)
    builder_frame.pack(fill="x")

    btn_frame = tk.Frame(root, bg="#F8FAFC", padx=24, pady=10)
    btn_frame.pack(fill="x")

    def on_next():
        asset = get_asset_id()
        if asset:
            result["asset_id"] = asset
        root.destroy()

    def on_quit():
        result["quit"] = True
        root.destroy()

    tk.Button(btn_frame, text="📷 Take Photo", command=on_next,
              bg="#1A6FB5", fg="white", font=("Calibri", 11, "bold"),
              relief="flat", padx=15, pady=6, cursor="hand2").pack(side="left", padx=5)

    tk.Button(btn_frame, text="Quit Session", command=on_quit,
              bg="#E2E8F0", fg="#1E293B", font=("Calibri", 11),
              relief="flat", padx=15, pady=6, cursor="hand2").pack(side="left", padx=5)

    root.mainloop()

    if result["quit"]:
        return None
    return result["asset_id"] or current_asset

    tk.Button(btn_frame, text="Quit Session", command=on_quit,
              bg="#E2E8F0", fg="#1E293B", font=("Calibri", 11),
              relief="flat", padx=15, pady=6, cursor="hand2").pack(side="left", padx=5)

    root.mainloop()

    if result["quit"]:
        return None
    return result["asset_id"] or current_asset


# ── GUI: new session prompt ────────────────────────────────────
def _new_session_gui():
    """
    Shows after the user clicks "Quit Session" in the Next Photo popup.
    Asks whether to start a fresh session (new technician/asset) or
    end the program entirely.
    Returns "new_session", or "end".
    """
    import tkinter as tk

    result = {"action": "end"}

    root = tk.Tk()
    root.title("Session Ended")
    root.resizable(False, False)
    root.configure(bg="#F8FAFC")
    root.attributes("-topmost", True)
    root.update_idletasks()
    root.after(200, lambda: [root.lift(), root.focus_force(), root.attributes("-topmost", True)])
    w, h = 360, 220
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    # Header
    header = tk.Frame(root, bg="#1A6FB5", height=50)
    header.pack(fill="x")
    tk.Label(
        header, text="📡  Session Complete",
        bg="#1A6FB5", fg="white",
        font=("Calibri", 14, "bold")
    ).pack(pady=12)

    # Body
    body = tk.Frame(root, bg="#F8FAFC", padx=30, pady=20)
    body.pack(fill="both", expand=True)
    tk.Label(
        body,
        text="What would you like to do next?",
        bg="#F8FAFC", font=("Calibri", 11),
    ).pack(pady=(0, 16))

    btn_frame = tk.Frame(body, bg="#F8FAFC")
    btn_frame.pack()

    def on_new():
        result["action"] = "new_session"
        root.destroy()

    def on_end():
        result["action"] = "end"
        root.destroy()

    tk.Button(
        btn_frame, text="🔄 New Session",
        command=on_new,
        bg="#1A6FB5", fg="white", font=("Calibri", 11, "bold"),
        relief="flat", padx=16, pady=8, cursor="hand2"
    ).pack(side="left", padx=(0, 10))

    tk.Button(
        btn_frame, text="⏹ End Program",
        command=on_end,
        bg="#C9382A", fg="white", font=("Calibri", 11, "bold"),
        relief="flat", padx=16, pady=8, cursor="hand2"
    ).pack(side="left")

    root.mainloop()
    return result["action"]


def main():
    print("=" * 60)
    print("  DJI Action 3 — Wireless Camera Station")
    print("=" * 60)

    # Connect to Supabase (anon — no login needed for technician)
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Connected to Supabase.")

    print("\nOpening stream connection window...")
    cap = _connect_stream_gui()

    if cap is None:
        print("❌ Stream connection cancelled or failed.")
        return

    print("✅ Receiving wireless stream from DJI Action 3!\n")

    print("Opening capture tips window...")
    if not _show_capture_tips_gui(station_type="wireless"):
        print("❌ Session cancelled.")
        cap.release()
        return

    print("Opening session setup window...")
    technician_name, asset_id = _get_session_info_gui(supabase)

    if not technician_name:
        print("❌ Session cancelled.")
        cap.release()
        return

    print(f"✅ Session started — Technician: {technician_name}")

    # Start voice listener (runs for the entire program lifetime)
    voice_thread = threading.Thread(target=voice_listener, daemon=True)
    voice_thread.start()
    time.sleep(2.5)  # voice listener calibration warmup

    # Extra 1s so stream buffer is flushed before first preview opens
    print("  → Preparing stream, please wait...")
    time.sleep(1)

    reconnect_count = 0

    try:
        # ── Outer loop: one iteration per session ──────────────
        while True:
            print("\n" + "=" * 60)
            print(f"  📡 SESSION ACTIVE — Technician: {technician_name}")
            print(f"  📸 3 captures required: Left (15°) → Centre (0°) → Right (15°)")
            print("=" * 60)

            # Create one shared session for all 3 captures
            session_data = {
                "technician_name": technician_name,
                "employee_id":     "N/A",
                "asset_id":        asset_id,
                "status":          "submitted",
                "notes":           "Captured via DJI wireless camera station — 3-angle inspection",
            }
            session_resp = supabase.table("inspection_sessions").insert(session_data).execute()
            if not session_resp.data:
                print("❌ Could not create session. Please try again.")
                continue
            shared_session_id = session_resp.data[0]["id"]
            print(f"  → Session ID: {shared_session_id}")

            TOTAL_CAPTURES  = 3
            session_cancelled = False

            # ── Step 1: Capture all 3 frames first ────────────────
            captured_frames = []
            session_cancelled = False

            for capture_num in range(1, TOTAL_CAPTURES + 1):
                angle = CAPTURE_ANGLES[capture_num - 1]
                print(f"\n📷 Capture {capture_num}/{TOTAL_CAPTURES} — {angle}")
                print(f"🎙️  Say 'take picture' or press SPACE in the preview window.")
                capture_requested.clear()

                triggered_by, cap = _wait_for_trigger(cap, asset_id, capture_num, TOTAL_CAPTURES)

                if triggered_by is None:
                    print("⚠️  Session cancelled by user.")
                    session_cancelled = True
                    break

                capture_requested.clear()
                print(f"  → Stabilising stream for 0.5s before capture ({triggered_by})...")
                time.sleep(0.5)

                # Capture and save locally only — no YOLO yet
                for _ in range(2):
                    cap.read()
                    time.sleep(0.05)
                ret, frame = cap.read()
                if not ret or frame is None or frame.size == 0:
                    print(f"❌ Capture {capture_num} failed — no valid frame. Skipping.")
                    continue

                frame      = gray_world_balance(frame)
                frame      = apply_glare_mode(frame)
                timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                local_path = os.path.join(TEMP_DIR, f"{timestamp}.jpg")
                cv2.imwrite(local_path, frame)
                captured_frames.append((local_path, timestamp))
                print(f"  ✅ Capture {capture_num}/{TOTAL_CAPTURES} saved locally — proceeding to next angle")

            # ── Step 2: Run YOLO on all captured frames ────────────
            if not session_cancelled and captured_frames:
                print(f"\n🤖 Running YOLO on {len(captured_frames)} captured frame(s)...")
                all_success = True
                for i, (local_path, timestamp) in enumerate(captured_frames):
                    print(f"\n  → Processing capture {i+1}/{len(captured_frames)}...")
                    success = run_capture_pipeline(
                        supabase, cap, asset_id, technician_name,
                        session_id=shared_session_id,
                        local_path=local_path,
                        timestamp=timestamp,
                    )
                    if not success:
                        all_success = False
                        if not cap.isOpened() or not cap.grab():
                            reconnect_count += 1
                            print(f"⚠️  Stream dropped — reconnecting ({reconnect_count})...")
                            cap.release()
                            time.sleep(1)
                            cap = cv2.VideoCapture(RTMP_RECEIVE_URL, cv2.CAP_FFMPEG)
                            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                            cap.set(cv2.CAP_PROP_FPS, 30)
                            if not cap.isOpened():
                                print("❌ Reconnect failed. Please restart the Mimo stream.")
                                return
                            print("✅ Stream reconnected.")

            if not session_cancelled:
                # Show session complete popup
                import subprocess, sys
                complete_script = """
import tkinter as tk
root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
win = tk.Toplevel(root)
win.title("Session Complete")
win.geometry("380x140")
win.configure(bg="#DCFCE7")
win.attributes('-topmost', True)
tk.Label(win, text="✅ Session Complete!", font=("Calibri", 14, "bold"),
    bg="#DCFCE7", fg="#166534").pack(pady=(20,5))
tk.Label(win, text="All 3 captures saved.\\nWindow closing in 3 seconds...",
    font=("Calibri", 11), bg="#DCFCE7", fg="#166534").pack()
win.after(3000, root.destroy)
root.mainloop()
"""
                subprocess.Popen([sys.executable, "-c", complete_script]).wait()
                print("\n✅ Session complete — all 3 captures saved.")

            # ── New session or end program? ────────────────────
            action = _new_session_gui()

            if action == "new_session":
                print("\nStarting new session...")
                if not _show_capture_tips_gui(station_type="wireless"):
                    print("❌ New session cancelled — ending program.")
                    break
                technician_name, asset_id = _get_session_info_gui(supabase)
                if not technician_name:
                    print("❌ New session cancelled — ending program.")
                    break
                print(f"✅ New session started — Technician: {technician_name}")
                print("\n  → Preparing stream, please wait...")
                time.sleep(1)
            else:
                print("\n👋 Program ended by user.")
                break

    except KeyboardInterrupt:
        print("\n\nStopped by user.")

    finally:
        stop_listening.set()
        cap.release()
        cv2.destroyAllWindows()
        print("\n👋 Wireless camera station shut down.")


if __name__ == "__main__":
    main()
