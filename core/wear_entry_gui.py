# core/wear_entry_gui.py
# ── Tkinter popup for the wear depth reading ──────────────────
# Shared by the desktop stations (wired + wireless DJI).
# Shown after the 3rd photo and BEFORE anything is saved.
# The reading is required: Cancel cancels the whole session.
# ─────────────────────────────────────────────────────────────

from core.wear_entry import (
    parse_reading, check_reading, get_severity,
    REPLACE_LIMIT_MM, ROTATION_TRIGGER_MM,
)


def ask_wear_reading(asset_id, last_wear_mm=None, reset_baseline=False,
                     header_color="#0A8A72", title="Wear Depth Reading",
                     rotation_trigger_mm=ROTATION_TRIGGER_MM, season_label=None):
    """
    Opens a popup asking for the depth gauge reading (mm of wear).
    Returns the confirmed reading (float), or None if the technician
    cancelled the session.
    """
    import tkinter as tk
    from tkinter import messagebox

    result = {"wear": None}

    root = tk.Tk()
    root.title(title)
    root.resizable(False, False)
    root.configure(bg="#F8FAFC")
    root.attributes("-topmost", True)
    root.after(200, lambda: [root.lift(), root.focus_force()])

    w, h = 440, 400
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    header = tk.Frame(root, bg=header_color, height=60)
    header.pack(fill="x")
    tk.Label(header, text="📏  Wear Depth Reading", bg=header_color, fg="white",
             font=("Calibri", 15, "bold")).pack(pady=14)

    body = tk.Frame(root, bg="#F8FAFC", padx=24, pady=14)
    body.pack(fill="both", expand=True)

    tk.Label(body, text=f"Shoe: {asset_id}", bg="#F8FAFC", fg="#1E293B",
             font=("Calibri", 11, "bold"), anchor="w").pack(fill="x")

    if reset_baseline:
        last_txt = "Last reading: — (new or just-rotated shoe)"
    elif last_wear_mm is not None:
        last_txt = f"Last reading: {last_wear_mm:g} mm"
    else:
        last_txt = "Last reading: — (first reading for this shoe)"
    tk.Label(body, text=last_txt, bg="#F8FAFC", fg="#64748B",
             font=("Calibri", 10), anchor="w").pack(fill="x", pady=(2, 10))

    tk.Label(body, text="Depth gauge reading — depth WORN AWAY (mm)",
             bg="#F8FAFC", fg="#1E293B", font=("Calibri", 11, "bold"),
             anchor="w").pack(fill="x")
    tk.Label(body, text="A new shoe reads about 0 mm.",
             bg="#F8FAFC", fg="#64748B", font=("Calibri", 9), anchor="w").pack(fill="x")

    entry_var = tk.StringVar()
    entry = tk.Entry(body, textvariable=entry_var, font=("Calibri", 20, "bold"),
                     justify="center", relief="groove", bd=2)
    entry.pack(fill="x", pady=(6, 6), ipady=6)
    entry.focus()

    limits_txt = f"Rotation at {rotation_trigger_mm:g} mm · Replace at {REPLACE_LIMIT_MM:g} mm"
    if season_label:
        limits_txt += f"  ({season_label})"
    status_var = tk.StringVar(value=limits_txt)
    status = tk.Label(body, textvariable=status_var, bg="#F8FAFC", fg="#64748B",
                      font=("Calibri", 10), anchor="w", wraplength=380, justify="left")
    status.pack(fill="x")

    # Live severity preview while typing
    def _preview(*_):
        value, err = parse_reading(entry_var.get())
        if err or value is None:
            status.config(fg="#64748B")
            status_var.set(limits_txt)
            return
        chk = check_reading(value, last_wear_mm, reset_baseline, rotation_trigger_mm)
        colour = {"reject": "#991B1B", "check_again": "#92400E",
                  "warn": "#92400E", "ok": "#166534"}[chk["level"]]
        status.config(fg=colour)
        status_var.set(chk["message"])
    entry_var.trace_add("write", _preview)

    def on_save(event=None):
        value, err = parse_reading(entry_var.get())
        if err:
            messagebox.showwarning("Reading needed", err, parent=root)
            return
        chk = check_reading(value, last_wear_mm, reset_baseline, rotation_trigger_mm)
        if chk["level"] == "reject":
            messagebox.showerror("Not possible", chk["message"], parent=root)
            return
        if chk["level"] == "check_again":
            if not messagebox.askyesno(
                    "Please re-measure",
                    chk["message"] + f"\n\nYou re-measured and {value} mm is correct?",
                    parent=root):
                entry.focus()
                return
        elif chk["level"] == "warn":
            if not messagebox.askyesno("Limit reached", chk["message"] + "\n\nSave this reading?",
                                       parent=root):
                entry.focus()
                return
        result["wear"] = value
        root.destroy()

    def on_cancel():
        if messagebox.askyesno(
                "Cancel session?",
                "The wear reading is required.\n\nCancelling now discards the 3 photos and "
                "nothing is saved. Cancel this session?", parent=root):
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    entry.bind("<Return>", on_save)

    btns = tk.Frame(root, bg="#F8FAFC", padx=24, pady=12)
    btns.pack(fill="x")
    tk.Button(btns, text="💾  Save Reading", command=on_save,
              bg=header_color, fg="white", font=("Calibri", 12, "bold"),
              relief="flat", padx=20, pady=8, cursor="hand2").pack(side="left")
    tk.Button(btns, text="Cancel Session", command=on_cancel,
              bg="#E2E8F0", fg="#1E293B", font=("Calibri", 11),
              relief="flat", padx=16, pady=8, cursor="hand2").pack(side="right")

    root.mainloop()
    return result["wear"]
