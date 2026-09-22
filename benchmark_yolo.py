# benchmark_yolo.py
# ── YOLO Model Benchmark — YOLOv8m vs YOLOv11m vs Roboflow v7 ─
# Run with: python benchmark_yolo.py --folder dji_wired_test_results
#           python benchmark_yolo.py --folder collector_shoe_test
#           python benchmark_yolo.py --folder dji_wired_test_results --roboflow-only
# ─────────────────────────────────────────────────────────────

import argparse
import os
import time
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime

# ── Colour helpers ────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):     print(f"  {GREEN}✓{RESET}  {msg}")
def fail(msg):   print(f"  {RED}✗{RESET}  {msg}")
def info(msg):   print(f"  {BLUE}ℹ{RESET}  {msg}")
def header(msg): print(f"\n{BOLD}{YELLOW}{msg}{RESET}")

# ── Roboflow settings ─────────────────────────────────────────
ROBOFLOW_API_KEY = "f2JiQ0Vkd0JRIDZ8UP5a"
ROBOFLOW_PROJECT = "piston-surface-defect-1-gjys9"
ROBOFLOW_VERSION = 22

# ── Local models ──────────────────────────────────────────────
MODELS = {
    "YOLOv8m":  "yolov8m.pt",
    "YOLOv11m": "yolo11m.pt",
}

# ── Defect mapping ────────────────────────────────────────────
DEFECT_MAP = {
    "crack":     ["crack", "fracture", "break", "split"],
    "wear":      ["scratch", "mark", "dent", "damage", "wear", "scuff", "pore"],
    "corrosion": ["rust", "stain", "discolor", "oxidation"],
}

ROBOFLOW_CLASS_MAP = {
    "crack": "crack", "pore": "wear", "scratch": "wear",
    "wear": "wear", "scuff marks": "wear",
    "oxidation": "corrosion", "none": "none", "water mark": "none",
}

def classify_defect(detections):
    if not detections:
        return "none", 0.0
    best  = max(detections, key=lambda x: x["confidence"])
    label = best["label"].lower()
    conf  = best["confidence"]
    for defect, keywords in DEFECT_MAP.items():
        if any(kw in label for kw in keywords):
            return defect, round(conf, 3)
    if conf > 0.7:
        return "other", round(conf, 3)
    return "none", round(conf, 3)


def run_roboflow_benchmark(image_paths, output_dir):
    """Runs Roboflow v7 on all images — same output format as run_benchmark."""
    try:
        from roboflow import Roboflow
        rf    = Roboflow(api_key=ROBOFLOW_API_KEY)
        model = rf.workspace().project(ROBOFLOW_PROJECT).version(ROBOFLOW_VERSION).model
        ok(f"Roboflow v{ROBOFLOW_VERSION} model loaded")
    except Exception as e:
        fail(f"Could not load Roboflow model: {e}")
        return []

    model_out_dir = os.path.join(output_dir, f"Roboflow_v{ROBOFLOW_VERSION}")
    os.makedirs(model_out_dir, exist_ok=True)

    results = []
    header(f"Running Roboflow v{ROBOFLOW_VERSION} on {len(image_paths)} image(s)")

    for img_path in image_paths:
        img_name = Path(img_path).name
        try:
            t_start    = time.perf_counter()
            prediction = model.predict(str(img_path), confidence=20, overlap=30)
            t_end      = time.perf_counter()
            inf_ms     = round((t_end - t_start) * 1000, 1)

            preds = prediction.json().get("predictions", [])
            detections = [{
                "label":      p.get("class", "unknown"),
                "confidence": p.get("confidence", 0.0),
            } for p in preds]
            detections.sort(key=lambda x: x["confidence"], reverse=True)

            # Skip collector_shoe — it's a locator class, not a defect
            SKIP_CLASSES = ("collector_shoe", "collector shoe")
            defect_detections = [d for d in detections if d["label"].lower() not in SKIP_CLASSES]

            top_label  = defect_detections[0]["label"].lower() if defect_detections else "none"
            top_conf   = defect_detections[0]["confidence"] if defect_detections else 0.0
            lrt_defect = ROBOFLOW_CLASS_MAP.get(top_label, "other")
            all_confs  = [d["confidence"] for d in defect_detections]
            avg_conf   = round(sum(all_confs) / len(all_confs), 3) if all_confs else 0.0

            try:
                prediction.save(os.path.join(model_out_dir, f"annotated_{img_name}"))
            except:
                pass

            results.append({
                "image":        img_name,
                "inference_ms": inf_ms,
                "detections":   len(detections),
                "top_label":    top_label,
                "top_conf":     top_conf,
                "avg_conf":     avg_conf,
                "defect":       lrt_defect,
            })

            conf_color = GREEN if top_conf >= 0.75 else (YELLOW if top_conf >= 0.5 else RED)
            print(
                f"  {img_name:<35} "
                f"{inf_ms:>6}ms  "
                f"{len(detections):>3} det  "
                f"top: {conf_color}{top_conf:.0%}{RESET}  "
                f"[{lrt_defect}]"
            )

        except Exception as e:
            fail(f"{img_name}: {e}")

    return results


