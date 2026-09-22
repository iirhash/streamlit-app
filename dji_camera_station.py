# dji_camera_station.py
# ── DJI Action 3 Camera Station (Technician, no login) ────────
# Run with: python dji_camera_station.py
#
# Wired (USB) capture only, voice-triggered with SPACE as a
# keyboard fallback (useful for testing in noisy environments
# where speech recognition picks up background conversation).
# For each photo:
#   1. Type the Asset ID being inspected (console prompt)
#   2. A preview window opens — say "take picture" OR press
#      SPACE to capture. Captures, corrects, runs YOLO,
#      uploads raw + annotated images to Supabase, logs result
#   3. Loop back to step 1 for the next asset/photo
#
# This script does NOT require SAP login — it matches the
# "technician = no login, public access" design used throughout
# this project. Supervisors/IC/management can still upload
# corrections manually via the Defect Viewer page in the
# Streamlit dashboard if a capture here fails or looks wrong.
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
from core.yolo_detect import detect_defects, CONFIDENCE_THRESHOLD, SCUFF_MARKS_THRESHOLD, get_status_label, increment_capture_count, RETRAIN_THRESHOLD, ROBOFLOW_CLASS_MAP

# ── Camera settings ─────────────────────────────────────────────
DJI_INDEX = 1   # change to 0 if DJI doesn't appear on index 1

# ── Voice trigger phrases ──────────────────────────────────────
TRIGGER_PHRASES = ["take picture", "take a picture", "take photo", "capture"]

# ── Local temp folder for processing before upload ─────────────
TEMP_DIR = "camera_station_temp"
os.makedirs(TEMP_DIR, exist_ok=True)

capture_requested = threading.Event()
stop_listening     = threading.Event()


def sharpen_image(frame, strength=1.0):
    """
    Unsharp mask sharpening — enhances surface detail for better YOLO detection.
    strength=1.0 (medium) selected based on visual comparison test.
    Helps YOLO detect fine surface features like grooves and scuff marks.
    """
    import numpy as np
    blurred   = cv2.GaussianBlur(frame, (0, 0), 3)
    sharpened = cv2.addWeighted(frame, 1 + strength, blurred, -strength, 0)
    return sharpened


def gray_world_balance(frame):
    """Apply gray world white balance correction."""
    result = frame.copy().astype("float32")
    avg_b  = result[:, :, 0].mean()
    avg_g  = result[:, :, 1].mean()
    avg_r  = result[:, :, 2].mean()
    avg    = (avg_b + avg_g + avg_r) / 3
    result[:, :, 0] = (result[:, :, 0] * (avg / avg_b)).clip(0, 255)
    result[:, :, 1] = (result[:, :, 1] * (avg / avg_g)).clip(0, 255)
    result[:, :, 2] = (result[:, :, 2] * (avg / avg_r)).clip(0, 255)
    return result.astype("uint8")


def apply_glare_mode(frame):
    """
    Greyscale + mild CLAHE + gentle sharpen for glare-affected captures.
    Mutes colour channel glare, slightly enhances local contrast.
    Returns 3-channel BGR image for YOLO compatibility.
    """
    grey     = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    clahe    = cv2.createCLAHE(clipLimit=0.5, tileGridSize=(8, 8))
    grey_eq  = clahe.apply(grey)
    blurred  = cv2.GaussianBlur(grey_eq, (0, 0), 3)
    sharpened = cv2.addWeighted(grey_eq, 1.5, blurred, -0.5, 0)
    return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)



    """Corrects yellowish tinge by neutralising per-channel colour cast."""
    import numpy as np
    result = frame.astype("float32")
    avg_b, avg_g, avg_r = (result[:, :, i].mean() for i in range(3))
    avg_gray = (avg_b + avg_g + avg_r) / 3
    result[:, :, 0] *= avg_gray / max(avg_b, 1)
    result[:, :, 1] *= avg_gray / max(avg_g, 1)
    result[:, :, 2] *= avg_gray / max(avg_r, 1)
    return result.clip(0, 255).astype("uint8")


def voice_listener():
    """Background thread — listens for 'take picture' and sets the event."""
    recognizer = sr.Recognizer()
    mic        = sr.Microphone()

    with mic as source:
        print("🎙️  Calibrating microphone for ambient noise...")
        recognizer.adjust_for_ambient_noise(source, duration=2)
    print("🎙️  Voice control ready — say 'take picture' when ready.\n")

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
            print(f"⚠️  Speech recognition service error: {e}")
        except Exception as e:
            print(f"⚠️  Voice listener error: {e}")


