# simulate_collector_shoe.py
# ── Collector Shoe Wear Tracking — Data Simulator ─────────────
# Run with: python simulate_collector_shoe.py
#
# Based on confirmed engineering data:
#   Original depth: 16mm
#   Rotate at:      4mm wear (12mm remaining)
#   Replace at:     5mm wear (11mm remaining)
#
# CS-001-NEW — first use, not yet rotated
#   Simulates 4 sessions of gradual wear from 16mm down
#
# CS-001-OLD — used twice (both sides worn), end of service life
#   Simulates 4 sessions showing progressive wear past replace limit
# ─────────────────────────────────────────────────────────────

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from supabase import create_client
from config.settings import SUPABASE_URL, SUPABASE_KEY
from datetime import datetime, timedelta

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):     print(f"  {GREEN}✓{RESET}  {msg}")
def fail(msg):   print(f"  {RED}✗{RESET}  {msg}")
def info(msg):   print(f"  {BLUE}ℹ{RESET}  {msg}")
def header(msg): print(f"\n{BOLD}{YELLOW}{msg}{RESET}")


TODAY = datetime.now()

# ── Realistic simulation based on 16mm original depth ──────────
# Wear thresholds (remaining thickness):
#   ≥ 14.1mm → none   (wear 0–1.9mm)
#   12.1–14.0mm → minor   (wear 2–3.9mm)
#   11.1–12.0mm → moderate (wear 4–4.9mm) ❌ fail
#   ≤ 11.0mm → severe  (wear ≥5mm)        ❌ fail

SESSIONS = [
    # ── CS-001-NEW: not rotated, slow wear from new ───────────
    {
        "date":              TODAY - timedelta(weeks=3),
        "shoe_id":           "CS-001-NEW",
        "technician_name":   "Iman Irhash Bin Amidan",
        "thickness_mm":      15.8,          # wear 0.2mm — none
        "physical_severity": "none",
        "visual_severity":   "none",        # agree ✅
        "yolo_confidence":   0.91,
        "wear_zones":        0,
        "notes":             "Week 1 baseline — new shoe, minimal wear",
    },
    {
        "date":              TODAY - timedelta(weeks=2),
        "shoe_id":           "CS-001-NEW",
        "technician_name":   "Iman Irhash Bin Amidan",
        "thickness_mm":      14.9,          # wear 1.1mm — none
        "physical_severity": "none",
        "visual_severity":   "minor",       # disagree ❌ (YOLO sees early surface marks)
        "yolo_confidence":   0.67,
        "wear_zones":        1,
        "notes":             "Week 2 — slight surface marks visible on camera, physical still none",
    },
    {
        "date":              TODAY - timedelta(weeks=1),
        "shoe_id":           "CS-001-NEW",
        "technician_name":   "Iman Irhash Bin Amidan",
        "thickness_mm":      13.5,          # wear 2.5mm — minor
        "physical_severity": "minor",
        "visual_severity":   "minor",       # agree ✅
        "yolo_confidence":   0.83,
        "wear_zones":        1,
        "notes":             "Week 3 — entered minor wear zone, increase inspection frequency",
    },
    {
        "date":              TODAY,
        "shoe_id":           "CS-001-NEW",
        "technician_name":   "Iman Irhash Bin Amidan",
        "thickness_mm":      12.8,          # wear 3.2mm — minor, approaching rotation
        "physical_severity": "minor",
        "visual_severity":   "minor",       # agree ✅
        "yolo_confidence":   0.87,
        "wear_zones":        2,
        "notes":             "Week 4 — approaching rotation threshold (4mm wear = 12mm remaining)",
    },

    # ── CS-001-OLD: rotated twice, past replacement limit ──────
    {
        "date":              TODAY - timedelta(weeks=3),
        "shoe_id":           "CS-001-OLD",
        "technician_name":   "Iman Irhash Bin Amidan",
        "thickness_mm":      12.1,          # wear 3.9mm — minor (borderline)
        "physical_severity": "minor",
        "visual_severity":   "moderate",    # disagree ❌ (YOLO sees worse wear on surface)
        "yolo_confidence":   0.71,
        "wear_zones":        2,
        "notes":             "Week 1 — old shoe already near rotation threshold",
    },
    {
        "date":              TODAY - timedelta(weeks=2),
        "shoe_id":           "CS-001-OLD",
        "technician_name":   "Iman Irhash Bin Amidan",
        "thickness_mm":      11.8,          # wear 4.2mm — moderate ❌ fail
        "physical_severity": "moderate",
        "visual_severity":   "moderate",    # agree ✅
        "yolo_confidence":   0.79,
        "wear_zones":        3,
        "notes":             "Week 2 — crossed rotation threshold. Already rotated twice — must replace.",
    },
    {
        "date":              TODAY - timedelta(weeks=1),
        "shoe_id":           "CS-001-OLD",
        "technician_name":   "Iman Irhash Bin Amidan",
        "thickness_mm":      11.2,          # wear 4.8mm — moderate ❌ fail
        "physical_severity": "moderate",
        "visual_severity":   "severe",      # disagree ❌ (YOLO detects severe surface damage)
        "yolo_confidence":   0.84,
        "wear_zones":        4,
        "notes":             "Week 3 — YOLO detecting severe surface damage, approaching 5mm limit",
    },
    {
        "date":              TODAY,
        "shoe_id":           "CS-001-OLD",
        "technician_name":   "Iman Irhash Bin Amidan",
        "thickness_mm":      10.8,          # wear 5.2mm — severe ❌ fail → REPLACE
        "physical_severity": "severe",
        "visual_severity":   "severe",      # agree ✅
        "yolo_confidence":   0.88,
        "wear_zones":        5,
        "notes":             "Week 4 — exceeded 5mm wear limit. REPLACE IMMEDIATELY. Both sides used.",
    },
]


