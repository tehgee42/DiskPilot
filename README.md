# DiskPilot

A Windows disk cleanup and organization tool. Scans all drives, intelligently categorizes files into confidence tiers, and lets you clean up junk with a single click.

![Windows](https://img.shields.io/badge/platform-Windows-blue) ![Python](https://img.shields.io/badge/python-3.10+-green) ![License](https://img.shields.io/badge/license-MIT-orange)

## Features

- **Smart scanning** - Walks all connected drives and catalogs every file into a SQLite database
- **4-tier confidence system** - Files are sorted into SAFE / RECOMMENDED / SUGGESTED / ASK based on what they are and how stale they are
- **Developer-friendly** - Automatically skips `node_modules`, `.venv`, `__pycache__`, `.gradle`, `.cargo`, and 30+ other dev directories
- **Piracy detection** - Flags known cracks, keygens, and activators as security risks
- **Duplicate finder** - Detects duplicate files across drives and suggests keeping the newest copy
- **Version detection** - Finds older versions of the same installer and flags them
- **Drive organization** - Assign purposes to drives (Games, Projects, Media, etc.) and find misplaced files
- **3-layer system protection** - System files are excluded at scan, analysis, and deletion layers
- **Recycle bin support** - Defaults to recycle bin so nothing is permanently lost
- **Dark modern UI** - Built with CustomTkinter + ttk.Treeview for a responsive dark interface

## Screenshots

The main interface shows all flagged files with tier, reason, path, and size. Filter by tier, search, and bulk-select with one click.

## Installation

### From installer (recommended)

Download `DiskPilot_Setup.exe` from [Releases](../../releases) and run it.

### From source

```bash
git clone https://github.com/yourusername/DiskPilot.git
cd DiskPilot
pip install customtkinter pillow
python app.py
```

### Build the .exe yourself

```bash
pip install pyinstaller
python build.py
# Output: dist/DiskPilot.exe
```

## Architecture

```
app.py              - Main window, ttk dark theme setup
panel_center.py     - Full UI layout (top bar, tier cards, filters, file list, bottom bar)
widgets.py          - FileListWidget (ttk.Treeview), TierCard, ToastWidget
panel_right.py      - Organize drives dialog (assign purposes, find misplaced files)
scanner.py          - File system walker, categorizer, system protection
smart_analyzer.py   - 4-tier confidence engine, duplicate/version/piracy detection
analyzer.py         - Aggregate queries, format helpers
organizer.py        - Delete queue, recycle bin support, drive purpose templates
database.py         - SQLite with WAL mode, batch inserts
theme.py            - Color palette, font constants
build.py            - PyInstaller build script
installer.iss       - Inno Setup installer script
```

## How it works

1. **Scan** - Walks every drive (skipping system dirs and dev folders), catalogs file metadata into SQLite
2. **Analyze** - Queries the database to find junk, old installers, duplicates, stale files, and piracy artifacts
3. **Tier** - Each file gets a confidence tier and a human-readable reason explaining why it was flagged
4. **Clean** - Select files (or use quick-select buttons), hit Clean, files go to recycle bin

## Confidence tiers

| Tier | What it means | Examples |
|------|---------------|----------|
| **SAFE** | Definitely deletable | Temp files, cache, logs |
| **RECOMMENDED** | Very likely safe | Old installers, torrents, duplicates |
| **SUGGESTED** | Probably fine, worth a glance | Stale archives, old backups |
| **ASK** | Only you know | Old media, abandoned projects |

## Developer directory skip list

The scanner automatically skips these directories to avoid indexing dev dependencies:

`node_modules`, `__pycache__`, `.venv`, `venv`, `.env`, `.next`, `.nuxt`, `.cache`, `.npm`, `.yarn`, `.gradle`, `.cargo`, `.m2`, `.tox`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.parcel-cache`, `.turbo`, `.angular`, `.svelte-kit`, `.expo`, `bower_components`, `.sass-cache`, `coverage`, `.nyc_output`, `.idea`, `.vs`, `vendor`, `target`

## System protection

Files are protected at three layers:

1. **Scanner** - System files (`pagefile.sys`, `ntuser.dat`, etc.) are categorized as `system_protected` and system directories (`Windows`, `Program Files`, etc.) are skipped entirely
2. **Analyzer** - All queries exclude `system_protected` category
3. **Organizer** - Delete execution refuses to touch any path containing system path fragments

## Requirements

- Windows 10/11
- Python 3.10+ (if running from source)
- ~50 MB disk space for the database (varies by number of files)

## License

MIT License. See [LICENSE](LICENSE) for details.
