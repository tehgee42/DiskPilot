"""Drive organizer - assign purposes to drives and move files accordingly."""
import os
import shutil
from datetime import datetime

from database import (
    save_drive_purpose, get_drive_purposes, add_to_move_queue,
    add_to_delete_queue, get_delete_queue, get_move_queue,
    update_queue_status, clear_queue, query_all, delete_from_queue
)
from scanner import SYSTEM_PROTECTED_FILES, SYSTEM_PROTECTED_PATH_FRAGMENTS


def _is_protected(path):
    """Hard safety check — refuse to delete system-critical files."""
    fname = os.path.basename(path).lower()
    path_lower = path.lower()
    if fname in SYSTEM_PROTECTED_FILES:
        return True
    for frag in SYSTEM_PROTECTED_PATH_FRAGMENTS:
        if frag in path_lower:
            return True
    return False

# Predefined purpose templates
PURPOSE_TEMPLATES = {
    "system": {
        "name": "System & Programs",
        "description": "Windows OS, installed programs, dev tools",
        "categories": ["application", "system"],
    },
    "games": {
        "name": "Games",
        "description": "Game installations (Steam, Epic, etc.)",
        "categories": ["game", "game_data"],
    },
    "projects": {
        "name": "Projects & Code",
        "description": "Active development projects, source code, repos",
        "categories": ["code"],
    },
    "documents": {
        "name": "Documents & Personal",
        "description": "PDFs, office docs, CVs, applications, personal files",
        "categories": ["document"],
    },
    "media": {
        "name": "Media",
        "description": "Photos, videos, music, drone footage",
        "categories": ["video", "audio", "image"],
    },
    "archive": {
        "name": "Archive & Backup",
        "description": "Old files, backups, things you want to keep but rarely access",
        "categories": ["archive"],
    },
    "downloads": {
        "name": "Downloads Staging",
        "description": "Temporary download location, sort regularly",
        "categories": [],
    },
    "vms": {
        "name": "Virtual Machines & Labs",
        "description": "VMs, ISOs, lab environments, security tools",
        "categories": ["vm", "forensics"],
    },
}


def suggest_drive_purposes(drives_info):
    """
    Suggest drive purposes based on drive characteristics.

    Args:
        drives_info: list of dicts with 'drive', 'label', 'total_bytes', 'free_bytes'

    Returns:
        dict mapping drive letter to suggested purpose key
    """
    suggestions = {}
    for d in drives_info:
        letter = d["drive"]
        label = (d.get("label") or "").lower()
        total_gb = d.get("total_bytes", 0) / (1024**3)

        if letter == "C":
            suggestions[letter] = "system"
        elif "game" in label:
            suggestions[letter] = "games"
        elif "download" in label:
            suggestions[letter] = "downloads"
        elif "torrent" in label:
            suggestions[letter] = "archive"  # repurpose torrents drive
        elif "mujrim" in label:
            suggestions[letter] = "archive"
        elif total_gb < 300:
            suggestions[letter] = "projects"  # small SSDs good for active work
        elif total_gb > 1500:
            suggestions[letter] = "games"  # large drives for games
        else:
            suggestions[letter] = "media"

    return suggestions


def find_misplaced_files(drive, purpose_key, limit=200):
    """
    Find files on a drive that don't match its assigned purpose.

    Returns list of files that should probably be on a different drive.
    """
    if purpose_key not in PURPOSE_TEMPLATES:
        return []

    purpose = PURPOSE_TEMPLATES[purpose_key]
    wanted_categories = purpose["categories"]

    if not wanted_categories:
        return []  # downloads/staging has no fixed categories

    placeholders = ",".join("?" * len(wanted_categories))
    # Also keep system-essential stuff
    always_keep = ("system", "application", "shortcut", "font", "database")
    keep_placeholders = ",".join("?" * len(always_keep))

    rows = query_all(
        f"""SELECT path, filename, size, category, accessed_at
            FROM files
            WHERE drive = ?
              AND category NOT IN ({placeholders})
              AND category NOT IN ({keep_placeholders})
              AND size > 1048576
            ORDER BY size DESC
            LIMIT ?""",
        (drive,) + tuple(wanted_categories) + tuple(always_keep) + (limit,)
    )
    return rows


