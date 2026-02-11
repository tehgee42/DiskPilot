"""DiskPilot color theme and styling constants."""

COLORS = {
    "bg_dark":      "#1a1a2e",
    "bg_card":      "#16213e",
    "bg_card_alt":  "#1b2a4a",
    "border":       "#0f3460",
    "accent":       "#e94560",
    "accent_hover": "#d63851",
    "safe":         "#00b894",
    "recommended":  "#0984e3",
    "suggested":    "#fdcb6e",
    "ask":          "#d63031",
    "misplaced":    "#6c5ce7",
    "text":         "#ffffff",
    "text_dim":     "#a0a0b0",
    "text_dark":    "#6c7293",
    "bar_green":    "#00b894",
    "bar_yellow":   "#fdcb6e",
    "bar_orange":   "#e17055",
    "bar_red":      "#d63031",
    "success":      "#00b894",
}

TIER_META = {
    "SAFE":        {"color": COLORS["safe"],        "label": "Safe to Delete", "desc": "Caches, temp, junk — auto-regenerated"},
    "RECOMMENDED": {"color": COLORS["recommended"],  "label": "Recommended",    "desc": "Old installers, duplicates — re-downloadable"},
    "SUGGESTED":   {"color": COLORS["suggested"],    "label": "Review These",   "desc": "Stale files — probably fine, worth a glance"},
    "ASK":         {"color": COLORS["ask"],          "label": "Your Call",      "desc": "Media, projects — only you know"},
    "MISPLACED":   {"color": COLORS["misplaced"],    "label": "Misplaced",      "desc": "Files on the wrong drive"},
}

FONT_FAMILY = "Segoe UI"
FONT_HEADER = (FONT_FAMILY, 18, "bold")
FONT_SUBHEADER = (FONT_FAMILY, 14, "bold")
FONT_BODY = (FONT_FAMILY, 13)
FONT_SMALL = (FONT_FAMILY, 11)
FONT_TINY = (FONT_FAMILY, 10)
FONT_BIG = (FONT_FAMILY, 26, "bold")

APP_NAME = "DiskPilot"
APP_VERSION = "1.0.0"