CAPTURE_ANGLES = [
    "Angle camera 15° to the LEFT",
    "Angle camera CENTRE (0°) — straight on",
    "Angle camera 15° to the RIGHT",
]

def _wait_for_trigger(cap, asset_id, capture_num=1, total=3):
    """
    Opens a live preview window and waits for either:
      - SPACE key pressed in the window, or
      - capture_requested event set by the voice listener thread
    Returns "voice", "space", or None if the window was closed (Q pressed).
    Shows capture counter and angle guidance in the window title.
    """
    angle    = CAPTURE_ANGLES[capture_num - 1]
    win_title = f"Capture {capture_num}/{total} — {angle} | SPACE = capture | Q = cancel session"
    cv2.namedWindow(win_title, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_title, 640, 360)

    while True:
        ret, frame = cap.read()
        if ret:
            preview = gray_world_balance(frame)
            # Draw capture counter on preview
            h, w = preview.shape[:2]
            cv2.putText(preview, f"Capture {capture_num}/{total}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.putText(preview, angle, (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
            cv2.imshow(win_title, preview)

        key = cv2.waitKey(1) & 0xFF

        if key == ord(" "):
            cv2.destroyAllWindows()
            return "space"

        if key == ord("q"):
            cv2.destroyAllWindows()
            return None

        if capture_requested.is_set():
            cv2.destroyAllWindows()
            return "voice"


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


def run_capture_pipeline(supabase, cap, asset_id, technician_name, session_id=None, local_path=None, timestamp=None):
    """
    Processes one frame through YOLO and uploads to Supabase.
    If local_path is provided, uses that pre-captured frame instead of capturing a new one.
    Returns True on success, False on failure.
    """
    # ── Capture frame if not pre-captured ──────────────────────
    if local_path is None:
        print("  → Flushing camera buffer...")
        for _ in range(3):
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
        print(f"📸 Frame captured and saved locally: {local_path}")
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
                "notes":           "Captured via DJI camera station (voice trigger)",
            }
            print("  → Inserting inspection session...")
            session_resp = supabase.table("inspection_sessions").insert(session_data).execute()
            print(f"  → Session response: {session_resp.data}")
            if not session_resp.data:
                raise Exception("Session insert returned no data — RLS may be blocking anon insert.")
            session_id = session_resp.data[0]["id"]
            print(f"  → Session ID: {session_id}")
        else:
            print(f"  → Using existing Session ID: {session_id}")

        # 2. Upload raw image
        raw_path = f"{asset_id}/{session_id}/{timestamp}_raw.jpg"
        print(f"  → Uploading raw image to raw-photos/{raw_path}...")
        with open(local_path, "rb") as f:
            upload_resp = supabase.storage.from_("raw-photos").upload(
                path=raw_path, file=f, file_options={"content-type": "image/jpeg"}
            )
        print(f"  → Upload response: {upload_resp}")
        print(f"☁️  Uploaded raw image to raw-photos/{raw_path}")

        # 3. Run YOLO detection
        print("  → Running YOLO detection...")
        result = detect_defects(local_path)
        print(f"  → YOLO result: defect={result.get('defect')} confidence={result.get('confidence')} error={result.get('error')}")
        annotated_path = None

        if result.get("error") is None and result.get("annotated") is not None:
            annotated_local = os.path.join(TEMP_DIR, f"{timestamp}_annotated.jpg")
            cv2.imwrite(annotated_local, cv2.cvtColor(result["annotated"], cv2.COLOR_RGB2BGR))

            annotated_path = f"{asset_id}/{session_id}/{timestamp}_annotated.jpg"
            print(f"  → Uploading annotated image to annotated-photos/{annotated_path}...")
            with open(annotated_local, "rb") as f:
                ann_resp = supabase.storage.from_("annotated-photos").upload(
                    path=annotated_path, file=f, file_options={"content-type": "image/jpeg"}
                )
            print(f"  → Annotated upload response: {ann_resp}")
            print(f"☁️  Uploaded annotated image to annotated-photos/{annotated_path}")
            os.remove(annotated_local)
        else:
            print(f"⚠️  YOLO not available ({result.get('error', 'unknown')}) — raw image saved without annotation.")

        # 4. Log defect records — one per detection above threshold
        print("  → Inserting defect records...")
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
            defect_resp = supabase.table("defect_records").insert(defect_data).execute()
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
        print(f"❌ Upload/processing error: {e}")
        print("   The photo was captured locally but NOT saved to Supabase.")
        print("   Please try again, or ask a supervisor to upload it manually.\n")
        return False


