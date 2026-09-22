# white_balance_fix.py
# ── Automatic White Balance Correction ────────────────────────
# Drop-in function to fix yellowish/color-cast tinge from
# compressed RTMP wireless streams.
#
# Two methods included:
#   1. gray_world_balance()  - fast, good for mild tinge
#   2. simplest_color_balance() - stronger correction, slightly slower
#
# Import and use either one on each frame before display/saving.
# ─────────────────────────────────────────────────────────────

import cv2
import numpy as np


def gray_world_balance(frame):
    """
    Gray World assumption: average colour in a normal scene
    should be neutral gray. Rescales each channel so their
    averages match, removing colour casts like a yellow tinge.

    Fast — safe to run on every frame in real time.
    """
    result = frame.astype(np.float32)

    avg_b = np.mean(result[:, :, 0])
    avg_g = np.mean(result[:, :, 1])
    avg_r = np.mean(result[:, :, 2])

    avg_gray = (avg_b + avg_g + avg_r) / 3

    # Avoid divide-by-zero on solid black frames
    result[:, :, 0] *= (avg_gray / max(avg_b, 1))
    result[:, :, 1] *= (avg_gray / max(avg_g, 1))
    result[:, :, 2] *= (avg_gray / max(avg_r, 1))

    return np.clip(result, 0, 255).astype(np.uint8)


def simplest_color_balance(frame, percent=1):
    """
    Stretches each channel's histogram, clipping the extreme
    top/bottom percentile of pixel values. Gives a stronger,
    more accurate correction than gray world, but is slightly
    heavier computationally — still fine for live video.
    """
    result = frame.copy()
    channels = cv2.split(result)
    out_channels = []

    half_percent = percent / 200.0

    for channel in channels:
        flat = channel.flatten()
        flat = np.sort(flat)
        n = len(flat)

        low_val  = flat[int(n * half_percent)]
        high_val = flat[int(n * (1 - half_percent)) - 1]

        # Stretch the channel between low_val and high_val
        channel = np.clip(channel, low_val, high_val)
        channel = ((channel - low_val) / max(high_val - low_val, 1) * 255)
        out_channels.append(channel.astype(np.uint8))

    return cv2.merge(out_channels)


if __name__ == "__main__":
    # Quick standalone test: load a saved test image and compare
    import sys
    import os

    if len(sys.argv) < 2:
        print("Usage: python white_balance_fix.py <path_to_image.jpg>")
        sys.exit(0)

    img_path = sys.argv[1]
    if not os.path.exists(img_path):
        print(f"File not found: {img_path}")
        sys.exit(1)

    frame = cv2.imread(img_path)

    gray_world_result = gray_world_balance(frame)
    simplest_result    = simplest_color_balance(frame)

    base = os.path.splitext(img_path)[0]
    cv2.imwrite(f"{base}_gray_world.jpg", gray_world_result)
    cv2.imwrite(f"{base}_simplest_balance.jpg", simplest_result)

    print(f"✅ Saved corrected versions:")
    print(f"   {base}_gray_world.jpg")
    print(f"   {base}_simplest_balance.jpg")
    print(f"\nCompare them side-by-side with the original to see which looks better.")
