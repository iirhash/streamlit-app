# core/ble_receiver.py
# ── BLE Receiver ───────────────────────────────────────────────
# Simulates BLE readings from all tools.
# Replace simulation functions with real bleak calls once
# physical tools are connected.

import random
import logging

log = logging.getLogger(__name__)  # fixed: was getlogger (typo)

# ── Simulated device addresses ────────────────────────────────
# Replace with actual Bluetooth MAC addresses when tools arrive
SIMULATED_DEVICES = {
    "Multimeter - Voltage":    {"address": "AA:BB:CC:DD:EE:01", "unit": "V"},
    "Multimeter - Current":    {"address": "AA:BB:CC:DD:EE:02", "unit": "A"},
    "Multimeter - Resistance": {"address": "AA:BB:CC:DD:EE:03", "unit": "Ohm"},
    "Digital Torque Wrench":   {"address": "AA:BB:CC:DD:EE:04", "unit": "Nm"},
    "Temp / Humidimeter":      {"address": "AA:BB:CC:DD:EE:05", "unit": "C"},
    "Humidity (Humidimeter)":  {"address": "AA:BB:CC:DD:EE:06", "unit": "%RH"},
    "Digital Sound Meter":     {"address": "AA:BB:CC:DD:EE:07", "unit": "dB"},
}

# ── Simulated value ranges ────────────────────────────────────
# Intentionally slightly wider than thresholds to generate
# realistic mix of pass/fail readings for testing
SIMULATED_RANGES = {
    "Multimeter - Voltage":    {"lo": 210, "hi": 250},
    "Multimeter - Current":    {"lo": 0,   "hi": 20},
    "Multimeter - Resistance": {"lo": 0,   "hi": 120},
    "Digital Torque Wrench":   {"lo": 30,  "hi": 70},
    "Temp / Humidimeter":      {"lo": 10,  "hi": 50},
    "Humidity (Humidimeter)":  {"lo": 20,  "hi": 80},
    "Digital Sound Meter":     {"lo": 0,   "hi": 100},
}


def simulate_reading(tool_name):
    """
    Returns a simulated BLE reading for a single tool.
    Remove once real BLE is connected.
    """
    if tool_name not in SIMULATED_RANGES:
        return None
    r = SIMULATED_RANGES[tool_name]
    return round(random.uniform(r["lo"], r["hi"]), 1)


def get_simulated_readings():
    """
    Returns simulated readings for ALL tools.
    Use for testing before real BLE is connected.
    """
    readings = {}
    for tool_name in SIMULATED_DEVICES:
        readings[tool_name] = simulate_reading(tool_name)
    return readings


# ── Simulation helpers ────────────────────────────────────────

DEFECT_CATEGORIES = ["none", "none", "none", "crack", "wear", "corrosion", "other"]

def get_simulated_defect():
    """Returns a random defect category. Weighted toward 'none'."""
    return random.choice(DEFECT_CATEGORIES)


TECH_NAMES = ["Ali Ahmad", "Farid Ismail", "Muhammad Adam", "Hazim Karim", "Iman Irhash"]

def get_simulated_technician():
    return random.choice(TECH_NAMES)


ASSET_IDS = ["V40A", "V40B", "V41A", "V41B", "V42A", "V42B"]

def get_simulated_asset():
    return random.choice(ASSET_IDS)


EMP_IDS = ["201234", "256789", "298765", "243210", "297531"]

def get_simulated_employee():
    return random.choice(EMP_IDS)


# ── Real BLE code (uncomment when tools are available) ────────
# async def connect_and_read(device_address):
#     """
#     Connects to a real BLE device and reads its measurement.
#     Requires: pip install bleak
#     """
#     from bleak import BleakClient, BleakError
#     MAX_RETRIES = 3
#
#     for attempt in range(MAX_RETRIES):
#         try:
#             async with BleakClient(device_address) as client:
#                 log.info(f"Connected to {device_address}")
#                 # Replace CHARACTERISTIC_UUID with your tool's UUID
#                 CHARACTERISTIC_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
#                 data = await client.read_gatt_char(CHARACTERISTIC_UUID)
#                 value = int.from_bytes(data, byteorder="little") / 100.0
#                 return value
#         except BleakError as e:
#             log.warning(f"Attempt {attempt+1} failed: {e}")
#             if attempt < MAX_RETRIES - 1:
#                 await asyncio.sleep(3)
#     return None
