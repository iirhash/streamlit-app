# test_reconnect.py
# Tests Option B — reconnect approach to reduce lag
# Run with: python test_reconnect.py
#
# Compare this against the flush approach to see which gives
# a more current frame when the preview window opens.

import cv2
import time

RTMP_URL = "rtmp://10.230.92.63:1936/live/stream"

def open_stream():
    cap = cv2.VideoCapture(RTMP_URL, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FPS, 30)
    return cap

print("Connecting to stream...")
cap = open_stream()

if not cap.isOpened():
    print("❌ Could not connect to stream. Make sure rtmp_server_test.js is running and Mimo is streaming.")
    exit()

print("✅ Connected. Reading a few frames to warm up...")
for _ in range(5):
    cap.read()
    time.sleep(0.1)

# ── Option B: Close and reopen for freshest frame ──────────────
print("Reconnecting for freshest frame...")
cap.release()
time.sleep(0.3)
cap = open_stream()

# Read one frame immediately after reconnect
ret, frame = cap.read()
if ret:
    cv2.imshow("Reconnect Test — Is this the current frame? (any key to close)", frame)
    print("✅ Frame shown — check if this is the CURRENT camera view")
    cv2.waitKey(5000)
else:
    print("❌ Could not read frame after reconnect")

cap.release()
cv2.destroyAllWindows()
print("Done.")
