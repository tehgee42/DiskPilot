"""Right panel -- Organize Drives: assign purposes and find misplaced files."""

import shutil
import threading
import os

import customtkinter as ctk

from theme import (
    COLORS, TIER_META, FONT_HEADER, FONT_SUBHEADER, FONT_BODY,
    FONT_SMALL, FONT_TINY,
)
from scanner import get_available_drives, get_volume_label
from database import get_drive_purposes, save_drive_purpose, get_scan_info
from organizer import (
    suggest_drive_purposes, find_misplaced_files, find_best_destination,
    PURPOSE_TEMPLATES,
)
from analyzer import format_size


# ---------------------------------------------------------------------------
# Purpose option list (display name -> key mapping)
# ---------------------------------------------------------------------------

_PURPOSE_OPTIONS = ["System", "Games", "Projects", "Documents",
                    "Media", "Archive", "Downloads", "VMs"]

_PURPOSE_DISPLAY_TO_KEY = {name: name.lower() for name in _PURPOSE_OPTIONS}
_PURPOSE_KEY_TO_DISPLAY = {v: k for k, v in _PURPOSE_DISPLAY_TO_KEY.items()}


# ---------------------------------------------------------------------------
# Drive data helper
# ---------------------------------------------------------------------------

def _collect_drives():
    """
    Build a list of dicts describing each accessible drive, merging live
    disk-usage data with any previously saved purpose from the database.
    """
    letters = get_available_drives()

    # Existing purposes keyed by drive letter
    purposes_map = {}
    try:
        for row in get_drive_purposes():
            purposes_map[row["drive"]] = row
    except Exception:
        pass

    drives = []
    for letter in letters:
        try:
            usage = shutil.disk_usage(f"{letter}:\\")
        except (OSError, PermissionError):
            continue

        label = ""
        try:
            label = get_volume_label(letter)
        except Exception:
            pass

        purpose = ""
        db_row = purposes_map.get(letter)
        if db_row:
            purpose = db_row["purpose"] or ""
            if not label:
                label = db_row["label"] or ""

        drives.append({
            "drive": letter,
            "label": label,
            "total_bytes": usage.total,
            "free_bytes": usage.free,
            "purpose": purpose,
        })

    return drives


# ---------------------------------------------------------------------------
# Card builder
# ---------------------------------------------------------------------------

