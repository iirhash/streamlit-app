# test_greyscale.py
# Converts a folder of colour images to greyscale for benchmark comparison
# Run: python test_greyscale.py --folder "Photo Batch [LRV15] (180826)"
#
# This creates a new folder with "_greyscale" suffix containing
# greyscale versions of all images in the source folder.
# Then run benchmark_yolo.py on both folders to compare.

import cv2
import os
import argparse

def convert_to_greyscale(source_folder, output_folder=None):
    if not os.path.exists(source_folder):
        print(f"❌ Folder not found: {source_folder}")
        return

    if output_folder is None:
        output_folder = source_folder.rstrip("/\\") + "_greyscale"

    os.makedirs(output_folder, exist_ok=True)

    exts   = (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG")
    images = [f for f in os.listdir(source_folder) if f.endswith(exts)]

    if not images:
        print(f"❌ No images found in: {source_folder}")
        return

    print(f"Converting {len(images)} image(s) to greyscale...")
    print(f"  Source:  {source_folder}")
    print(f"  Output:  {output_folder}")
    print()

    for fname in images:
        src_path = os.path.join(source_folder, fname)
        dst_path = os.path.join(output_folder, fname)

        img  = cv2.imread(src_path)
        if img is None:
            print(f"  ⚠️  Could not read {fname} — skipping")
            continue

        # Convert to greyscale then back to BGR so YOLO still gets 3 channels
        grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        grey_bgr = cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR)
        cv2.imwrite(dst_path, grey_bgr)
        print(f"  ✅ {fname}")

    print(f"\nDone! Greyscale images saved to: {output_folder}")
    print(f"\nNow run benchmark on both folders:")
    print(f'  python benchmark_yolo.py --folder "{source_folder}" --roboflow-only')
    print(f'  python benchmark_yolo.py --folder "{output_folder}" --roboflow-only')

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True, help="Source folder of colour images")
    parser.add_argument("--output", default=None, help="Output folder (default: source_greyscale)")
    args = parser.parse_args()
    convert_to_greyscale(args.folder, args.output)