def _show_capture_tips_gui(station_type="wired"):
    """
    Shows a tkinter popup with capture tips before the session setup.
    Technician must click 'Got it, Let's Go!' to proceed.
    Returns True if acknowledged, False if cancelled.
    """
    import tkinter as tk

    result = {"proceed": False}

    root = tk.Tk()
    root.title("📷 Capture Tips — Read Before Starting")
    root.resizable(False, False)
    root.configure(bg="#F8FAFC")
    root.attributes("-topmost", True)

    root.update_idletasks()
    w, h = 480, 420
    x = (root.winfo_screenwidth()  // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    # ── Header ─────────────────────────────────────────────────
    header = tk.Frame(root, bg="#0A8A72", height=60)
    header.pack(fill="x")
    icon = "📷" if station_type == "wired" else "📡"
    tk.Label(
        header,
        text=f"{icon}  Capture Tips — Before You Start",
        bg="#0A8A72", fg="white",
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
        ("✅", "Position camera front-on to the shoe surface"),
        ("✅", "Ensure even lighting — no direct overhead reflection"),
        ("✅", "Get close enough — shoe should fill most of the frame"),
        ("⚠️", "Avoid glare on the shoe surface — reposition if you see reflection"),
        ("⚠️", "Hold camera steady before pressing SPACE or saying 'take picture'"),
        ("💡", "Good lighting = higher confidence score"),
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
        bg="#0A8A72", fg="white",
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

# Flat lookup: number → model name
LRV_NUM_TO_MODEL = {}
for model, nums in LRV_MODELS.items():
    for n in nums:
        LRV_NUM_TO_MODEL[n] = model

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
    Returns a function get_asset_id() that returns the currently selected ID.

    Dropdown flow:
      Part Type → LRV Model → LRV Number → Cab End → Position → Upper/Lower
      → Generated: CS-LRV01-+A1
    """
    import tkinter as tk
    from tkinter import ttk

    frame = tk.Frame(parent, bg=bg)

    # ── Row labels + dropdowns ─────────────────────────────────
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

    # ── Generated Asset ID display ─────────────────────────────
    tk.Label(frame, text="Generated Asset ID", bg=bg,
             font=("Calibri", 10, "bold"), anchor="w").pack(fill="x", pady=(6, 0))
    id_var = tk.StringVar()
    id_label = tk.Label(
        frame, textvariable=id_var,
        bg="#F0FDF4", fg=header_color,
        font=("Calibri", 13, "bold"),
        anchor="w", padx=8, pady=6,
        relief="groove"
    )
    id_label.pack(fill="x", pady=(2, 4))

    # ── Update logic ───────────────────────────────────────────
    def update_lrv_numbers(*_):
        model = model_var.get()
        nums  = [f"LRV{n:02d}" for n in LRV_MODELS.get(model, [])]
        lrv_combo["values"] = nums
        if nums:
            lrv_var.set(nums[0])
        update_id()

    def update_positions(*_):
        cab  = cab_var.get()
        positions = CAB_POSITIONS.get(cab, ["1", "2"])
        pos_combo["values"] = positions
        pos_var.set(positions[0])
        update_id()

    def update_id(*_):
        part  = part_var.get().split(" ")[0]   # "CS"
        lrv   = lrv_var.get()                  # "LRV01"
        cab   = cab_var.get()                  # "A"
        pos   = pos_var.get()                  # "1"
        side  = "+" if side_var.get().startswith("+") else "-"
        if lrv:
            asset_id = f"{part}-{lrv}-{side}{cab}{pos}"
            id_var.set(asset_id)
        else:
            id_var.set("—")

    model_combo.bind("<<ComboboxSelected>>", update_lrv_numbers)
    cab_combo.bind("<<ComboboxSelected>>", update_positions)
    part_combo.bind("<<ComboboxSelected>>", update_id)
    lrv_combo.bind("<<ComboboxSelected>>", update_id)
    pos_combo.bind("<<ComboboxSelected>>", update_id)
    side_combo.bind("<<ComboboxSelected>>", update_id)

    # Initialise
    update_lrv_numbers()

    def get_asset_id():
        return id_var.get() if id_var.get() != "—" else ""

    return frame, get_asset_id


def _get_session_info_gui(supabase):
    """
    Shows a tkinter popup to collect technician name and asset ID.
    Asset ID is built via dropdowns (Part Type → LRV → Cab End → Position → Side).
    Returns (technician_name, asset_id) or (None, None) if cancelled.
    """
    import tkinter as tk
    from tkinter import ttk, messagebox

    result = {"technician_name": None, "asset_id": None}

    root = tk.Tk()
    root.title("DJI Camera Station — Session Setup")
    root.resizable(False, False)
    root.configure(bg="#F8FAFC")

    root.update_idletasks()
    w, h = 440, 640
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    # ── Header ────────────────────────────────────────────────
    header = tk.Frame(root, bg="#0A8A72", height=60)
    header.pack(fill="x")
    tk.Label(
        header, text="📷  DJI Camera Station",
        bg="#0A8A72", fg="white",
        font=("Calibri", 16, "bold")
    ).pack(pady=15)

    # ── Form ──────────────────────────────────────────────────
    form = tk.Frame(root, bg="#F8FAFC", padx=24, pady=12)
    form.pack(fill="both", expand=True)

    # Technician name
    tk.Label(form, text="Technician Name", bg="#F8FAFC",
             font=("Calibri", 11, "bold"), anchor="w").pack(fill="x")
    name_var = tk.StringVar()
    name_entry = ttk.Entry(form, textvariable=name_var, font=("Calibri", 11), width=38)
    name_entry.pack(fill="x", pady=(4, 14))
    name_entry.focus()

    # ── Asset ID builder ──────────────────────────────────────
    tk.Label(form, text="Asset ID", bg="#F8FAFC",
             font=("Calibri", 11, "bold"), anchor="w").pack(fill="x")
    builder_frame, get_asset_id = _build_asset_id_frame(form, "#F8FAFC", "#0A8A72")
    builder_frame.pack(fill="x")

    # ── Buttons — packed at bottom, always visible ────────────
    btn_frame = tk.Frame(root, bg="#F8FAFC", padx=24, pady=12)
    btn_frame.pack(side="bottom", fill="x")

    tk.Frame(root, bg="#E2E8F0", height=1).pack(side="bottom", fill="x")

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
        bg="#0A8A72", fg="white", font=("Calibri", 11, "bold"),
        relief="flat", padx=20, pady=8, cursor="hand2"
    ).pack(side="left")

    tk.Button(
        btn_frame, text="Cancel", command=on_cancel,
        bg="#E2E8F0", fg="#1E293B", font=("Calibri", 11),
        relief="flat", padx=20, pady=8, cursor="hand2"
    ).pack(side="right")

    root.mainloop()
    return result["technician_name"], result["asset_id"]


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

    w, h = 440, 500
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    # ── Header ────────────────────────────────────────────────
    header = tk.Frame(root, bg="#0A8A72", height=50)
    header.pack(fill="x")
    tk.Label(
        header, text="📷  Next Asset ID",
        bg="#0A8A72", fg="white",
        font=("Calibri", 14, "bold")
    ).pack(pady=12)

    body = tk.Frame(root, bg="#F8FAFC", padx=24, pady=16)
    body.pack(fill="both", expand=True)

    builder_frame, get_asset_id = _build_asset_id_frame(body, "#F8FAFC", "#0A8A72", current_asset)
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
              bg="#0A8A72", fg="white", font=("Calibri", 11, "bold"),
              relief="flat", padx=15, pady=6, cursor="hand2").pack(side="left", padx=5)

    tk.Button(btn_frame, text="Quit Session", command=on_quit,
              bg="#E2E8F0", fg="#1E293B", font=("Calibri", 11),
              relief="flat", padx=15, pady=6, cursor="hand2").pack(side="left", padx=5)

    root.mainloop()

    if result["quit"]:
        return None
    return result["asset_id"] or current_asset


def main():
    print("=" * 60)
    print("  DJI Camera Station — Technician Capture (no login)")
    print("=" * 60)

    # Connect to Supabase
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Connected to Supabase.")

    # ── Camera connection check with timeout ─────────────────────
    import threading
    import tkinter as tk
    from tkinter import messagebox

    connection_result = {"cap": None, "ret": False}

    def _try_connect():
        try:
            cap = cv2.VideoCapture(DJI_INDEX, cv2.CAP_DSHOW)
            ret, _ = cap.read()
            connection_result["cap"] = cap
            connection_result["ret"] = ret
        except Exception:
            pass

    read_thread = threading.Thread(target=_try_connect, daemon=True)
    read_thread.start()
    read_thread.join(timeout=10)

    timed_out = read_thread.is_alive()

    if timed_out or not connection_result["ret"]:
        if connection_result["cap"]:
            try:
                connection_result["cap"].release()
            except:
                pass

        msg = (
            "⏱️ Camera connection timed out after 10 seconds.\n\n"
            "Please check:\n"
            "• USB-C cable is plugged in securely\n"
            "• Camera is switched on\n"
            "• Camera is in USB/Webcam mode\n\n"
            "Then try launching the camera station again."
        ) if timed_out else (
            "❌ Could not connect to DJI Action 3.\n\n"
            "Please check:\n"
            "• USB-C cable is plugged in\n"
            "• Camera is switched on\n"
            "• Camera is in USB/Webcam mode\n\n"
            "Then try launching the camera station again."
        )
        title = "Camera Timeout" if timed_out else "Camera Not Found"

        print(f"  ❌ {title}")

        # Use a fresh isolated tkinter instance
        import subprocess
        import sys
        # Show error via simple tkinter script to avoid root window conflicts
        err_script = f"""
import tkinter as tk
from tkinter import messagebox
root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
root.after(100, lambda: root.focus_force())
messagebox.showerror({repr(title)}, {repr(msg)})
root.destroy()
"""
        subprocess.Popen([sys.executable, "-c", err_script]).wait()
        return

    cap = connection_result["cap"]
    print("✅ Camera connected and ready.\n")

    print("Opening capture tips window...")
    if not _show_capture_tips_gui(station_type="wired"):
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

    # Start voice listener
    voice_thread = threading.Thread(target=voice_listener, daemon=True)
    voice_thread.start()
    time.sleep(2.5)

    print("\n" + "=" * 60)
    print("  📡 CAMERA READY — connected and listening for voice trigger")
    print("=" * 60)

    try:
        while True:
            print(f"\n🔧 Starting new inspection — Asset ID = {asset_id}")
            print(f"📸 3 captures required: Left (15°) → Centre (0°) → Right (15°)")

            # Create one shared session for all 3 captures
            session_data = {
                "technician_name": technician_name,
                "employee_id":     "N/A",
                "asset_id":        asset_id,
                "status":          "submitted",
                "notes":           "Captured via DJI camera station — 3-angle inspection",
            }
            session_resp = supabase.table("inspection_sessions").insert(session_data).execute()
            if not session_resp.data:
                print("❌ Could not create session. Please try again.")
                continue
            shared_session_id = session_resp.data[0]["id"]
            print(f"  → Session ID: {shared_session_id}")

            # ── Step 1: Capture all 3 frames first ────────────────
            TOTAL_CAPTURES  = 3
            captured_frames = []  # store (local_path, timestamp) for each capture
            session_cancelled = False

            for capture_num in range(1, TOTAL_CAPTURES + 1):
                angle = CAPTURE_ANGLES[capture_num - 1]
                print(f"\n📷 Capture {capture_num}/{TOTAL_CAPTURES} — {angle}")
                print(f"🎙️  Say 'take picture' or press SPACE in the preview window.")
                capture_requested.clear()

                triggered_by = _wait_for_trigger(cap, asset_id, capture_num, TOTAL_CAPTURES)

                if triggered_by is None:
                    print("⚠️  Session cancelled by user.")
                    session_cancelled = True
                    break

                capture_requested.clear()
                print(f"  → Stabilising camera for 0.5s before capture ({triggered_by})...")
                time.sleep(0.5)

                # Capture and save locally only — no YOLO yet
                print("  → Flushing camera buffer...")
                for _ in range(3):
                    cap.read()
                    time.sleep(0.05)
                ret, frame = cap.read()
                if not ret or frame is None or frame.size == 0:
                    print(f"❌ Capture {capture_num} failed — no valid frame. Skipping.")
                    continue

                frame     = gray_world_balance(frame)
                frame     = apply_glare_mode(frame)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
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
                        print(f"  ⚠️ Capture {i+1} processing failed.")

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

            # ── GUI popup for next asset ───────────────────────
            next_asset = _get_next_asset_gui(supabase, asset_id)

            if next_asset is None:
                print("\n👋 Session ended by user.")
                break

            asset_id = next_asset

    except KeyboardInterrupt:
        print("\n\nStopped by user.")

    finally:
        stop_listening.set()
        cap.release()
        cv2.destroyAllWindows()
        print("\n👋 Camera station shut down.")


if __name__ == "__main__":
    main()
