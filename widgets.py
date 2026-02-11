"""DiskPilot widgets — fast file list using ttk.Treeview, tier cards, toast."""

import os
import subprocess
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
from theme import COLORS, TIER_META
from analyzer import format_size

# Tier display info
TIER_COLORS = {
    "SAFE":        "#00b894",
    "RECOMMENDED": "#0984e3",
    "SUGGESTED":   "#fdcb6e",
    "ASK":         "#d63031",
    "MISPLACED":   "#6c5ce7",
}


# ═══════════════════════════════════════════════════════════════════════════════
# FileListWidget — ttk.Treeview based, handles 1000+ rows with zero lag
# ═══════════════════════════════════════════════════════════════════════════════

class FileListWidget(ctk.CTkFrame):
    """Fast scrollable file list using ttk.Treeview under the hood."""

    CHECK = "\u2611"    # ☑
    UNCHECK = "\u2610"  # ☐

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", corner_radius=0, **kwargs)

        self._data = {}          # iid -> result dict
        self._checked = set()    # set of checked iids
        self._all_results = []   # full unfiltered results (never overwritten by filter)
        self._results = []       # currently displayed results
        self._on_change_cb = None

        # Treeview with columns
        cols = ("check", "tier", "reason", "path", "size")
        self.tree = ttk.Treeview(
            self, columns=cols, show="headings",
            style="Dark.Treeview", selectmode="browse",
        )

        # Column config
        self.tree.heading("check", text="")
        self.tree.heading("tier", text="Tier", command=lambda: self._sort("tier"))
        self.tree.heading("reason", text="Reason", command=lambda: self._sort("reason"))
        self.tree.heading("path", text="Path", command=lambda: self._sort("path"))
        self.tree.heading("size", text="Size", command=lambda: self._sort("size"))

        self.tree.column("check",  width=40,  minwidth=40,  stretch=False, anchor="center")
        self.tree.column("tier",   width=130, minwidth=100, stretch=False, anchor="w")
        self.tree.column("reason", width=300, minwidth=160, stretch=True,  anchor="w")
        self.tree.column("path",   width=400, minwidth=220, stretch=True,  anchor="w")
        self.tree.column("size",   width=100, minwidth=70,  stretch=False, anchor="e")

        # Tag colors for tiers
        self.tree.tag_configure("SAFE",        foreground=TIER_COLORS["SAFE"])
        self.tree.tag_configure("RECOMMENDED", foreground=TIER_COLORS["RECOMMENDED"])
        self.tree.tag_configure("SUGGESTED",   foreground=TIER_COLORS["SUGGESTED"])
        self.tree.tag_configure("ASK",         foreground=TIER_COLORS["ASK"])
        self.tree.tag_configure("MISPLACED",   foreground=TIER_COLORS["MISPLACED"])
        self.tree.tag_configure("alt",         background=COLORS["bg_card_alt"])

        # Scrollbar
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview,
                             style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Click on check column toggles
        self.tree.bind("<ButtonRelease-1>", self._on_click)
        # Right-click context menu
        self.tree.bind("<Button-3>", self._on_right_click)

        # Sort state
        self._sort_col = "tier"
        self._sort_rev = False

    # ── Public API ───────────────────────────────────────────────────

    def populate(self, results, _is_filter=False):
        """Fill the treeview from smart_scan results. Fast — no widget creation per row."""
        self.tree.delete(*self.tree.get_children())
        self._data.clear()
        self._checked.clear()
        if not _is_filter:
            self._all_results = list(results)
        self._results = list(results)

        for i, r in enumerate(results):
            tier = r.get("tier", "ASK")
            tier_label = TIER_META.get(tier, {}).get("label", tier)
            checked = r.get("auto_check", False)
            check_char = self.CHECK if checked else self.UNCHECK

            tags = (tier,)
            if i % 2 == 1:
                tags = (tier, "alt")

            iid = self.tree.insert("", "end", values=(
                check_char,
                tier_label,
                r.get("reason", ""),
                r.get("path", ""),
                format_size(r.get("size", 0)),
            ), tags=tags)

            self._data[iid] = r
            if checked:
                self._checked.add(iid)

        self._fire_change()

    def get_checked(self):
        """Return list of result dicts for checked rows."""
        return [self._data[iid] for iid in self._checked if iid in self._data]

    def get_total_checked_size(self):
        return sum(self._data[iid].get("size", 0) for iid in self._checked if iid in self._data)

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self._data.clear()
        self._checked.clear()
        self._all_results.clear()
        self._results.clear()
        self._fire_change()

    def check_all(self):
        for iid in self.tree.get_children():
            self._set_check(iid, True)
        self._fire_change()

    def uncheck_all(self):
        for iid in self.tree.get_children():
            self._set_check(iid, False)
        self._fire_change()

    def check_by_tier(self, tiers):
        """Uncheck all, then check only rows matching tiers set."""
        for iid in self.tree.get_children():
            data = self._data.get(iid)
            should_check = data and data.get("tier", "") in tiers
            self._set_check(iid, should_check)
        self._fire_change()

    def set_on_change(self, callback):
        self._on_change_cb = callback

    def apply_filter(self, search_text="", tier_filter="ALL"):
        """Re-populate with filtered subset of results."""
        search_lower = search_text.strip().lower()
        filtered = []
        for r in self._all_results:
            if tier_filter != "ALL" and r.get("tier", "") != tier_filter:
                continue
            if search_lower:
                haystack = (r.get("path", "") + r.get("reason", "")).lower()
                if search_lower not in haystack:
                    continue
            filtered.append(r)
        self.populate(filtered, _is_filter=True)

    def remove_paths(self, path_set):
        """Remove rows matching paths (after cleaning)."""
        self._all_results = [r for r in self._all_results if r.get("path", "") not in path_set]
        self.populate(self._all_results)

    # ── Internal ─────────────────────────────────────────────────────

    def _set_check(self, iid, checked):
        vals = list(self.tree.item(iid, "values"))
        if checked:
            vals[0] = self.CHECK
            self._checked.add(iid)
        else:
            vals[0] = self.UNCHECK
            self._checked.discard(iid)
        self.tree.item(iid, values=vals)

    def _on_click(self, event):
        col = self.tree.identify_column(event.x)
        if col != "#1":  # only toggle on check column
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self._set_check(iid, iid not in self._checked)
        self._fire_change()

    def _sort(self, col):
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False

        tier_order = {"SAFE": 0, "RECOMMENDED": 1, "SUGGESTED": 2, "ASK": 3, "MISPLACED": 4}
        items = list(self.tree.get_children())

        if col == "size":
            def key(iid):
                d = self._data.get(iid)
                return d.get("size", 0) if d else 0
        elif col == "tier":
            def key(iid):
                d = self._data.get(iid)
                return tier_order.get(d.get("tier", ""), 99) if d else 99
        else:
            col_idx = {"tier": 1, "reason": 2, "path": 3, "size": 4}.get(col, 3)
            def key(iid):
                return str(self.tree.item(iid, "values")[col_idx]).lower()

        items.sort(key=key, reverse=self._sort_rev)
        for i, iid in enumerate(items):
            self.tree.move(iid, "", i)

    def _on_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        data = self._data.get(iid)
        if not data:
            return

        menu = tk.Menu(self.tree, tearoff=0,
                       bg=COLORS["bg_card"], fg=COLORS["text"],
                       activebackground=COLORS["border"],
                       activeforeground="#ffffff",
                       font=("Segoe UI", 12))

        path = data.get("path", "")
        menu.add_command(label="Open File Location",
                         command=lambda: self._open_location(path))
        menu.add_command(label="Copy Path",
                         command=lambda: self._copy_path(path))
        menu.tk_popup(event.x_root, event.y_root)

    def _open_location(self, path):
        if os.path.exists(path):
            subprocess.run(["explorer", "/select,", path])
        else:
            parent = os.path.dirname(path)
            if os.path.isdir(parent):
                os.startfile(parent)

    def _copy_path(self, path):
        self.winfo_toplevel().clipboard_clear()
        self.winfo_toplevel().clipboard_append(path)

    def _fire_change(self):
        if self._on_change_cb:
            try:
                self._on_change_cb()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
