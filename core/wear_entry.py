# core/wear_entry.py
# ── Collector shoe wear depth entry — shared rules ─────────────
# Used by every camera station (wired, wireless, mobile, DJI mobile)
# so the same checks apply everywhere.
#
# The technician types the reading from the depth gauge, which is
# the DEPTH WORN AWAY (a new shoe reads about 0 mm).
#
# Saving is done through the Supabase RPC `record_wear_reading`,
# which re-checks the value on the server and also stores
# thickness_mm = baseline - wear for the existing dashboard views.
# ─────────────────────────────────────────────────────────────

# ── OMM engineering data ──────────────────────────────────────
ORIGINAL_DEPTH_MM   = 16.0   # new shoe thickness
ROTATION_TRIGGER_MM = 4.0    # dry (non-rainy) season default
REPLACE_LIMIT_MM    = 5.0
MAX_WEAR_MM         = ORIGINAL_DEPTH_MM   # anything above this is impossible

# Severity bands (mm of wear) — must match record_wear_reading in Supabase
SEVERITY_BANDS = [
    (2.0, "none"),       # 0 – 1.9
    (4.0, "minor"),      # 2 – 3.9
    (5.0, "moderate"),   # 4 – 4.9
]                        # >= 5 → severe


# Same colours as the Shoe Health Monitor severity scheme (collector_shoe.py)
SEVERITY_COLORS = {
    "none":     "#0A8A72",
    "minor":    "#E8920A",
    "moderate": "#E85D04",
    "severe":   "#C9382A",
}


def severity_box_html(text, severity):
    """Coloured message box for Streamlit pages, using the severity colour."""
    color = SEVERITY_COLORS.get(severity, "#64748B")
    return (f'<div style="background:{color}1A;border:2px solid {color};border-radius:10px;'
            f'padding:12px 16px;margin:8px 0;color:#1E293B;font-size:15px;">'
            f'<span style="display:inline-block;background:{color};color:white;border-radius:10px;'
            f'padding:2px 10px;font-size:12px;font-weight:700;margin-right:8px;">'
            f'{severity.upper()}</span>{text}</div>')


def get_severity(wear_mm):
    """Returns 'none', 'minor', 'moderate' or 'severe' for a wear reading."""
    for upper, label in SEVERITY_BANDS:
        if wear_mm < upper:
            return label
    return "severe"


def parse_reading(text):
    """
    Turns the typed text into a number.
    Returns (value, error_message). value is None if the text is not valid.
    """
    text = (text or "").strip().replace(",", ".")
    if not text:
        return None, "Please enter the wear depth reading from the gauge."
    try:
        value = float(text)
    except ValueError:
        return None, f"'{text}' is not a number. Please type the reading in mm, e.g. 2.8"
    return round(value, 2), None


def check_reading(wear_mm, last_wear_mm=None, reset_baseline=False,
                  rotation_trigger_mm=ROTATION_TRIGGER_MM):
    """
    Week 11 wrong-entry rules.

    Returns a dict:
      level   : "reject" | "check_again" | "warn" | "ok"
      message : text to show the technician
    Rules, in order:
      1. Impossible value  → reject (cannot be saved)
      2. Less wear than the last reading (and the shoe was NOT new or
         just rotated) → check_again (re-measure, then confirm)
      3. At or above replace / rotation limit → warn (confirm, inform IC)
      4. Otherwise → ok
    """
    if wear_mm < 0 or wear_mm > MAX_WEAR_MM:
        return {
            "level": "reject",
            "message": f"{wear_mm} mm is not possible. The reading must be between 0 and {MAX_WEAR_MM:g} mm.",
        }

    if (last_wear_mm is not None and not reset_baseline
            and wear_mm < float(last_wear_mm)):
        return {
            "level": "check_again",
            "message": (f"This reading ({wear_mm} mm) shows LESS wear than the last reading "
                        f"({float(last_wear_mm):g} mm). Wear should not go down unless the shoe "
                        f"was replaced or rotated. Please re-measure before saving."),
        }

    if wear_mm >= REPLACE_LIMIT_MM:
        return {
            "level": "warn",
            "message": (f"{wear_mm} mm is at or above the REPLACEMENT limit ({REPLACE_LIMIT_MM:g} mm). "
                        f"Inform your IC after saving."),
        }

    if wear_mm >= rotation_trigger_mm:
        return {
            "level": "warn",
            "message": (f"{wear_mm} mm is at or above the ROTATION trigger ({rotation_trigger_mm:g} mm). "
                        f"Inform your IC after saving."),
        }

    return {"level": "ok", "message": f"{wear_mm} mm — severity: {get_severity(wear_mm)}."}


def get_last_reading(supabase, shoe_id):
    """Latest saved wear reading (mm) for this shoe, or None if there is none."""
    try:
        r = supabase.table("shoe_physical_inspections") \
            .select("wear_mm, thickness_mm, inspected_at") \
            .eq("shoe_id", shoe_id) \
            .order("inspected_at", desc=True) \
            .limit(1).execute()
        if not r.data:
            return None
        row = r.data[0]
        if row.get("wear_mm") is not None:
            return float(row["wear_mm"])
        # Older rows only had thickness — convert back to wear
        if row.get("thickness_mm") is not None:
            return round(ORIGINAL_DEPTH_MM - float(row["thickness_mm"]), 2)
    except Exception as e:
        print(f"  ⚠️  Could not load last wear reading: {e}")
    return None


def save_reading(supabase, shoe_id, session_id, technician_name, wear_mm, notes=None):
    """
    Saves the reading through the secure RPC. Returns (ok, message).
    Must be called AFTER the shoe is registered and the session is created.
    """
    try:
        resp = supabase.rpc("record_wear_reading", {
            "p_shoe_id":    shoe_id,
            "p_session_id": session_id,
            "p_technician": technician_name,
            "p_wear_mm":    wear_mm,
            "p_notes":      notes,
        }).execute()
        if resp.data:
            return True, f"Wear reading saved: {wear_mm} mm ({get_severity(wear_mm)})"
        return False, "Wear reading was not saved (no response from server)."
    except Exception as e:
        return False, f"Wear reading was not saved: {e}"
