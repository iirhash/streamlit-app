# test_sharpen.py
# Tests different levels of sharpening on an existing image
# Run with: python test_sharpen.py
#
# Saves 4 versions of the image side by side:
#   Original | Light sharpen | Medium sharpen | Strong sharpen
# So you can visually compare and pick the best level

import cv2
import numpy as np
import os
import glob

def sharpen(image, strength=1.0):
    """
    Unsharp mask sharpening.
    strength: 0.5 = light, 1.0 = medium, 2.0 = strong
    """
    blurred   = cv2.GaussianBlur(image, (0, 0), 3)
    sharpened = cv2.addWeighted(image, 1 + strength, blurred, -strength, 0)
    return sharpened

def main():
    # Find an image to test on
    search_paths = [
        "collector_shoe_test/*.jpg",
        "collector_shoe_test/*.png",
        "dji_wired_test_results/*.jpg",
        "camera_station_temp/*.jpg",
    ]

    image_path = None
    for pattern in search_paths:
        matches = glob.glob(pattern)
        if matches:
            image_path = matches[0]
            break

    if not image_path:
        print("❌ No test image found.")
        print("   Place an image in collector_shoe_test/ or dji_wired_test_results/")
        return

    print(f"  Testing on: {image_path}")

    image = cv2.imread(image_path)
    if image is None:
        print(f"❌ Could not read: {image_path}")
        return

    # Generate 4 versions
    original = image.copy()
    light    = sharpen(image, 0.5)
    medium   = sharpen(image, 1.0)
    strong   = sharpen(image, 2.0)

    # Add labels to each
    def label(img, text):
        out = img.copy()
        cv2.rectangle(out, (0, 0), (300, 40), (30, 30, 30), -1)
        cv2.putText(out, text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        return out

    original = label(original, "Original")
    light    = label(light,    "Light (0.5)")
    medium   = label(medium,   "Medium (1.0)")
    strong   = label(strong,   "Strong (2.0)")

    # Resize all to same height for side-by-side
    h = 600
    def resize_h(img):
        ratio = h / img.shape[0]
        return cv2.resize(img, (int(img.shape[1]*ratio), h))

    row = np.hstack([
        resize_h(original),
        resize_h(light),
        resize_h(medium),
        resize_h(strong),
    ])

    # Save output
    os.makedirs("sharpen_test", exist_ok=True)
    out_path = "sharpen_test/sharpen_comparison.jpg"
    cv2.imwrite(out_path, row)
    print(f"✅ Comparison saved: {out_path}")
    print(f"   Open this file to compare all 4 versions side by side")
    print(f"   Original | Light (0.5) | Medium (1.0) | Strong (2.0)")

    # Also save individual files
    cv2.imwrite("sharpen_test/original.jpg", image)
    cv2.imwrite("sharpen_test/light_sharpen.jpg",  sharpen(image, 0.5))
    cv2.imwrite("sharpen_test/medium_sharpen.jpg", sharpen(image, 1.0))
    cv2.imwrite("sharpen_test/strong_sharpen.jpg", sharpen(image, 2.0))
    print(f"   Individual files also saved in sharpen_test/")

if __name__ == "__main__":
    main()