def get_severity(thickness_mm):
    """Derives severity from remaining thickness based on confirmed OMM thresholds."""
    if thickness_mm >= 14.1:  return "none"
    if thickness_mm >= 12.1:  return "minor"
    if thickness_mm >= 11.1:  return "moderate"
    return "severe"


def get_pass_fail(severity):
    return "pass" if severity in ("none", "minor") else "fail"


def main():
    print("=" * 60)
    print("  Collector Shoe Simulator — Real OMM Thresholds")
    print("  Original depth: 16mm | Rotate: 4mm wear | Replace: 5mm wear")
    print("=" * 60)

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    ok("Connected to Supabase")

    # Login for RLS
    header("Logging in as staff")
    SAP_NUMBER = "S12345"
    PASSWORD   = "Thisisthedeveloperpassword"
    try:
        supabase.auth.sign_in_with_password({
            "email":    f"{SAP_NUMBER}@lrt-internal.com",
            "password": PASSWORD,
        })
        ok(f"Logged in as {SAP_NUMBER}")
    except Exception as e:
        fail(f"Login failed: {e}")
        return

    # Check existing data
    header("Checking for existing simulation data")
    existing = supabase.table("shoe_physical_inspections") \
        .select("id") \
        .in_("shoe_id", ["CS-001-NEW", "CS-001-OLD"]) \
        .execute()

    if existing.data:
        print(f"\n  ⚠️  Found {len(existing.data)} existing record(s).")
        confirm = input("  Delete and re-simulate? (y/n): ").strip().lower()
        if confirm == "y":
            supabase.table("shoe_physical_inspections") \
                .delete().in_("shoe_id", ["CS-001-NEW", "CS-001-OLD"]).execute()
            supabase.table("shoe_visual_inspections") \
                .delete().in_("shoe_id", ["CS-001-NEW", "CS-001-OLD"]).execute()
            ok("Existing data deleted")
        else:
            print("  Keeping existing data. Exiting.")
            return

    header("Inserting simulated sessions")

    for s in SESSIONS:
        date_str    = s["date"].strftime("%Y-%m-%d %H:%M:%S+00")
        phys_sev    = get_severity(s["thickness_mm"])
        pf          = get_pass_fail(phys_sev)
        corr        = "agree" if phys_sev == s["visual_severity"] else "disagree"
        shoe_label  = f"{s['shoe_id']} [{s['date'].strftime('%d %b')}]"
        wear_mm     = round(16.0 - s["thickness_mm"], 1)

        # Create session
        session_resp = supabase.table("inspection_sessions").insert({
            "technician_name": s["technician_name"],
            "employee_id":     "SIM-001",
            "asset_id":        s["shoe_id"],
            "status":          "submitted",
            "notes":           f"[SIMULATED] {s['notes']}",
        }).execute()

        if not session_resp.data:
            fail(f"{shoe_label} — session insert failed")
            continue

        session_id = session_resp.data[0]["id"]

        # Physical inspection
        phys_resp = supabase.table("shoe_physical_inspections").insert({
            "shoe_id":           s["shoe_id"],
            "session_id":        session_id,
            "technician_name":   s["technician_name"],
            "employee_id":       "SIM-001",
            "thickness_mm":      s["thickness_mm"],
            "physical_severity": phys_sev,
            "notes":             f"[SIMULATED] {s['notes']}",
            "inspected_at":      date_str,
        }).execute()

        if not phys_resp.data:
            fail(f"{shoe_label} — physical insert failed")
            continue

        # Visual inspection
        vis_resp = supabase.table("shoe_visual_inspections").insert({
            "shoe_id":             s["shoe_id"],
            "technician_name":     s["technician_name"],
            "visual_severity":     s["visual_severity"],
            "confidence":          s["yolo_confidence"],
            "wear_zones_detected": s["wear_zones"],
            "notes":               f"[SIMULATED] {s['notes']}",
            "inspected_at":        date_str,
        }).execute()

        if not vis_resp.data:
            fail(f"{shoe_label} — visual insert failed")
            continue

        pf_icon   = "✅" if pf == "pass" else "❌"
        corr_icon = "✅" if corr == "agree" else "❌"
        ok(
            f"{shoe_label} — "
            f"{s['thickness_mm']}mm (wear {wear_mm}mm) | "
            f"{phys_sev} {pf_icon} | "
            f"vis: {s['visual_severity']} | "
            f"{corr_icon} {corr}"
        )

    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}Simulation complete!{RESET}")
    print(f"\n  Open dashboard → 👟 Collector Shoe")
    print(f"  All sections populated with real OMM-based data.")
    print(f"\n  Key findings to present:")
    print(f"  {GREEN}✓{RESET} CS-001-NEW at 12.8mm — 3.2mm wear — minor, approaching rotation")
    print(f"  {RED}✗{RESET} CS-001-OLD at 10.8mm — 5.2mm wear — SEVERE, replace immediately")
    print(f"{'─'*60}\n")


if __name__ == "__main__":
    main()
