# test_sharpen_compare.py
# Compares greyscale + CLAHE + sharpen at strength 1.2 vs 1.5
# Run: python test_sharpen_compare.py --folder "glare-reflection LRV photos"

import cv2
import numpy as np
import os
import argparse


def apply_grey_clahe_sharp(image, strength=1.2):
    """Greyscale + CLAHE + Sharpen pipeline."""
    grey      = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe     = cv2.createCLAHE(clipLimit=0.5, tileGridSize=(8, 8))
    grey_eq   = clahe.apply(grey)
    blurred   = cv2.GaussianBlur(grey_eq, (0, 0), 3)
    sharpened = cv2.addWeighted(grey_eq, 1 + strength, blurred, -strength, 0)
    return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)


def process_folder(source_folder, suffix, strength):
    output_folder = source_folder.rstrip("/\\") + suffix
    os.makedirs(output_folder, exist_ok=True)

    exts   = (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG")
    images = [f for f in os.listdir(source_folder) if f.endswith(exts)]

    print(f"\nProcessing → {output_folder} (sharpen strength={strength})")
    for fname in images:
        src = os.path.join(source_folder, fname)
        dst = os.path.join(output_folder, fname)
        img = cv2.imread(src)
        if img is None:
            print(f"  ⚠️  Could not read {fname}")
            continue
        result = apply_grey_clahe_sharp(img, strength=strength)
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

    f1 = process_folder(src, "_grey_clahe_sharp_1.2", strength=1.2)
    f2 = process_folder(src, "_grey_clahe_sharp_1.5", strength=1.5)

    print(f"\n✅ Done! Now run benchmark on both:")
    print(f'  python benchmark_yolo.py --folder "{f1}" --roboflow-only')
    print(f'  python benchmark_yolo.py --folder "{f2}" --roboflow-only')
