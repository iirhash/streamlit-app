# core/yolo_detect.py
# ── YOLO Defect Detection — Model Switching Architecture ──────
#
# To switch models, change MODEL_PATH below:
#   "yolov8n.pt"                              — generic nano
#   "yolov8m.pt"                              — generic medium (benchmarked)
#   "roboflow:piston-surface-defect-1-gjys9/2" — Roboflow trained model
#   "lrt_model.pt"                            — custom trained LRT model
#
# Everything else in the pipeline stays the same regardless
# of which model is loaded — no other files need to change.
# ─────────────────────────────────────────────────────────────

import os
import logging

log = logging.getLogger(__name__)

# ── MODEL CONFIGURATION ───────────────────────────────────────
# Change this one line to switch models across the entire system

MODEL_PATH = "roboflow:piston-surface-defect-1-gjys9/11"

# ── Roboflow API settings ──────────────────────────────────────
ROBOFLOW_API_KEY = "f2JiQ0Vkd0JRIDZ8UP5a"
ROBOFLOW_API_URL = "https://serverless.roboflow.com"

# Model metadata
MODEL_INFO = {
    "yolov8n.pt":   {"name": "YOLOv8 Nano",                    "trained": False, "version": "generic"},
    "yolov8m.pt":   {"name": "YOLOv8 Medium",                  "trained": False, "version": "generic"},
    "yolov8l.pt":   {"name": "YOLOv8 Large",                   "trained": False, "version": "generic"},
    "yolo11m.pt":   {"name": "YOLOv11 Medium",                 "trained": False, "version": "generic"},
    "roboflow:piston-surface-defect-1-gjys9/2": {
                    "name": "Piston Surface Defect",           "trained": True,  "version": "v2"},
    "roboflow:piston-surface-defect-1-gjys9/3": {
                    "name": "Piston + LRT Wheel Defect",       "trained": True,  "version": "v3"},
    "roboflow:piston-surface-defect-1-gjys9/4": {
                    "name": "Piston + LRT + Collector Shoe",   "trained": True,  "version": "v4"},
    "roboflow:piston-surface-defect-1-gjys9/5": {
                    "name": "Workshop Collector Shoe v5",      "trained": True,  "version": "v5"},
    "roboflow:piston-surface-defect-1-gjys9/6": {
                    "name": "Workshop Collector Shoe v6",      "trained": True,  "version": "v6"},
    "roboflow:piston-surface-defect-1-gjys9/7": {
                    "name": "Workshop Collector Shoe v7",      "trained": True,  "version": "v7"},
    "roboflow:piston-surface-defect-1-gjys9/8": {
                    "name": "Workshop Collector Shoe v8",      "trained": True,  "version": "v8"},
    "roboflow:piston-surface-defect-1-gjys9/10": {
                    "name": "Workshop Collector Shoe v10",     "trained": True,  "version": "v10"},
    "roboflow:piston-surface-defect-1-gjys9/11": {
                    "name": "Workshop Collector Shoe v11",     "trained": True,  "version": "v11"},
    "roboflow:piston-surface-defect-1-gjys9/16": {
                    "name": "Workshop Collector Shoe v16",     "trained": True,  "version": "v16"},
    "lrt_model.pt": {"name": "LRT Custom Model",               "trained": True,  "version": "v1.0"},
}

# ── Confidence threshold ───────────────────────────────────────
CONFIDENCE_THRESHOLD        = 0.85  # default threshold for all defects
SCUFF_MARKS_THRESHOLD       = 0.50  # lower threshold for scuff marks — visually subtle defect

# ── Auto-Retrain Pipeline Settings ────────────────────────────
RETRAIN_THRESHOLD    = 30    # trigger retrain notification after this many new captures
ROBOFLOW_PROJECT     = "piston-surface-defect-1-gjys9"
ROBOFLOW_WORKSPACE   = "iman-irhash"


