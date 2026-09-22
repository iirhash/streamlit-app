# config/settings.py
# ── All project settings in one place ─────────────────────────
# Update min/max values once confirmed by supervisor

import os
from dotenv import load_dotenv

load_dotenv()

# ── Tool config with min/max thresholds ───────────────────────
# These names MUST match what ble_receiver.py sends
TOOLS = {
    "Digital Torque Wrench": {
        "unit": "Nm",
        "min":  45,
        "max":  55,
        "desc": "Measures torque applied to fasteners",
    },
    "Temp / Humidimeter": {
        "unit": "C",
        "min":  15,
        "max":  40,
        "desc": "Ambient temperature reading",
    },
    "Humidity (Humidimeter)": {
        "unit": "%RH",
        "min":  30,
        "max":  70,
        "desc": "Relative humidity reading",
    },
    "Digital Sound Meter": {
        "unit": "dB",
        "min":  0,
        "max":  85,
        "desc": "Ambient noise / sound pressure level",
    },
}

# ── Multimeter (3 separate readings) ──────────────────────────
MULTIMETER = {
    "Multimeter - Voltage": {
        "unit": "V",
        "min":  220,
        "max":  240,
    },
    "Multimeter - Current": {
        "unit": "A",
        "min":  0,
        "max":  15,
    },
    "Multimeter - Resistance": {
        "unit": "Ohm",
        "min":  0,
        "max":  100,
    },
}

# ── Combined dict (used by dashboard & BLE auto-save) ─────────
ALL_TOOLS = {**MULTIMETER, **TOOLS}

# ── File paths ────────────────────────────────────────────────
CSV_FILE   = "data/condition_records.csv"
UPLOAD_DIR = "uploads/"

# ── Supabase (loaded from .env) ───────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
