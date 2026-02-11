"""Center panel — the entire DiskPilot UI. Clean single-screen layout."""

import threading
import customtkinter as ctk

from theme import COLORS, TIER_META
from analyzer import format_size
from widgets import FileListWidget, TierCard, ToastWidget

from database import get_scan_info
from scanner import get_available_drives, scan_drive
from smart_analyzer import smart_scan, smart_scan_summary, SAFE, RECOMMENDED, SUGGESTED, ASK
from organizer import queue_file_delete, execute_deletes


def _bg_thread(parent, func, on_done):
    """Run func() in background, post on_done(result) to GUI thread."""
    def worker():
        try:
            result = func()
        except Exception as exc:
            result = exc
        try:
            parent.after(0, lambda: on_done(result))
        except Exception:
            pass
    threading.Thread(target=worker, daemon=True).start()


def build_center_panel(parent, app):
    """Build the full DiskPilot UI inside parent. Returns context dict."""

    state = {"results": [], "scanning": False}

    # ══════════════════════════════════════════════════════════════════
    # TOP BAR — app name, status, scan button
    # ══════════════════════════════════════════════════════════════════
    top_bar = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], height=56, corner_radius=0)
    top_bar.pack(fill="x")
    top_bar.pack_propagate(False)

    ctk.CTkLabel(top_bar, text="DiskPilot", font=("Segoe UI", 20, "bold"),
                  text_color=COLORS["text"]).pack(side="left", padx=16)

    status_label = ctk.CTkLabel(top_bar, text="", font=("Segoe UI", 13),
                                 text_color=COLORS["text_dim"])
    status_label.pack(side="left", padx=16)

    rescan_btn = ctk.CTkButton(
        top_bar, text="Re-scan All Drives", width=170, height=36,
        fg_color=COLORS["border"], hover_color=COLORS["bg_card_alt"],
        text_color=COLORS["text"], font=("Segoe UI", 13), corner_radius=6,
    )
    rescan_btn.pack(side="right", padx=16, pady=8)

    organize_btn = ctk.CTkButton(
        top_bar, text="Organize Drives", width=160, height=36,
        fg_color=COLORS["misplaced"], hover_color="#5a4bd5",
        text_color="#ffffff", font=("Segoe UI", 13), corner_radius=6,
    )
    organize_btn.pack(side="right", padx=(0, 8), pady=8)

    # ══════════════════════════════════════════════════════════════════
    # TIER SUMMARY — 4 cards in a row
    # ══════════════════════════════════════════════════════════════════
    tier_frame = ctk.CTkFrame(parent, fg_color="transparent", height=82)
    tier_frame.pack(fill="x", padx=16, pady=(10, 6))
    tier_frame.pack_propagate(False)
    tier_frame.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="t")
    tier_frame.grid_rowconfigure(0, weight=1)

    tier_cards = {}
    for i, tier in enumerate([SAFE, RECOMMENDED, SUGGESTED, ASK]):
        card = TierCard(tier_frame, tier, on_click=lambda t: _filter_tier(t))
        card.grid(row=0, column=i, sticky="nsew", padx=4)
        tier_cards[tier] = card

    # ══════════════════════════════════════════════════════════════════
    # SEARCH + FILTER (single row, always visible, compact)
    # ══════════════════════════════════════════════════════════════════
    filter_bar = ctk.CTkFrame(parent, fg_color="transparent", height=44)
    filter_bar.pack(fill="x", padx=16, pady=(0, 6))
    filter_bar.pack_propagate(False)

    search_entry = ctk.CTkEntry(
        filter_bar, placeholder_text="Search files...", width=280, height=36,
        font=("Segoe UI", 13), fg_color=COLORS["bg_card"],
        border_color=COLORS["border"], text_color=COLORS["text"],
    )
    search_entry.pack(side="left", padx=(0, 12))

    tier_combo = ctk.CTkComboBox(
        filter_bar, values=["ALL", "SAFE", "RECOMMENDED", "SUGGESTED", "ASK"],
        width=170, height=36, font=("Segoe UI", 13),
        fg_color=COLORS["bg_card"], border_color=COLORS["border"],
        text_color=COLORS["text"], dropdown_fg_color=COLORS["bg_card"],
        dropdown_text_color=COLORS["text"], dropdown_hover_color=COLORS["bg_card_alt"],
        button_color=COLORS["border"], button_hover_color=COLORS["accent"],
    )
    tier_combo.set("ALL")
    tier_combo.pack(side="left", padx=(0, 12))

    # Quick-select buttons
    ctk.CTkButton(
        filter_bar, text="Check Safe", width=110, height=34,
        fg_color=COLORS["border"], hover_color=COLORS["bg_card_alt"],
        text_color=COLORS["text"], font=("Segoe UI", 13), corner_radius=4,
        command=lambda: (file_list.check_by_tier({SAFE}), _update_bar()),
    ).pack(side="left", padx=(0, 6))

    ctk.CTkButton(
        filter_bar, text="Safe + Rec", width=110, height=34,
        fg_color=COLORS["border"], hover_color=COLORS["bg_card_alt"],
        text_color=COLORS["text"], font=("Segoe UI", 13), corner_radius=4,
        command=lambda: (file_list.check_by_tier({SAFE, RECOMMENDED}), _update_bar()),
    ).pack(side="left", padx=(0, 6))

    ctk.CTkButton(
        filter_bar, text="Uncheck All", width=110, height=34,
        fg_color=COLORS["border"], hover_color=COLORS["bg_card_alt"],
        text_color=COLORS["text"], font=("Segoe UI", 13), corner_radius=4,
        command=lambda: (file_list.uncheck_all(), _update_bar()),
    ).pack(side="left")

    # ══════════════════════════════════════════════════════════════════
    # PROGRESS BAR (hidden by default)
    # ══════════════════════════════════════════════════════════════════
    progress_frame = ctk.CTkFrame(parent, fg_color="transparent", height=24)
    progress_bar = ctk.CTkProgressBar(
        progress_frame, height=4, fg_color=COLORS["border"],
        progress_color=COLORS["accent"], mode="indeterminate",
    )
    progress_bar.pack(fill="x", padx=16, pady=4)

    # ══════════════════════════════════════════════════════════════════
    # FILE LIST — ttk.Treeview, fills all remaining space
    # ══════════════════════════════════════════════════════════════════
    file_list = FileListWidget(parent)
    file_list.pack(fill="both", expand=True, padx=16, pady=(0, 6))

    # ══════════════════════════════════════════════════════════════════
    # BOTTOM BAR — selection info + clean button
    # ══════════════════════════════════════════════════════════════════
    bottom = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], height=58, corner_radius=0)
    bottom.pack(fill="x", side="bottom")
    bottom.pack_propagate(False)

    sel_label = ctk.CTkLabel(bottom, text="Selected: 0 files (0 B)",
                              font=("Segoe UI", 13), text_color=COLORS["text_dim"])
    sel_label.pack(side="left", padx=16, pady=8)

    recycle_var = ctk.BooleanVar(value=True)
    ctk.CTkSwitch(
        bottom, text="Recycle Bin", variable=recycle_var,
        font=("Segoe UI", 13), text_color=COLORS["text_dim"],
        fg_color=COLORS["border"], progress_color=COLORS["accent"],
        button_color=COLORS["text"], button_hover_color=COLORS["accent_hover"],
    ).pack(side="right", padx=(8, 16), pady=8)

    clean_btn = ctk.CTkButton(
        bottom, text="Clean 0 B", width=180, height=40,
        fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        text_color="#ffffff", font=("Segoe UI", 14, "bold"), corner_radius=6,
    )
    clean_btn.pack(side="right", padx=8, pady=8)

    # ══════════════════════════════════════════════════════════════════
    # LOGIC
    # ══════════════════════════════════════════════════════════════════

    def _update_bar():
        checked = file_list.get_checked()
        size = file_list.get_total_checked_size()
        sel_label.configure(text=f"Selected: {len(checked)} files ({format_size(size)})")
        clean_btn.configure(text=f"Clean {format_size(size)}")

    file_list.set_on_change(_update_bar)

    def _filter_tier(tier):
        tier_combo.set(tier)
        _apply_filters()

    def _apply_filters(*_):
        file_list.apply_filter(search_text=search_entry.get(), tier_filter=tier_combo.get())
        _update_bar()

    tier_combo.configure(command=_apply_filters)
    search_entry.bind("<KeyRelease>", _apply_filters)

    def _show_progress(msg="Scanning..."):
        status_label.configure(text=msg)
        progress_frame.pack(fill="x", before=file_list)
        progress_bar.start()

    def _hide_progress():
        progress_bar.stop()
        progress_frame.pack_forget()

    def _display_results(results):
        if isinstance(results, Exception):
            status_label.configure(text=f"Error: {results}")
            _hide_progress()
            return
        state["results"] = results
        state["scanning"] = False
        _hide_progress()

        summary = smart_scan_summary(results)
        for tier, card in tier_cards.items():
            info = summary.get(tier, {"count": 0, "total_size": 0, "auto_checked": 0})
            card.update_stats(info["count"], info["total_size"], info["auto_checked"])

        file_list.populate(results)
        _update_bar()
        n = len(results)
        total = sum(r.get("size", 0) for r in results)
        status_label.configure(text=f"{n} items found · {format_size(total)} total")
        rescan_btn.configure(state="normal")

    def _scan_all_and_analyze():
        if state["scanning"]:
            return
        state["scanning"] = True
        rescan_btn.configure(state="disabled")
        file_list.clear()
        _update_bar()
        _show_progress("Scanning drives...")
        for card in tier_cards.values():
            card.update_stats(0, 0, 0)

        def do_work():
            drives = get_available_drives()
            for i, letter in enumerate(drives):
                def _progress(files_scanned, current_path, l=letter, n=i+1, t=len(drives)):
                    short = current_path
                    if len(short) > 60:
                        short = "..." + short[-57:]
                    try:
                        parent.after(0, lambda: status_label.configure(
                            text=f"Scanning {l}: ({n}/{t}) \u2014 {files_scanned:,} files"))
                    except Exception:
                        pass
                try:
                    parent.after(0, lambda l=letter, n=i+1, t=len(drives):
                        status_label.configure(text=f"Scanning {l}: ({n}/{t})..."))
                except Exception:
                    pass
                scan_drive(letter, progress_callback=_progress)
            try:
                parent.after(0, lambda: status_label.configure(text="Analyzing..."))
            except Exception:
                pass
            return smart_scan()

        _bg_thread(parent, do_work, _display_results)

    def _run_smart_scan():
        _show_progress("Analyzing...")
        _bg_thread(parent, smart_scan, _display_results)

    rescan_btn.configure(command=_scan_all_and_analyze)

    # ── Clean logic ──

    def _clean():
        checked = file_list.get_checked()
        if not checked:
            ToastWidget.show(parent, "No files selected.", color=COLORS["ask"])
            return

        total_size = sum(f.get("size", 0) for f in checked)
        count = len(checked)
        use_recycle = recycle_var.get()

        # Confirmation dialog
        dialog = ctk.CTkToplevel(parent)
        dialog.title("Confirm")
        dialog.geometry("400x180")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.attributes("-topmost", True)
        dialog.grab_set()
        dialog.transient(parent.winfo_toplevel())
        dialog.update_idletasks()
        x = parent.winfo_toplevel().winfo_x() + parent.winfo_toplevel().winfo_width() // 2 - 200
        y = parent.winfo_toplevel().winfo_y() + parent.winfo_toplevel().winfo_height() // 2 - 90
        dialog.geometry(f"+{x}+{y}")

        mode = "Recycle Bin" if use_recycle else "PERMANENTLY"
        ctk.CTkLabel(dialog, text=f"Delete {count} files ({format_size(total_size)})?",
                      font=("Segoe UI", 16, "bold"), text_color=COLORS["text"]
                      ).pack(pady=(24, 4))
        ctk.CTkLabel(dialog, text=f"Files will be sent to {mode}.",
                      font=("Segoe UI", 13), text_color=COLORS["text_dim"]
                      ).pack(pady=(0, 16))

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack()
        ctk.CTkButton(btn_row, text="Cancel", width=120, height=38,
                       fg_color=COLORS["border"], hover_color=COLORS["bg_card_alt"],
                       text_color=COLORS["text"], font=("Segoe UI", 13),
                       command=dialog.destroy).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text=f"Clean {format_size(total_size)}", width=160, height=38,
                       fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                       text_color="#ffffff", font=("Segoe UI", 14, "bold"),
                       command=lambda: (dialog.destroy(), _execute_clean(checked, use_recycle))
                       ).pack(side="left", padx=8)

    def _execute_clean(checked_files, use_recycle):
        clean_btn.configure(state="disabled", text="Cleaning...")
        paths = set()

        def do_clean():
            for f in checked_files:
                queue_file_delete(f["path"], f["size"], f.get("reason", ""))
                paths.add(f["path"])
            return execute_deletes(use_recycle=use_recycle)

        def on_done(results):
            if isinstance(results, Exception):
                ToastWidget.show(parent, f"Error: {results}", color=COLORS["ask"])
                clean_btn.configure(state="normal")
                _update_bar()
                return
            deleted = sum(1 for _, _, s in results if s == "deleted")
            freed = sum(sz for _, sz, s in results if s == "deleted")
            file_list.remove_paths(paths)
            clean_btn.configure(state="normal")
            _update_bar()
            # Update tier cards
            summary = smart_scan_summary(file_list._results)
            for tier, card in tier_cards.items():
                info = summary.get(tier, {"count": 0, "total_size": 0, "auto_checked": 0})
                card.update_stats(info["count"], info["total_size"])
            ToastWidget.show(parent, f"Freed {format_size(freed)} ({deleted} files)")

        _bg_thread(parent, do_clean, on_done)

    clean_btn.configure(command=_clean)

    # ── inject_results (for organize panel) ──
    def _inject(results):
        if not results:
            return
        state["results"].extend(results)
        file_list.populate(state["results"])
        summary = smart_scan_summary(state["results"])
        for tier, card in tier_cards.items():
            info = summary.get(tier, {"count": 0, "total_size": 0, "auto_checked": 0})
            card.update_stats(info["count"], info["total_size"])
        _update_bar()

    # ── Organize dialog ──
    def _open_organize():
        from panel_right import build_right_panel
        dialog = ctk.CTkToplevel(parent)
        dialog.title("Organize Drives")
        dialog.geometry("420x560")
        dialog.resizable(False, True)
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.attributes("-topmost", True)
        dialog.grab_set()
        dialog.transient(parent.winfo_toplevel())
        dialog.update_idletasks()
        x = parent.winfo_toplevel().winfo_x() + parent.winfo_toplevel().winfo_width() // 2 - 210
        y = parent.winfo_toplevel().winfo_y() + parent.winfo_toplevel().winfo_height() // 2 - 280
        dialog.geometry(f"+{x}+{y}")
        build_right_panel(dialog, app)

    organize_btn.configure(command=_open_organize)

    # ── Auto-launch: check for existing data or scan ──
    def _auto_start():
        def check():
            return get_scan_info()
        def on_check(rows):
            if isinstance(rows, Exception) or not rows:
                _scan_all_and_analyze()
            else:
                status_label.configure(text="Loading results...")
                _run_smart_scan()
        _bg_thread(parent, check, on_check)

    parent.after(200, _auto_start)

    return {
        "refresh": lambda: _run_smart_scan(),
        "start_scan": _scan_all_and_analyze,
        "inject_results": _inject,
    }
