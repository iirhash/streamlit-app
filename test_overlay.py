# test_overlay.py
# Use arrow keys to adjust overlay zones
# UP/DOWN = adjust selected zone, TAB = switch zone, S = save, Q = quit

import cv2
import numpy as np

DJI_INDEX = 1

params = {"left": 20, "right": 20, "top": 0, "bottom": 0}
zones  = ["left", "right", "top", "bottom"]
sel    = 0

def apply_overlay(frame, p, alpha=0.70):
    h, w = frame.shape[:2]
    x1 = int(w * p["left"]   / 100)
    x2 = int(w * (1 - p["right"]  / 100))
    y1 = int(h * p["top"]    / 100)
    y2 = int(h * (1 - p["bottom"] / 100))
    o  = frame.copy()
    o[:, :x1]          = (frame[:, :x1]          * (1-alpha)).astype(np.uint8)
    o[:, x2:]          = (frame[:, x2:]           * (1-alpha)).astype(np.uint8)
    o[:y1, x1:x2]      = (frame[:y1, x1:x2]       * (1-alpha)).astype(np.uint8)
    o[y2:, x1:x2]      = (frame[y2:, x1:x2]       * (1-alpha)).astype(np.uint8)
    cv2.rectangle(o, (x1, y1), (x2, y2), (255,255,255), 2)
    return o, x1, x2, y1, y2

cap = cv2.VideoCapture(DJI_INDEX, cv2.CAP_DSHOW)
if not cap.isOpened():
    print("Camera not found — try changing DJI_INDEX")
    exit()

print("Controls: UP/DOWN arrow = adjust | TAB = switch zone | S = save | Q = quit")
print(f"Active zone: {zones[sel].upper()}")

while True:
    ret, frame = cap.read()
    if not ret:
        continue

    preview, x1, x2, y1, y2 = apply_overlay(frame, params)
    h, w = frame.shape[:2]

    # Info overlay
    for i, z in enumerate(zones):
        color = (0,255,255) if i == sel else (200,200,200)
        cv2.putText(preview, f"{'>' if i==sel else ' '} {z.upper()}: {params[z]}%",
                    (10, 30+i*28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
    cv2.putText(preview, "TAB=switch  UP/DOWN=adjust  S=save  Q=quit",
                (10, h-15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)

    cv2.imshow("Overlay Tuner", preview)
    key = cv2.waitKey(30) & 0xFF

    if key == ord('q'):
        break
    elif key == ord('\t'):  # TAB
        sel = (sel + 1) % len(zones)
        print(f"Active zone: {zones[sel].upper()}")
    elif key == 82 or key == ord('w'):  # UP arrow or W — increase
        params[zones[sel]] = min(49, params[zones[sel]] + 1)
    elif key == 84 or key == ord('x'):  # DOWN arrow or X — decrease
        params[zones[sel]] = max(0, params[zones[sel]] - 1)
    elif key == ord('s'):  # Save
        print(f"\nSettings: {params}")
        print(f"x_start = int(w * {params['left']/100})")
        print(f"x_end   = int(w * {1-params['right']/100})")
        print(f"y_start = int(h * {params['top']/100})")
        print(f"y_end   = int(h * {1-params['bottom']/100})")

cap.release()
cv2.destroyAllWindows()
