# find_camera.py
# Scans camera indices 0-5 to find the DJI camera
# Run: python find_camera.py

import cv2

print("Scanning for available cameras...")
found = []
for i in range(6):
    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            h, w = frame.shape[:2]
            print(f"  ✅ Camera found at index {i} — resolution {w}x{h}")
            found.append(i)
        else:
            print(f"  ⚠️  Index {i} opened but no frame")
        cap.release()
    else:
        print(f"  ❌ Index {i} — not available")

if found:
    print(f"\nUse DJI_INDEX = {found[-1]} in test_overlay.py")
else:
    print("\n❌ No cameras found. Make sure DJI is plugged in and no other app is using it.")
