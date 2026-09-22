# test_contrast_sharpen.py
# Applies different contrast and sharpening variations to a folder of images
# for benchmark comparison against the original.
#
# Run: python test_contrast_sharpen.py --folder "glare-reflection LRV photos"
#
# Creates 4 output folders:
#   _sharpen2    — higher sharpening (strength 2.0)
#   _clahe       — contrast enhanced using CLAHE
#   _clahe_sharp — contrast + sharpening combined
#   _natural     — no sharpening, no enhancement (natural)

import cv2
import numpy as np
import os
import argparse


def sharpen(image, strength=1.0):
    """Apply unsharp mask sharpening."""
    blurred = cv2.GaussianBlur(image, (0, 0), 3)
    return cv2.addWeighted(image, 1 + strength, blurred, -strength, 0)


def apply_clahe(image):
    """
    Apply CLAHE (Contrast Limited Adaptive Histogram Equalization).
    Works per channel in LAB colour space — enhances local contrast
    without over-amplifying noise. Effective for reducing glare impact.
    """
    lab   = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_eq  = clahe.apply(l)
    lab_eq = cv2.merge([l_eq, a, b])
    return cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)


def process_folder(source_folder, suffix, process_fn):
    output_folder = source_folder.rstrip("/\\") + suffix
    os.makedirs(output_folder, exist_ok=True)

    exts   = (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG")
    images = [f for f in os.listdir(source_folder) if f.endswith(exts)]

    print(f"\nProcessing → {output_folder}")
    for fname in images:
        src = os.path.join(source_folder, fname)
        dst = os.path.join(output_folder, fname)
        img = cv2.imread(src)
        if img is None:
            print(f"  ⚠️  Could not read {fname}")
            continue
        result = process_fn(img)
        cv2.imwrite(dst, result)
        print(f"  ✅ {fname}")

    return output_folder


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True, help="Source folder of images")
    args = parser.parse_args()

    src = args.folder

    if not os.path.exists(src):
        print(f"❌ Folder not found: {src}")
        exit()

    # Variation 1 — Natural (no enhancement)
    f1 = process_folder(src, "_natural",     lambda img: img)

    # Variation 2 — Higher sharpening (strength 2.0)
    f2 = process_folder(src, "_sharpen2",    lambda img: sharpen(img, strength=2.0))

    # Variation 3 — CLAHE contrast enhancement
    f3 = process_folder(src, "_clahe",       apply_clahe)

    # Variation 4 — CLAHE + sharpening combined
    f4 = process_folder(src, "_clahe_sharp", lambda img: sharpen(apply_clahe(img), strength=1.0))

    print(f"\n✅ Done! Now run benchmark on all folders:")
    print(f'  python benchmark_yolo.py --folder "{src}" --roboflow-only')
    print(f'  python benchmark_yolo.py --folder "{f1}" --roboflow-only')
    print(f'  python benchmark_yolo.py --folder "{f2}" --roboflow-only')
    print(f'  python benchmark_yolo.py --folder "{f3}" --roboflow-only')
    print(f'  python benchmark_yolo.py --folder "{f4}" --roboflow-only')
