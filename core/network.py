# core/network.py
# ── Finds this laptop's current local IP address ───────────────
# Used by the wireless stations (RTMP) and the dashboard help text,
# so nothing breaks when the laptop joins a different network.
#
# To force a fixed IP instead, add this line to .env:
#   PC_IP=172.19.120.63

import os
import socket


def is_cloud():
    """True when running on Streamlit Community Cloud (app lives in /mount/src)."""
    return os.getcwd().startswith("/mount/src") or os.path.isdir("/mount/src")


def get_local_ip():
    override = os.getenv("PC_IP", "").strip()
    if override:
        return override
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No data is sent; this just asks the OS which network
        # adapter would be used to reach the outside world.
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        s.close()
