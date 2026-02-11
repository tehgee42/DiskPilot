"""DiskPilot — Scan, Clean & Organize your drives."""
import sys
import os
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk
import database as db
from theme import COLORS, APP_NAME

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class DiskPilotApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        db.init_db()

        self.title(APP_NAME)
        self.geometry("1200x800")
        self.minsize(900, 600)
        self.configure(fg_color=COLORS["bg_dark"])

        # App icon
        icon_path = os.path.join(os.path.dirname(__file__), "diskpilot.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)

        # Style the ttk.Treeview for dark theme
        self._setup_treeview_style()

        # Single full-width panel
        from panel_center import build_center_panel
        self.center_ctx = build_center_panel(self, self)

    def _setup_treeview_style(self):
        """Dark theme for ttk.Treeview — the only ttk widget we use."""
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("Dark.Treeview",
            background=COLORS["bg_card"],
            foreground=COLORS["text"],
            fieldbackground=COLORS["bg_card"],
            borderwidth=0,
            font=("Segoe UI", 13),
            rowheight=34,
        )
        style.configure("Dark.Treeview.Heading",
            background=COLORS["bg_dark"],
            foreground=COLORS["text_dim"],
            borderwidth=0,
            font=("Segoe UI", 13, "bold"),
            relief="flat",
        )
        style.map("Dark.Treeview",
            background=[("selected", COLORS["border"])],
            foreground=[("selected", "#ffffff")],
        )
        style.map("Dark.Treeview.Heading",
            background=[("active", COLORS["bg_card_alt"])],
        )

        # Scrollbar
        style.configure("Dark.Vertical.TScrollbar",
            background=COLORS["bg_card"],
            troughcolor=COLORS["bg_dark"],
            arrowcolor=COLORS["text_dim"],
            borderwidth=0,
        )

    def refresh_drives(self):
        """Called after clean — no-op in simplified layout."""
        pass

    def get_center(self):
        return getattr(self, "center_ctx", {})


def main():
    app = DiskPilotApp()
    app.mainloop()


if __name__ == "__main__":
    main()