def run_benchmark(image_paths, output_dir):
    from ultralytics import YOLO

    results_summary = {}

    for model_name, model_file in MODELS.items():
        header(f"Loading {model_name} ({model_file})")
        try:
            model = YOLO(model_file)
            ok(f"{model_name} loaded")
        except Exception as e:
            fail(f"Could not load {model_name}: {e}")
            continue

        info("Running warmup pass...")
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        model(dummy, verbose=False)
        ok("Warmup complete")

        model_results = []
        model_out_dir = os.path.join(output_dir, model_name)
        os.makedirs(model_out_dir, exist_ok=True)

        header(f"Running {model_name} on {len(image_paths)} image(s)")

        for img_path in image_paths:
            img_name = Path(img_path).name
            image    = cv2.imread(str(img_path))

            if image is None:
                fail(f"Could not read: {img_path}")
                continue

            t_start  = time.perf_counter()
            yolo_out = model(image, verbose=False)
            t_end    = time.perf_counter()
            inf_ms   = round((t_end - t_start) * 1000, 1)

            result = yolo_out[0]
            detections = []
            for box in result.boxes:
                label = model.names[int(box.cls)]
                conf  = float(box.conf)
                detections.append({"label": label, "confidence": conf})

            detections.sort(key=lambda x: x["confidence"], reverse=True)
            defect, top_conf = classify_defect(detections)
            all_confs = [d["confidence"] for d in detections]
            avg_conf  = round(sum(all_confs) / len(all_confs), 3) if all_confs else 0.0

            annotated    = result.plot()
            out_filename = os.path.join(model_out_dir, f"annotated_{img_name}")
            cv2.imwrite(out_filename, annotated)

            model_results.append({
                "image":        img_name,
                "inference_ms": inf_ms,
                "detections":   len(detections),
                "top_label":    detections[0]["label"] if detections else "none",
                "top_conf":     top_conf,
                "avg_conf":     avg_conf,
                "defect":       defect,
            })

            conf_color = GREEN if top_conf >= 0.75 else (YELLOW if top_conf >= 0.5 else RED)
            print(
                f"  {img_name:<35} "
                f"{inf_ms:>6}ms  "
                f"{len(detections):>3} det  "
                f"top: {conf_color}{top_conf:.0%}{RESET}  "
                f"[{defect}]"
            )

        results_summary[model_name] = model_results

    return results_summary


def print_summary(results_summary):
    header("BENCHMARK RESULTS — SUMMARY")
    print(f"\n{'─'*70}")

    for model_name, results in results_summary.items():
        if not results:
            continue
        avg_ms    = round(sum(r["inference_ms"] for r in results) / len(results), 1)
        avg_conf  = round(sum(r["top_conf"]     for r in results) / len(results) * 100, 1)
        avg_det   = round(sum(r["detections"]   for r in results) / len(results), 1)
        high_conf = sum(1 for r in results if r["top_conf"] >= 0.75)
        low_conf  = sum(1 for r in results if r["top_conf"] <  0.50)

        color = GREEN if avg_conf >= 75 else (YELLOW if avg_conf >= 50 else RED)
        print(f"\n  {BOLD}{model_name}{RESET}")
        print(f"  {'Avg inference time':<28} {avg_ms} ms")
        print(f"  {'Avg top confidence':<28} {color}{avg_conf}%{RESET}")
        print(f"  {'Avg detections per image':<28} {avg_det}")
        print(f"  {'High confidence (>=75%)':<28} {high_conf}/{len(results)} images")
        print(f"  {'Low confidence (<50%)':<28} {low_conf}/{len(results)} images")

    print(f"\n{'─'*70}\n")


def main():
    parser = argparse.ArgumentParser(description="Benchmark YOLO models on collector shoe images")
    parser.add_argument("--folder", default="dji_wired_test_results",
                        help="Folder containing images (default: dji_wired_test_results)")
    parser.add_argument("--roboflow-only", action="store_true",
                        help="Only run Roboflow v7 (skip local YOLOv8m/v11m)")
    args = parser.parse_args()

    print("=" * 60)
    print(f"  YOLO Benchmark — Roboflow v{ROBOFLOW_VERSION} + Local Models")
    print("=" * 60)

    # Support comma-separated folders
    folders = [f.strip() for f in args.folder.split(",")]
    image_paths = []
    for folder_str in folders:
        folder = Path(folder_str)
        if not folder.exists():
            fail(f"Folder not found: {folder}")
            continue
        imgs = (list(folder.glob("*.jpg")) + list(folder.glob("*.jpeg")) +
                list(folder.glob("*.png")) + list(folder.glob("*.bmp")) +
                list(folder.glob("*.webp")))
        image_paths.extend(imgs)
        ok(f"Found {len(imgs)} image(s) in {folder}/")

    if not image_paths:
        fail("No images found. Check folder paths.")
        return

    info(f"Total images to benchmark: {len(image_paths)}")
    output_dir = "benchmark_output"
    os.makedirs(output_dir, exist_ok=True)

    all_results = {}

    # ── Roboflow v7 ───────────────────────────────────────────
    rf_results = run_roboflow_benchmark(image_paths, output_dir)
    if rf_results:
        all_results[f"Roboflow v{ROBOFLOW_VERSION}"] = rf_results

    # ── Local models (optional) ───────────────────────────────
    if not args.roboflow_only:
        local_results = run_benchmark(image_paths, output_dir)
        all_results.update(local_results)

    # ── Print summary ─────────────────────────────────────────
    print_summary(all_results)

    # ── Save CSV ──────────────────────────────────────────────
    import csv
    csv_path = os.path.join(output_dir, f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["model", "image", "inference_ms", "detections",
                         "top_label", "top_conf", "avg_conf", "defect"])
        for model_name, res_list in all_results.items():
            for r in res_list:
                writer.writerow([model_name, r["image"], r["inference_ms"],
                                 r["detections"], r["top_label"],
                                 r["top_conf"], r["avg_conf"], r["defect"]])
    ok(f"CSV saved: {csv_path}")


if __name__ == "__main__":
    main()
