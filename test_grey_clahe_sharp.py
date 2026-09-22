# test_grey_clahe_sharp.py
# Converts images to greyscale + CLAHE + sharpen combination
# Run: python test_grey_clahe_sharp.py --folder "glare-reflection LRV photos"

import cv2
import numpy as np
import os
import argparse


def sharpen(image, strength=1.0):
    blurred = cv2.GaussianBlur(image, (0, 0), 3)
    return cv2.addWeighted(image, 1 + strength, blurred, -strength, 0)


def apply_clahe_grey(image):
    """
    Convert to greyscale, apply CLAHE, sharpen.
    Returns 3-channel BGR image (grey values in all 3 channels)
    so YOLO still gets the expected input format.
    """
    # Convert to greyscale
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Apply CLAHE on greyscale
    clahe  = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    grey_eq = clahe.apply(grey)

    # Sharpen
    blurred  = cv2.GaussianBlur(grey_eq, (0, 0), 3)
    sharpened = cv2.addWeighted(grey_eq, 2.0, blurred, -1.0, 0)

    # Convert back to BGR for YOLO
    return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)


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

    f1 = process_folder(src, "_grey_clahe_sharp", apply_clahe_grey)

    print(f"\n✅ Done! Now run benchmark:")
    print(f'  python benchmark_yolo.py --folder "{f1}" --roboflow-only')
