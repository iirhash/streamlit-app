"""
Collector Shoe Wear Bucket Estimator
=====================================

Instead of reporting a single precise thickness number (which is fragile
when derived from a photo), this tool classifies the shoe's remaining
thickness into a coarse bucket:

    >= 5mm   |   < 5mm   |   < 4mm   |   < 3mm   |   < 2mm   |   < 1mm

It reduces click/calibration noise by asking you to click each of the two
lines (the reference object, and the shoe's current thickness) THREE times
and averaging the results, then reports:
    - the bucket
    - the raw averaged measurement + its spread (std dev)
    - a CONFIDENT / BORDERLINE flag -- BORDERLINE means the measurement is
      close enough to a bucket boundary that you should double check with
      a caliper before trusting the bucket.

IMPORTANT CAVEAT (read this)
-----------------------------
Bucketing does NOT remove the need for a decent calibration reference --
the buckets are still only 1mm apart. Averaging repeated clicks helps with
human click-precision error, but it cannot fix:
    - a bad/incorrectly-sized reference object,
    - the reference and the shoe being in different focal planes
      (perspective distortion), or
    - the photo angle not being perpendicular to the true wear-depth axis.
For anything you plan to act on (e.g. scheduling a shoe replacement), treat
a "BORDERLINE" result -- and ideally even a "CONFIDENT" one -- as a trigger
to verify with a physical caliper/depth gauge, not as a final answer.

HOW TO USE
----------
    python measure_shoe_thickness_bucketed.py <image_path> [options]

Options:
    --buckets 5 4 3 2 1     Bucket thresholds in mm, descending (default: 5 4 3 2 1)
    --repeats 3             How many times to click each line (default: 3)
    --tolerance 0.5         mm margin around a boundary considered "borderline" (default: 0.5)
    --ref-mm <value>        Skip the terminal prompt, give reference length directly

Controls in each click window:
    - Click point 1, then point 2
    - Press ENTER to accept this repeat and move to the next
    - Press 'r' to redo the current repeat
    - Press 'q' / ESC to quit

Requires: opencv-python  (pip install opencv-python)
"""

import sys
import argparse
import math
import os
import statistics
import cv2