def find_best_destination(file_category, drive_purposes):
    """Given a file category, find which drive is assigned to hold that type."""
    for dp in drive_purposes:
        purpose_key = dp["purpose"]
        if purpose_key in PURPOSE_TEMPLATES:
            if file_category in PURPOSE_TEMPLATES[purpose_key]["categories"]:
                return dp["drive"]
    return None


def queue_file_move(source_path, dest_drive, size):
    """Add a file move to the queue."""
    # Preserve relative path structure
    source_drive = source_path[0]
    rel_path = source_path[3:]  # Strip "X:\"
    dest_path = f"{dest_drive}:\\{rel_path}"
    add_to_move_queue(source_path, dest_path, size)


def queue_file_delete(path, size, reason):
    """Add a file to the deletion queue."""
    add_to_delete_queue(path, size, reason)


def execute_deletes(dry_run=False, use_recycle=True):
    """
    Execute pending deletions.

    Args:
        dry_run: if True, just report what would be deleted
        use_recycle: if True, move to recycle bin instead of permanent delete

    Returns:
        list of (path, size, status) tuples
    """
    queue = get_delete_queue()
    results = []

    for item in queue:
        path = item["path"]
        size = item["size"]

        if dry_run:
            results.append((path, size, "would_delete"))
            continue

        if _is_protected(path):
            update_queue_status("delete_queue", item["id"], "blocked_protected")
            results.append((path, size, "blocked: system protected"))
            continue

        try:
            if os.path.exists(path):
                if use_recycle:
                    _send_to_recycle(path)
                else:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                update_queue_status("delete_queue", item["id"], "completed")
                results.append((path, size, "deleted"))
            else:
                update_queue_status("delete_queue", item["id"], "not_found")
                results.append((path, size, "not_found"))
        except (OSError, PermissionError) as e:
            update_queue_status("delete_queue", item["id"], f"error: {e}")
            results.append((path, size, f"error: {e}"))

    return results


def execute_moves(dry_run=False):
    """Execute pending file moves."""
    queue = get_move_queue()
    results = []

    for item in queue:
        source = item["source_path"]
        dest = item["dest_path"]
        size = item["size"]

        if dry_run:
            results.append((source, dest, size, "would_move"))
            continue

        try:
            if os.path.exists(source):
                dest_dir = os.path.dirname(dest)
                os.makedirs(dest_dir, exist_ok=True)
                shutil.move(source, dest)
                update_queue_status("move_queue", item["id"], "completed")
                results.append((source, dest, size, "moved"))
            else:
                update_queue_status("move_queue", item["id"], "not_found")
                results.append((source, dest, size, "not_found"))
        except (OSError, PermissionError) as e:
            update_queue_status("move_queue", item["id"], f"error: {e}")
            results.append((source, dest, size, f"error: {e}"))

    return results


def _send_to_recycle(path):
    """Send a file to the Windows Recycle Bin."""
    try:
        # Try using send2trash if available
        from send2trash import send2trash
        send2trash(path)
    except ImportError:
        # Fallback: use ctypes to call SHFileOperation
        try:
            import ctypes
            from ctypes import wintypes

            class SHFILEOPSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("wFunc", ctypes.c_uint),
                    ("pFrom", ctypes.c_wchar_p),
                    ("pTo", ctypes.c_wchar_p),
                    ("fFlags", ctypes.c_ushort),
                    ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", ctypes.c_wchar_p),
                ]

            FO_DELETE = 3
            FOF_ALLOWUNDO = 0x0040
            FOF_NOCONFIRMATION = 0x0010
            FOF_SILENT = 0x0004

            op = SHFILEOPSTRUCT()
            op.wFunc = FO_DELETE
            op.pFrom = path + "\0"
            op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT

            ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        except Exception:
            # Last resort: just delete
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