# TierCard — compact summary card
# ═══════════════════════════════════════════════════════════════════════════════

class TierCard(ctk.CTkFrame):
    def __init__(self, master, tier_name, on_click=None, **kwargs):
        super().__init__(master, fg_color=COLORS["bg_card"], corner_radius=8,
                         height=76, **kwargs)
        self.pack_propagate(False)
        self._tier = tier_name
        meta = TIER_META.get(tier_name, {})
        color = meta.get("color", COLORS["text_dim"])

        # Color stripe
        ctk.CTkFrame(self, fg_color=color, width=4, corner_radius=0
                      ).pack(side="left", fill="y")

        text_frame = ctk.CTkFrame(self, fg_color="transparent")
        text_frame.pack(side="left", fill="both", expand=True, padx=(10, 8), pady=6)

        self._name = ctk.CTkLabel(text_frame, text=meta.get("label", tier_name),
                                   font=("Segoe UI", 14, "bold"), text_color=color, anchor="w")
        self._name.pack(anchor="w")

        self._stats = ctk.CTkLabel(text_frame, text="0 files · 0 B",
                                    font=("Segoe UI", 12), text_color=COLORS["text_dim"], anchor="w")
        self._stats.pack(anchor="w")

        if on_click:
            for w in [self, text_frame, self._name, self._stats]:
                w.bind("<Button-1>", lambda e, t=tier_name: on_click(t))
            self.bind("<Enter>", lambda e: self.configure(fg_color=COLORS["bg_card_alt"]))
            self.bind("<Leave>", lambda e: self.configure(fg_color=COLORS["bg_card"]))

    def update_stats(self, count, total_size, auto_checked=0):
        self._stats.configure(text=f"{count} files · {format_size(total_size)}")


# ═══════════════════════════════════════════════════════════════════════════════
# ToastWidget — notification bar
# ═══════════════════════════════════════════════════════════════════════════════

class ToastWidget:
    @classmethod
    def show(cls, parent, message, color=None):
        if color is None:
            color = COLORS["success"]
        toast = ctk.CTkFrame(parent, fg_color=color, corner_radius=8, height=40)
        toast.place(relx=0.5, y=8, anchor="n", relwidth=0.5)

        ctk.CTkLabel(toast, text=message, font=("Segoe UI", 14),
                      text_color="#ffffff").pack(side="left", padx=16, pady=8)
        ctk.CTkButton(toast, text="×", width=32, height=32,
                       fg_color="transparent", text_color="#ffffff",
                       font=("Segoe UI", 16), hover_color="transparent",
                       command=lambda: toast.destroy()
                       ).pack(side="right", padx=8)

        parent.after(5000, lambda: toast.destroy() if toast.winfo_exists() else None)
