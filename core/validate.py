# core/validate.py
# ── Validation helpers ─────────────────────────────────────────
# Update THRESHOLDS once confirmed by supervisor

# ── Default thresholds ────────────────────────────────────────
THRESHOLDS = {
    "Multimeter - Voltage":    {"min": 220, "max": 240, "unit": "V"},
    "Multimeter - Current":    {"min": 0,   "max": 15,  "unit": "A"},
    "Multimeter - Resistance": {"min": 0,   "max": 100, "unit": "Ohm"},
    "Digital Torque Wrench":   {"min": 45,  "max": 55,  "unit": "Nm"},
    "Temp / Humidimeter":      {"min": 15,  "max": 40,  "unit": "C"},
    "Humidity (Humidimeter)":  {"min": 30,  "max": 70,  "unit": "%RH"},
    "Digital Sound Meter":     {"min": 0,   "max": 85,  "unit": "dB"},
}


def validate_reading(tool_name, value, thresholds=None):
    """
    Checks if a single measurement is within the acceptable range.

    Steps:
      1. Gets min/max for the tool from thresholds (falls back to THRESHOLDS)
      2. Calculates a 10% warning buffer near the limits
      3. Returns PASS, WARN, or FAIL with a human-readable message

    Args:
        tool_name  - e.g. "Multimeter - Voltage"
        value      - the measured number, e.g. 228.4
        thresholds - optional dict override (pass TOOLS or MULTIMETER from settings)

    Returns a dict with keys:
        passed, status, level, message, value, unit, min, max
    """
    lookup = thresholds or THRESHOLDS

    if tool_name not in lookup:
        return {
            "passed":  None,
            "status":  "No threshold set",
            "level":   "UNKNOWN",
            "message": f"No threshold defined for '{tool_name}' — add it to settings.py",
            "value":   value,
            "unit":    "",
            "min":     None,
            "max":     None,
        }

    t       = lookup[tool_name]
    min_val = t["min"]
    max_val = t["max"]
    unit    = t.get("unit", "")
    buffer  = (max_val - min_val) * 0.10

    if value < min_val or value > max_val:
        if value < min_val:
            diff = round(min_val - value, 2)
            msg  = f"OUT OF RANGE: {value} {unit} is {diff} {unit} below minimum ({min_val})"
        else:
            diff = round(value - max_val, 2)
            msg  = f"OUT OF RANGE: {value} {unit} is {diff} {unit} above maximum ({max_val})"
        return {
            "passed": False, "status": "Out of Range", "level": "FAIL",
            "message": msg, "value": value, "unit": unit,
            "min": min_val, "max": max_val,
        }

    elif value <= min_val + buffer or value >= max_val - buffer:
        return {
            "passed": True, "status": "Warning", "level": "WARN",
            "message": f"NEAR LIMIT: {value} {unit} is close to [{min_val} – {max_val}]",
            "value": value, "unit": unit, "min": min_val, "max": max_val,
        }

    else:
        return {
            "passed": True, "status": "Within Range", "level": "PASS",
            "message": f"OK: {value} {unit} is within range [{min_val} – {max_val}]",
            "value": value, "unit": unit, "min": min_val, "max": max_val,
        }


def validate_all_readings(readings, thresholds=None):
    """
    Validates multiple tool readings at once.

    Args:
        readings   - dict of {tool_name: value}
        thresholds - optional override dict

    Returns:
        results - dict of {tool_name: validation_result}
        summary - overall counts dict
    """
    results = {}
    for tool_name, value in readings.items():
        if value == 0.0:
            continue
        results[tool_name] = validate_reading(tool_name, value, thresholds)

    total   = len(results)
    passed  = sum(1 for r in results.values() if r["level"] == "PASS")
    warned  = sum(1 for r in results.values() if r["level"] == "WARN")
    failed  = sum(1 for r in results.values() if r["level"] == "FAIL")
    unknown = sum(1 for r in results.values() if r["level"] == "UNKNOWN")

    summary = {
        "total":      total,
        "passed":     passed,
        "warned":     warned,
        "failed":     failed,
        "unknown":    unknown,
        "all_passed": failed == 0,
        "pass_rate":  round((passed / total * 100), 1) if total > 0 else 0,
    }
    return results, summary


def get_status_color(level):
    """Returns a hex colour for a given validation level."""
    return {
        "PASS":    "#0A8A72",
        "WARN":    "#E8920A",
        "FAIL":    "#C9382A",
        "UNKNOWN": "#888780",
    }.get(level, "#888780")