def _build_drive_card(scroll_frame, drive_info, idx):
    """
    Create a single drive-purpose card inside *scroll_frame*.

    Returns a dict: {"frame": CTkFrame, "combo": CTkComboBox, "drive": str}
    """
    bg = COLORS["bg_card"] if idx % 2 == 0 else COLORS["bg_card_alt"]

    card = ctk.CTkFrame(
        scroll_frame,
        fg_color=bg,
        corner_radius=8,
        border_width=1,
        border_color=COLORS["border"],
    )
    card.pack(fill="x", padx=6, pady=(0, 6))

    inner = ctk.CTkFrame(card, fg_color="transparent")
    inner.pack(fill="both", expand=True, padx=10, pady=8)

    # -- Row 1: drive letter + volume label --
    display_label = drive_info["label"] if drive_info["label"] else "Local Disk"
    header_text = f"{drive_info['drive']}: \u2014 {display_label}"

    lbl_name = ctk.CTkLabel(
        inner, text=header_text,
        font=FONT_SUBHEADER, text_color=COLORS["text"],
        anchor="w",
    )
    lbl_name.pack(fill="x")

    # -- Row 2: size summary (tiny, dim) --
    total = drive_info["total_bytes"]
    free = drive_info["free_bytes"]
    size_text = f"{format_size(total)} total \u00b7 {format_size(free)} free"

    ctk.CTkLabel(
        inner, text=size_text,
        font=FONT_TINY, text_color=COLORS["text_dark"],
        anchor="w",
    ).pack(fill="x", pady=(0, 4))

    # -- Row 3: purpose combo box --
    current_purpose = drive_info.get("purpose", "")
    default_value = _PURPOSE_KEY_TO_DISPLAY.get(current_purpose, "")

    combo = ctk.CTkComboBox(
        inner,
        values=_PURPOSE_OPTIONS,
        width=200,
        height=28,
        font=FONT_SMALL,
        dropdown_font=FONT_SMALL,
        fg_color=COLORS["bg_dark"],
        border_color=COLORS["border"],
        button_color=COLORS["border"],
        button_hover_color=COLORS["bg_card_alt"],
        text_color=COLORS["text"],
        dropdown_fg_color=COLORS["bg_card"],
        dropdown_text_color=COLORS["text"],
        dropdown_hover_color=COLORS["bg_card_alt"],
    )
    if default_value:
        combo.set(default_value)
    else:
        combo.set("")
    combo.pack(fill="x")

    return {
        "frame": card,
        "combo": combo,
        "drive": drive_info["drive"],
        "label": drive_info["label"],
        "total_bytes": drive_info["total_bytes"],
        "free_bytes": drive_info["free_bytes"],
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_right_panel(parent, app):
    """
    Populate *parent* (a 300 px wide CTkFrame) with the Organize panel:
    drive purpose assignment cards, auto-suggest, save, and misplaced-file
    finder.

    Returns ``{"refresh": <callable>}``.
    """

    # ── Header ───────────────────────────────────────────────────────────────
    ctk.CTkLabel(
        parent, text="Organize Drives",
        font=FONT_SUBHEADER, text_color=COLORS["text"],
        anchor="w",
    ).pack(fill="x", padx=14, pady=(14, 0))

    # ── Description ──────────────────────────────────────────────────────────
    ctk.CTkLabel(
        parent,
        text="Assign a purpose to each drive, then find files that belong elsewhere.",
        font=FONT_SMALL, text_color=COLORS["text_dim"],
        anchor="w", wraplength=270, justify="left",
    ).pack(fill="x", padx=14, pady=(4, 8))

    # ── Scrollable card area ─────────────────────────────────────────────────
    scroll = ctk.CTkScrollableFrame(
        parent,
        fg_color="transparent",
        scrollbar_button_color=COLORS["border"],
        scrollbar_button_hover_color=COLORS["bg_card_alt"],
    )
    scroll.pack(fill="both", expand=True, padx=0, pady=0)

    # Mutable state shared with closures
    state = {
        "cards": [],       # list of dicts from _build_drive_card
        "scroll": scroll,
        "running": False,  # guard against concurrent misplaced scans
    }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_combo_values():
        """Return a list of (drive_letter, purpose_key) from current combo boxes."""
        results = []
        for card in state["cards"]:
            display = card["combo"].get()
            key = _PURPOSE_DISPLAY_TO_KEY.get(display, "")
            results.append((card["drive"], key))
        return results

    def _rebuild_cards():
        """Destroy all existing cards and rebuild from live drive data."""
        for c in state["cards"]:
            try:
                c["frame"].destroy()
            except Exception:
                pass
        state["cards"] = []

        drives = _collect_drives()
        for idx, drv in enumerate(drives):
            card = _build_drive_card(state["scroll"], drv, idx)
            state["cards"].append(card)

    # ------------------------------------------------------------------
    # Auto-Suggest callback
    # ------------------------------------------------------------------

    def _on_auto_suggest():
        drives_info = []
        for card in state["cards"]:
            drives_info.append({
                "drive": card["drive"],
                "label": card["label"],
                "total_bytes": card["total_bytes"],
                "free_bytes": card["free_bytes"],
            })

        try:
            suggestions = suggest_drive_purposes(drives_info)
        except Exception:
            return

        for card in state["cards"]:
            suggested_key = suggestions.get(card["drive"], "")
            display = _PURPOSE_KEY_TO_DISPLAY.get(suggested_key, "")
            if display:
                card["combo"].set(display)

    # ------------------------------------------------------------------
    # Save Purposes callback
    # ------------------------------------------------------------------

    def _on_save_purposes():
        for card in state["cards"]:
            display = card["combo"].get()
            key = _PURPOSE_DISPLAY_TO_KEY.get(display, "")
            try:
                save_drive_purpose(
                    card["drive"],
                    card["label"],
                    key,
                    card["total_bytes"],
                    card["free_bytes"],
                )
            except Exception:
                pass

        # Refresh the left panel so purpose labels update there too
        try:
            app.refresh_drives()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Find Misplaced Files callback (background thread)
    # ------------------------------------------------------------------

    def _on_find_misplaced():
        if state["running"]:
            return
        state["running"] = True

        misplaced_btn.configure(state="disabled", text="Scanning\u2026")
        status_label.configure(text="Searching for misplaced files\u2026")

        def _worker():
            results = []
            total_size = 0

            # Save current combo state first so the DB is up-to-date
            _on_save_purposes()

            # Re-read purposes from DB for destination lookups
            try:
                all_purposes = get_drive_purposes()
            except Exception:
                all_purposes = []

            for card in state["cards"]:
                display = card["combo"].get()
                purpose_key = _PURPOSE_DISPLAY_TO_KEY.get(display, "")
                if not purpose_key:
                    continue

                purpose_name = PURPOSE_TEMPLATES.get(purpose_key, {}).get("name", display)
                drive_letter = card["drive"]

                try:
                    rows = find_misplaced_files(drive_letter, purpose_key, limit=200)
                except Exception:
                    continue

                for row in rows:
                    file_category = row["category"]
                    dest_drive = find_best_destination(file_category, all_purposes)
                    if dest_drive and dest_drive != drive_letter:
                        dest_label = f"{dest_drive}:"
                    else:
                        dest_label = "another"

                    reason = (
                        f"{row['category']} file on {purpose_name} drive "
                        f"\u2192 belongs on {dest_label} drive"
                    )

                    results.append({
                        "path": row["path"],
                        "filename": row["filename"],
                        "size": row["size"],
                        "drive": drive_letter,
                        "category": row["category"],
                        "accessed_at": row["accessed_at"] if row["accessed_at"] else "",
                        "tier": "MISPLACED",
                        "reason": reason,
                        "auto_check": False,
                        "extension": "",
                    })
                    total_size += row["size"]

            # Schedule GUI update on main thread
            count = len(results)
            size_str = format_size(total_size)

            def _update_gui():
                state["running"] = False
                misplaced_btn.configure(state="normal", text="Find Misplaced Files")

                if count > 0:
                    status_label.configure(
                        text=f"Found {count} misplaced file{'s' if count != 1 else ''} ({size_str})"
                    )
                    # Inject into center panel
                    try:
                        center = app.get_center()
                        if center and "inject_results" in center:
                            center["inject_results"](results)
                    except Exception:
                        pass
                else:
                    status_label.configure(text="No misplaced files found.")

            try:
                parent.after(0, _update_gui)
            except Exception:
                pass

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Button row: Auto-Suggest + Save Purposes
    # ------------------------------------------------------------------

    btn_row = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row.pack(fill="x", padx=10, pady=(6, 4))

    ctk.CTkButton(
        btn_row,
        text="Auto-Suggest",
        width=130,
        height=30,
        font=FONT_SMALL,
        fg_color=COLORS["border"],
        hover_color=COLORS["bg_card_alt"],
        text_color=COLORS["text"],
        corner_radius=6,
        command=_on_auto_suggest,
    ).pack(side="left", padx=(0, 4))

    ctk.CTkButton(
        btn_row,
        text="Save Purposes",
        width=130,
        height=30,
        font=FONT_SMALL,
        fg_color=COLORS["accent"],
        hover_color=COLORS["accent_hover"] if "accent_hover" in COLORS else "#d63851",
        text_color=COLORS["text"],
        corner_radius=6,
        command=_on_save_purposes,
    ).pack(side="right")

    # ------------------------------------------------------------------
    # Separator
    # ------------------------------------------------------------------

    ctk.CTkFrame(
        parent, fg_color=COLORS["border"], height=1,
    ).pack(fill="x", padx=10, pady=(8, 8))

    # ------------------------------------------------------------------
    # Find Misplaced Files button + status label
    # ------------------------------------------------------------------

    misplaced_btn = ctk.CTkButton(
        parent,
        text="Find Misplaced Files",
        width=270,
        height=34,
        font=FONT_BODY,
        fg_color=COLORS["misplaced"],
        hover_color="#5a4bd5",
        text_color=COLORS["text"],
        corner_radius=6,
        command=_on_find_misplaced,
    )
    misplaced_btn.pack(padx=14, pady=(0, 4))

    status_label = ctk.CTkLabel(
        parent, text="",
        font=FONT_TINY, text_color=COLORS["text_dim"],
        anchor="w", wraplength=270, justify="left",
    )
    status_label.pack(fill="x", padx=14, pady=(0, 10))

    # ------------------------------------------------------------------
    # refresh() -- re-read drive purposes and update combo boxes
    # ------------------------------------------------------------------

    def refresh():
        _rebuild_cards()

    # Initial population
    try:
        _rebuild_cards()
    except Exception:
        pass

    return {"refresh": refresh}