class PointPicker:
    """Click-to-collect-points helper for ONE pair of points."""

    def __init__(self, window_name, image, instruction):
        self.window_name = window_name
        self.base_image = image
        self.display = image.copy()
        self.points = []
        self.instruction = instruction
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, 1200, 800)
        cv2.setMouseCallback(self.window_name, self._on_click)

    def _on_click(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(self.points) < 2:
            self.points.append((x, y))
            self._redraw()

    def _redraw(self):
        self.display = self.base_image.copy()
        for i, p in enumerate(self.points):
            cv2.circle(self.display, p, 6, (0, 0, 255), -1)
            cv2.putText(self.display, str(i + 1), (p[0] + 8, p[1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        if len(self.points) == 2:
            cv2.line(self.display, self.points[0], self.points[1], (0, 255, 0), 2)

    def run(self):
        while True:
            frame = self.display.copy()
            cv2.putText(frame, self.instruction[:90], (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 255, 255), 2)
            cv2.imshow(self.window_name, frame)
            key = cv2.waitKey(20) & 0xFF
            if key in (27, ord('q')):
                return None
            if key == ord('r'):
                self.points = []
                self._redraw()
            if key in (13, 10) and len(self.points) == 2:
                return tuple(self.points)


def pixel_distance(p1, p2):
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def collect_repeated_measurement(image, window_name, label, repeats):
    """Click the same line `repeats` times, return list of pixel distances."""
    distances = []
    for i in range(repeats):
        picker = PointPicker(
            window_name, image,
            f"{label} -- repeat {i + 1}/{repeats}: click 2 points, ENTER to confirm"
        )
        pts = picker.run()
        cv2.destroyAllWindows()
        if pts is None:
            return None
        distances.append(pixel_distance(*pts))
        print(f"  Repeat {i + 1}/{repeats}: {distances[-1]:.1f} px")
    return distances


def bucket_and_confidence(value_mm, thresholds, tolerance):
    """
    Cleaner implementation: thresholds descending, e.g. [5,4,3,2,1].
    Buckets (from high to low): >=5, [4,5), [3,4), [2,3), [1,2), <1
    Returns (label, is_borderline, nearest_boundary_distance)
    """
    thresholds = sorted(thresholds, reverse=True)
    boundaries = thresholds  # e.g. 5,4,3,2,1

    if value_mm >= boundaries[0]:
        label = f">= {boundaries[0]:g}mm"
    else:
        label = f"< {boundaries[-1]:g}mm"  # default: below smallest threshold
        for i in range(len(boundaries) - 1):
            hi, lo = boundaries[i], boundaries[i + 1]
            if lo <= value_mm < hi:
                label = f"< {hi:g}mm"
                break

    nearest_boundary_dist = min(abs(value_mm - b) for b in boundaries)
    is_borderline = nearest_boundary_dist <= tolerance
    return label, is_borderline, nearest_boundary_dist


def main():
    parser = argparse.ArgumentParser(description="Bucketed collector shoe wear estimate from a photo.")
    parser.add_argument("image_path", help="Path to the input image")
    parser.add_argument("--buckets", type=float, nargs="+", default=[5, 4, 3, 2, 1],
                         help="Bucket thresholds in mm, e.g. --buckets 5 4 3 2 1")
    parser.add_argument("--repeats", type=int, default=3,
                         help="Number of times to click each line for averaging (default: 3)")
    parser.add_argument("--tolerance", type=float, default=0.2,
                         help="mm margin around a boundary considered borderline (default: 0.2). "
                              "Note: with 1mm-wide buckets, a value of 0.5 would flag almost "
                              "everything as borderline (since 0.5mm is the max possible distance "
                              "from any point to its nearest boundary) -- keep this well under 0.5.")
    parser.add_argument("--ref-mm", type=float, default=None,
                         help="Reference object's real length in mm (skip terminal prompt)")
    args = parser.parse_args()

    if not os.path.exists(args.image_path):
        print(f"Error: file not found: {args.image_path}")
        sys.exit(1)

    image = cv2.imread(args.image_path)
    if image is None:
        print("Error: could not read image.")
        sys.exit(1)

    # --- Step 1: calibration (repeated) ---
    print("\n=== STEP 1: Reference object calibration ===")
    print("Click the same known-size reference object's two endpoints, "
          f"{args.repeats} times, for averaging.")
    ref_distances_px = collect_repeated_measurement(
        image, "Step 1: Reference object", "Click reference object endpoints", args.repeats
    )
    if ref_distances_px is None:
        print("Cancelled.")
        sys.exit(0)

    ref_px_mean = statistics.mean(ref_distances_px)
    ref_px_std = statistics.stdev(ref_distances_px) if len(ref_distances_px) > 1 else 0.0
    print(f"Reference: mean = {ref_px_mean:.1f} px, std dev = {ref_px_std:.1f} px "
          f"({(ref_px_std / ref_px_mean * 100 if ref_px_mean else 0):.1f}% noise)")

    if args.ref_mm is not None:
        ref_mm = args.ref_mm
    else:
        while True:
            try:
                ref_mm = float(input("\nEnter the REAL-WORLD length of the reference object in mm: "))
                if ref_mm > 0:
                    break
                print("Please enter a positive number.")
            except ValueError:
                print("Please enter a numeric value.")

    mm_per_px = ref_mm / ref_px_mean
    print(f"Calibration: {mm_per_px:.5f} mm/pixel")

    # --- Step 2: shoe measurement (repeated) ---
    print("\n=== STEP 2: Shoe current thickness ===")
    print(f"Click the shoe's current wear-face thickness endpoints, {args.repeats} times.")
    shoe_distances_px = collect_repeated_measurement(
        image, "Step 2: Shoe thickness", "Click shoe thickness endpoints", args.repeats
    )
    if shoe_distances_px is None:
        print("Cancelled.")
        sys.exit(0)

    shoe_px_mean = statistics.mean(shoe_distances_px)
    shoe_px_std = statistics.stdev(shoe_distances_px) if len(shoe_distances_px) > 1 else 0.0
    print(f"Shoe: mean = {shoe_px_mean:.1f} px, std dev = {shoe_px_std:.1f} px "
          f"({(shoe_px_std / shoe_px_mean * 100 if shoe_px_mean else 0):.1f}% noise)")

    current_thickness_mm = shoe_px_mean * mm_per_px
    # propagate pixel noise (both ref and shoe clicking noise) into an mm uncertainty estimate
    rel_noise = math.sqrt(
        (ref_px_std / ref_px_mean) ** 2 if ref_px_mean else 0
        + (shoe_px_std / shoe_px_mean) ** 2 if shoe_px_mean else 0
    )
    thickness_uncertainty_mm = current_thickness_mm * rel_noise

    label, is_borderline, boundary_dist = bucket_and_confidence(
        current_thickness_mm, args.buckets, args.tolerance
    )

    # --- Report ---
    print("\n" + "=" * 55)
    print("COLLECTOR SHOE WEAR -- BUCKETED ESTIMATE")
    print("=" * 55)
    print(f"Averaged measured thickness: {current_thickness_mm:.2f} mm "
          f"(+/- ~{thickness_uncertainty_mm:.2f} mm from click noise)")
    print(f"Bucket estimate:             {label}")
    print(f"Distance to nearest boundary: {boundary_dist:.2f} mm "
          f"(tolerance: {args.tolerance:g} mm)")
    if is_borderline:
        print("Confidence:                  BORDERLINE -- verify with a caliper before acting on this")
    else:
        print("Confidence:                  reasonably clear of a boundary given click noise, "
              "but still recommend spot-checking with a caliper for anything safety-critical")
    print("=" * 55)

    if current_thickness_mm <= 0 or current_thickness_mm > 30:
        print("\nWarning: measured value looks implausible for a 16mm-nominal shoe. "
              "Check that your reference object's real length is correct and that both "
              "lines were clicked on the correct, comparable features.")

    # --- Save annotated image (using the LAST repeat's points as the visual) ---
    # (Re-run picks aren't stored individually here beyond distances; for a visual
    #  record, click once more on each line to annotate.)
    print("\nFor a saved annotated image, click each line one more time.")
    calib_picker = PointPicker(
        "Annotation: reference line", image, "Click reference line once more for the saved image"
    )
    calib_pts = calib_picker.run()
    cv2.destroyAllWindows()
    shoe_picker = PointPicker(
        "Annotation: shoe line", image, "Click shoe line once more for the saved image"
    )
    shoe_pts = shoe_picker.run()
    cv2.destroyAllWindows()

    if calib_pts and shoe_pts:
        annotated = image.copy()
        cv2.line(annotated, calib_pts[0], calib_pts[1], (255, 0, 0), 3)
        cv2.putText(annotated, f"Ref: {ref_mm:.1f}mm", calib_pts[0],
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 0), 2)
        cv2.line(annotated, shoe_pts[0], shoe_pts[1], (0, 255, 0), 3)
        cv2.putText(annotated, f"~{current_thickness_mm:.1f}mm ({label})", shoe_pts[0],
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        base, ext = os.path.splitext(args.image_path)
        out_path = f"{base}_bucketed.jpg"
        cv2.imwrite(out_path, annotated)
        print(f"Annotated image saved to: {out_path}")


if __name__ == "__main__":
    main()
