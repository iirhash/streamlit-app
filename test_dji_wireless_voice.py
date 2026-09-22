# test_dji_wireless_voice.py
# ── DJI Action 3 Wireless Stream + Voice Trigger ──────────────
# Run with: python test_dji_wireless_voice.py
#
# Capture a photo by:
#   - Pressing SPACE  (manual, always works)
#   - Saying "take picture"  (voice, via laptop microphone)
#
# Before running:
#   1. Start rtmp_server.js
#   2. Start streaming from DJI Mimo to that RTMP URL
#   3. Run this script
# ─────────────────────────────────────────────────────────────

import cv2
import datetime
import os
import threading
import queue

import speech_recognition as sr

# ── Your PC's IP address ──────────────────────────────────────
PC_IP      = "10.138.211.63"
RTMP_PORT  = 1935
STREAM_KEY = "live/stream"
RTMP_RECEIVE_URL = f"rtmp://{PC_IP}:{RTMP_PORT}/{STREAM_KEY}"

# ── Output folder ─────────────────────────────────────────────
CAPTURE_DIR = "dji_wireless_captures"
os.makedirs(CAPTURE_DIR, exist_ok=True)

# ── Voice trigger phrases ──────────────────────────────────────
# Any of these spoken phrases will trigger a capture
TRIGGER_PHRASES = ["take picture", "take a picture", "take photo", "capture"]

# Shared flag set by the voice thread, read by the main video loop
capture_requested = threading.Event()
stop_listening     = threading.Event()


def voice_listener():
    """
    Runs in a background thread.
    Continuously listens to the laptop microphone and sets
    capture_requested whenever a trigger phrase is heard.
    """
    recognizer = sr.Recognizer()
    mic        = sr.Microphone()

    with mic as source:
        print("🎙️  Calibrating microphone for ambient noise...")
        recognizer.adjust_for_ambient_noise(source, duration=2)
    print("🎙️  Voice control ready — say 'take picture' anytime.\n")

    while not stop_listening.is_set():
        try:
            with mic as source:
                audio = recognizer.listen(source, timeout=4, phrase_time_limit=4)
            text = recognizer.recognize_google(audio).lower()
            print(f"🗣️  Heard: \"{text}\"")

            if any(phrase in text for phrase in TRIGGER_PHRASES):
                print("✅ Voice trigger matched — capturing photo!")
                capture_requested.set()

        except sr.WaitTimeoutError:
            continue  # no speech detected in this window, keep listening
        except sr.UnknownValueError:
            continue  # speech was unclear, ignore and keep listening
        except sr.RequestError as e:
            print(f"⚠️  Speech recognition service error: {e}")
        except Exception as e:
            print(f"⚠️  Voice listener error: {e}")


def save_frame(frame, photo_count, source_label="manual"):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = os.path.join(CAPTURE_DIR, f"{source_label}_{timestamp}.jpg")
    cv2.imwrite(filename, frame)
    print(f"📸 Photo {photo_count} saved ({source_label}): {filename}")


def main():
    print("=" * 55)
    print("  DJI Action 3 — Wireless Feed + Voice Trigger")
    print("=" * 55)
    print(f"\n  Stream URL: {RTMP_RECEIVE_URL}")
    print("\n  Controls:")
    print("  SPACE          = capture photo")
    print("  Say 'take picture' = capture photo (voice)")
    print("  Q              = quit")
    print("=" * 55)
    input("\n  Press ENTER once DJI Mimo is streaming...")

    print("\n  Connecting to stream...")
    cap = cv2.VideoCapture(RTMP_RECEIVE_URL)

    if not cap.isOpened():
        print("\n❌ Could not receive stream.")
        print("  Make sure Mimo is streaming BEFORE running this script.")
        return

    print("✅ Receiving stream from DJI Action 3!\n")

    # Start the voice listener in the background
    voice_thread = threading.Thread(target=voice_listener, daemon=True)
    voice_thread.start()

    photo_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("⚠️  Stream interrupted.")
            break

        cv2.imshow("DJI Action 3 — Wireless Feed (SPACE or voice 'take picture' = capture, Q = quit)", frame)

        key = cv2.waitKey(1) & 0xFF

        # Manual trigger — SPACE
        if key == ord(" "):
            photo_count += 1
            save_frame(frame, photo_count, source_label="manual")

        # Voice trigger — checked every loop iteration
        if capture_requested.is_set():
            photo_count += 1
            save_frame(frame, photo_count, source_label="voice")
            capture_requested.clear()

        # Quit
        if key == ord("q"):
            print(f"\n  Session ended. {photo_count} photo(s) saved to '{CAPTURE_DIR}/'")
            break

    stop_listening.set()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