def increment_capture_count(supabase):
    """
    Increments the new capture count in retrain_tracker.
    Returns the updated count so caller can check if threshold is reached.
    """
    try:
        tracker = supabase.table("retrain_tracker").select("id, new_captures_count").limit(1).execute()
        if not tracker.data:
            return 0
        rec   = tracker.data[0]
        new_count = rec["new_captures_count"] + 1
        supabase.table("retrain_tracker").update({
            "new_captures_count": new_count
        }).eq("id", rec["id"]).execute()
        return new_count
    except Exception as e:
        print(f"  ⚠️  Could not update retrain tracker: {e}")
        return 0


def get_capture_count(supabase):
    """Returns current new capture count since last retrain."""
    try:
        tracker = supabase.table("retrain_tracker").select("new_captures_count").limit(1).execute()
        return tracker.data[0]["new_captures_count"] if tracker.data else 0
    except:
        return 0


def reset_capture_count(supabase, triggered_by, version_note=""):
    """
    Resets capture count after retrain is triggered.
    Logs the retrain event to retrain_history.
    Counter reset and history log are separate — counter always resets even if history fails.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    # Step 1: Reset counter (critical)
    try:
        tracker = supabase.table("retrain_tracker").select("id, new_captures_count").limit(1).execute()
        if tracker.data:
            rec = tracker.data[0]
            supabase.table("retrain_tracker").update({
                "new_captures_count":   0,
                "last_retrain_at":      now,
                "last_retrain_version": version_note,
                "last_reset_at":        now,
            }).eq("id", rec["id"]).execute()
            print(f"  ✅ Retrain counter reset to 0")

            # Step 2: Log to history (non-critical — don't fail if this errors)
            try:
                supabase.table("retrain_history").insert({
                    "triggered_by":     triggered_by,
                    "image_count":      rec["new_captures_count"],
                    "roboflow_version": version_note,
                    "status":           "triggered",
                    "notes":            f"Retrain triggered after {rec['new_captures_count']} new captures",
                }).execute()
                print(f"  ✅ Retrain history logged")
            except Exception as hist_err:
                print(f"  ⚠️  History log failed (non-critical): {hist_err}")
    except Exception as e:
        print(f"  ⚠️  Could not reset retrain tracker: {e}")


def trigger_roboflow_retrain(supabase, triggered_by):
    """
    Uploads new images to Roboflow via API and triggers retraining.
    Returns (success, message).
    """
    try:
        import requests
        # Trigger a new training version via Roboflow API
        url = f"https://api.roboflow.com/{ROBOFLOW_WORKSPACE}/{ROBOFLOW_PROJECT}/train"
        params = {"api_key": ROBOFLOW_API_KEY}
        resp = requests.post(url, params=params, timeout=30)
        if resp.status_code == 200:
            data    = resp.json()
            version = data.get("version", "unknown")
            reset_capture_count(supabase, triggered_by, f"v{version}")
            return True, f"Roboflow retraining triggered successfully — new version will be v{version}"
        else:
            return False, f"Roboflow API error: {resp.status_code} — {resp.text[:200]}"
    except Exception as e:
        return False, f"Could not trigger retraining: {e}"

# ── Defect class mapping ───────────────────────────────────────
DEFECT_MAP = {
    "wear":      ["scratch", "mark", "dent", "damage", "wear", "abrasion", "scuff"],
    "crack":     ["crack", "fracture", "break", "split"],
    "corrosion": ["rust", "stain", "discolor", "corrosion", "oxidation", "oxide"],
    "arcing":    ["burn", "arc", "char", "scorch", "blacken"],
}

# Roboflow class mapping — maps dataset class names to LRT defect categories
ROBOFLOW_CLASS_MAP = {
    "crack":           "crack",
    "pore":            "wear",
    "scratch":         "wear",
    "wear":            "wear",
    "scuff marks":     "scuff marks",  # keep as own defect type
    "oxidation":       "corrosion",
    "none":            "none",
    "water mark":      "none",
    "collector_shoe":  "none",
    "collector shoe":  "none",
}

_model_cache = {}  # cleared on every restart


def get_model_info():
    return MODEL_INFO.get(MODEL_PATH, {
        "name":    MODEL_PATH,
        "trained": False,
        "version": "unknown",
    })


def _is_roboflow_model():
    return MODEL_PATH.startswith("roboflow:")


def _get_roboflow_model_id():
    return MODEL_PATH.replace("roboflow:", "")


def load_model():
    global _model_cache

    # Only use cache if model loaded successfully previously
    if MODEL_PATH in _model_cache and _model_cache[MODEL_PATH] is not None:
        return _model_cache[MODEL_PATH]

    if _is_roboflow_model():
        try:
            from roboflow import Roboflow
            model_id = _get_roboflow_model_id()
            project, version = model_id.rsplit("/", 1)
            rf      = Roboflow(api_key=ROBOFLOW_API_KEY)
            model   = rf.workspace(ROBOFLOW_WORKSPACE).project(project).version(int(version)).model
            _model_cache[MODEL_PATH] = model
            log.info(f"Roboflow model ready: {model_id}")
            return model
        except ImportError:
            log.error("roboflow not installed — run: pip install roboflow")
            return None
        except Exception as e:
            log.error(f"Failed to initialise Roboflow model: {e}")
            return None
    else:
        try:
            from ultralytics import YOLO
            model = YOLO(MODEL_PATH)
            _model_cache[MODEL_PATH] = model
            log.info(f"Local model loaded: {MODEL_PATH}")
            return model
        except ImportError:
            log.error("ultralytics not installed — run: pip install ultralytics")
            return None
        except Exception as e:
            log.error(f"Failed to load model {MODEL_PATH}: {e}")
            return None


def detect_defects(image_path):
    """
    Runs defect detection on an image file.
    Automatically uses Roboflow API or local YOLO based on MODEL_PATH.
    """
    model = load_model()

    if model is None:
        return {
            "defect":       "unknown",
            "confidence":   0.0,
            "detections":   [],
            "annotated":    None,
            "needs_review": True,
            "model_path":   MODEL_PATH,
            "model_info":   get_model_info(),
            "error":        "Model not available",
        }

    if _is_roboflow_model():
        return _detect_roboflow(model, image_path)
    else:
        return _detect_local(model, image_path)


def _detect_roboflow(model, image_path):
    """Runs detection via Roboflow API using roboflow package."""
    try:
        import cv2

        prediction = model.predict(image_path, confidence=20, overlap=30)
        result     = prediction.json()

        predictions = result.get("predictions", [])
        detections  = []

        # ── Focus zone filter ───────────────────────────────────
        # Only keep detections whose centre falls within the focus
        # zone (20%-80% of image width). Detections in the darkened
        # left/right zones are discarded — they are suppressed visually
        # and should not influence the defect classification.
        image_width = int(result.get("image", {}).get("width", 0))
        if image_width > 0:
            focus_x_start = image_width * 0.30
            focus_x_end   = image_width * 0.70
        else:
            focus_x_start = None
            focus_x_end   = None

        filtered_predictions = []
        for pred in predictions:
            cx = pred.get("x", 0)  # Roboflow x = centre of box
            if focus_x_start is not None:
                if cx < focus_x_start or cx > focus_x_end:
                    log.info(f"Filtered out detection at x={cx:.0f} (outside focus zone {focus_x_start:.0f}–{focus_x_end:.0f})")
                    continue
            filtered_predictions.append(pred)

        for pred in filtered_predictions:
            label = pred.get("class", "unknown")
            conf  = pred.get("confidence", 0.0)
            detections.append({
                "label":      label,
                "confidence": conf,
                "x":          pred.get("x", 0),
                "y":          pred.get("y", 0),
                "width":      pred.get("width", 0),
                "height":     pred.get("height", 0),
            })

        detections.sort(key=lambda x: x["confidence"], reverse=True)
        defect, confidence = _classify_defect_roboflow(detections)
        threshold    = SCUFF_MARKS_THRESHOLD if defect == "scuff marks" else CONFIDENCE_THRESHOLD
        needs_review = confidence < threshold

        image     = cv2.imread(image_path)
        image_h, image_w = image.shape[:2] if image is not None else (0, 0)

        # ── Build annotated image with shoe bbox as white frame ─
        if image is not None:
            import numpy as np
            annotated = image.copy()

            # Get collector_shoe bbox
            shoe_bbox = get_shoe_bbox(filtered_predictions, image_w, image_h)

            if shoe_bbox:
                x1, y1, x2, y2 = shoe_bbox
                # Darken everything outside shoe bbox
                alpha = 0.70
                mask = np.zeros_like(annotated, dtype=np.uint8)
                mask[:, :]           = annotated
                mask[:y1, :]         = (annotated[:y1, :]         * (1 - alpha)).astype(np.uint8)
                mask[y2:, :]         = (annotated[y2:, :]         * (1 - alpha)).astype(np.uint8)
                mask[y1:y2, :x1]     = (annotated[y1:y2, :x1]    * (1 - alpha)).astype(np.uint8)
                mask[y1:y2, x2:]     = (annotated[y1:y2, x2:]    * (1 - alpha)).astype(np.uint8)
                annotated = mask
                # collector_shoe bbox serves as frame through darkening — no border needed
                log.info(f"Auto-frame applied — shoe bbox: ({x1},{y1}) to ({x2},{y2})")

            # Draw defect boxes (skip collector_shoe)
            defect_preds = [p for p in filtered_predictions
                           if p.get("class", "").lower() not in ("collector_shoe", "collector shoe")]
            annotated = _draw_roboflow_boxes(annotated, defect_preds)
            annotated_rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
        else:
            annotated_rgb = None

        if needs_review and confidence > 0:
            log.warning(f"Low confidence ({confidence:.0%}) — flagged for review")

        return {
            "defect":       defect,
            "confidence":   confidence,
            "detections":   detections,
            "annotated":    annotated_rgb,
            "needs_review": needs_review,
            "model_path":   MODEL_PATH,
            "model_info":   get_model_info(),
            "error":        None,
        }

    except Exception as e:
        log.error(f"Roboflow detection failed: {e}")
        return {
            "defect":       "unknown",
            "confidence":   0.0,
            "detections":   [],
            "annotated":    None,
            "needs_review": True,
            "model_path":   MODEL_PATH,
            "model_info":   get_model_info(),
            "error":        str(e),
        }


def _draw_roboflow_boxes(image, predictions):
    """Draws bounding boxes from Roboflow predictions onto the image."""
    import cv2

    COLORS = {
        "crack":   (0,   0,   255),   # red
        "wear":    (0,  165,  255),   # orange
        "scratch": (0,  165,  255),   # orange
        "pore":    (0,  255,  255),   # yellow
        "default": (128, 0,  128),    # purple
    }

    for pred in predictions:
        label  = pred.get("class", "")
        conf   = pred.get("confidence", 0)
        x, y   = int(pred.get("x", 0)), int(pred.get("y", 0))
        w, h   = int(pred.get("width", 0)), int(pred.get("height", 0))
        x1, y1 = x - w // 2, y - h // 2
        x2, y2 = x + w // 2, y + h // 2

        color = COLORS.get(label, COLORS["default"])
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            image, f"{label} {conf:.2f}",
            (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX,
            0.5, color, 2,
        )

    return image


def get_shoe_bbox(predictions, image_width, image_height):
    """
    Extracts the collector_shoe bounding box from v11 predictions.
    Returns (x1, y1, x2, y2) pixel coordinates with 5% padding,
    or None if no collector_shoe detection found.
    Used for auto-cropping the frame to the shoe surface.
    """
    shoe_preds = [
        p for p in predictions
        if p.get("class", "").lower() in ("collector_shoe", "collector shoe")
    ]
    if not shoe_preds:
        return None

    best = max(shoe_preds, key=lambda p: p.get("confidence", 0))
    cx, cy = best["x"], best["y"]
    bw, bh = best["width"], best["height"]

    pad_x = int(image_width  * 0.02)
    pad_y = int(image_height * 0.02)

    x1 = max(0, int(cx - bw / 2) - pad_x)
    y1 = max(0, int(cy - bh / 2) - pad_y)
    x2 = min(image_width,  int(cx + bw / 2) + pad_x)
    y2 = min(image_height, int(cy + bh / 2) + pad_y)

    return (x1, y1, x2, y2)


def _classify_defect_roboflow(detections):
    """
    Maps Roboflow class names to LRT defect categories.
    Skips collector_shoe class — used for auto-crop only, not a defect.
    """
    if not detections:
        return "none", 0.0

    # Filter out collector_shoe — it's a locator class, not a defect
    defect_detections = [
        d for d in detections
        if d["label"].lower() not in ("collector_shoe", "collector shoe")
    ]

    if not defect_detections:
        return "none", 0.0

    best  = defect_detections[0]
    label = best["label"].lower()
    conf  = best["confidence"]

    # Direct mapping from Roboflow piston dataset classes
    lrt_defect = ROBOFLOW_CLASS_MAP.get(label)
    if lrt_defect:
        return lrt_defect, round(conf, 3)

    # Fallback keyword matching
    for defect, keywords in DEFECT_MAP.items():
        if any(kw in label for kw in keywords):
            return defect, round(conf, 3)

    return "none", round(conf, 3)


def _detect_local(model, image_path):
    """Runs detection using a local YOLO model."""
    try:
        import numpy as np
        from PIL import Image
        import cv2

        image     = Image.open(image_path).convert("RGB")
        img_array = np.array(image)
        results   = model(img_array, verbose=False)
        result    = results[0]

        detections = []
        for box in result.boxes:
            label = model.names[int(box.cls)]
            conf  = float(box.conf)
            detections.append({"label": label, "confidence": conf})

        detections.sort(key=lambda x: x["confidence"], reverse=True)
        defect, confidence = _classify_defect_local(detections)
        threshold    = SCUFF_MARKS_THRESHOLD if defect == "scuff marks" else CONFIDENCE_THRESHOLD
        needs_review = confidence < threshold

        if needs_review and confidence > 0:
            log.warning(f"Low confidence ({confidence:.0%}) — flagged for review")

        annotated     = result.plot()
        annotated_rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)

        return {
            "defect":       defect,
            "confidence":   confidence,
            "detections":   detections,
            "annotated":    annotated_rgb,
            "needs_review": needs_review,
            "model_path":   MODEL_PATH,
            "model_info":   get_model_info(),
            "error":        None,
        }

    except Exception as e:
        log.error(f"Local detection failed: {e}")
        return {
            "defect":       "unknown",
            "confidence":   0.0,
            "detections":   [],
            "annotated":    None,
            "needs_review": True,
            "model_path":   MODEL_PATH,
            "model_info":   get_model_info(),
            "error":        str(e),
        }


def _classify_defect_local(detections):
    """Maps local YOLO COCO labels to LRT defect categories."""
    import random

    if not detections:
        return "none", 0.0

    best  = detections[0]
    label = best["label"].lower()
    conf  = best["confidence"]

    for defect, keywords in DEFECT_MAP.items():
        if any(kw in label for kw in keywords):
            return defect, round(conf, 3)

    info = get_model_info()
    if not info.get("trained", False):
        if conf > 0.7:
            return random.choice(["wear", "corrosion"]), round(conf, 3)
        elif conf > 0.4:
            return "wear", round(conf, 3)
        else:
            return "none", round(conf, 3)

    return "none", round(conf, 3)


def _classify_defect(detections):
    """Unified classifier — routes to correct method based on model type."""
    if _is_roboflow_model():
        return _classify_defect_roboflow(detections)
    return _classify_defect_local(detections)


def get_status_color(level):
    if level >= CONFIDENCE_THRESHOLD:
        return "#0A8A72"
    elif level >= 0.5:
        return "#E8920A"
    else:
        return "#C9382A"


def get_status_label(needs_review, defect, confidence):
    if defect == "none" or confidence == 0.0:
        return "No defect detected"
    if needs_review:
        return f"⚠️ {defect} detected — LOW CONFIDENCE ({confidence:.0%}) — needs human review"
    return f"✅ {defect} detected ({confidence:.0%} confidence)"
