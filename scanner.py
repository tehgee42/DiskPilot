"""File scanner engine - walks drives and catalogs everything."""
import os
import hashlib
from datetime import datetime
from collections import defaultdict

from database import (
    start_scan, finish_scan, insert_files_batch, save_drive_purpose
)

# File category mappings
CATEGORY_MAP = {
    # Games
    ".exe": "application",
    ".dll": "application",
    ".msi": "application",
    ".sys": "system",

    # Documents
    ".pdf": "document",
    ".doc": "document",
    ".docx": "document",
    ".xls": "document",
    ".xlsx": "document",
    ".ppt": "document",
    ".pptx": "document",
    ".txt": "document",
    ".rtf": "document",
    ".odt": "document",
    ".csv": "document",
    ".md": "document",
    ".epub": "document",

    # Images
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".gif": "image",
    ".bmp": "image",
    ".svg": "image",
    ".ico": "image",
    ".webp": "image",
    ".tif": "image",
    ".tiff": "image",
    ".psd": "image",
    ".raw": "image",
    ".cr2": "image",
    ".nef": "image",
    ".dng": "image",

    # Video
    ".mp4": "video",
    ".mkv": "video",
    ".avi": "video",
    ".mov": "video",
    ".wmv": "video",
    ".flv": "video",
    ".webm": "video",
    ".m4v": "video",
    ".mpg": "video",
    ".mpeg": "video",
    ".3gp": "video",

    # Audio
    ".mp3": "audio",
    ".wav": "audio",
    ".flac": "audio",
    ".aac": "audio",
    ".ogg": "audio",
    ".wma": "audio",
    ".m4a": "audio",

    # Archives
    ".zip": "archive",
    ".rar": "archive",
    ".7z": "archive",
    ".tar": "archive",
    ".gz": "archive",
    ".bz2": "archive",
    ".xz": "archive",
    ".iso": "archive",
    ".img": "archive",

    # Code
    ".py": "code",
    ".js": "code",
    ".ts": "code",
    ".jsx": "code",
    ".tsx": "code",
    ".html": "code",
    ".css": "code",
    ".java": "code",
    ".c": "code",
    ".cpp": "code",
    ".h": "code",
    ".cs": "code",
    ".go": "code",
    ".rs": "code",
    ".rb": "code",
    ".php": "code",
    ".sql": "code",
    ".sh": "code",
    ".bat": "code",
    ".ps1": "code",
    ".json": "code",
    ".xml": "code",
    ".yaml": "code",
    ".yml": "code",
    ".toml": "code",

    # Virtual machines
    ".ova": "vm",
    ".ovf": "vm",
    ".vmdk": "vm",
    ".vdi": "vm",
    ".vhd": "vm",
    ".vhdx": "vm",
    ".qcow2": "vm",

    # Torrents
    ".torrent": "torrent",

    # Game-specific
    ".pak": "game_data",
    ".wad": "game_data",
    ".bsp": "game_data",
    ".vpk": "game_data",
    ".gcf": "game_data",
    ".ncf": "game_data",

    # Temp / cache
    ".tmp": "temp",
    ".log": "temp",
    ".bak": "temp",
    ".cache": "temp",
    ".dmp": "temp",

    # Shortcuts
    ".lnk": "shortcut",
    ".url": "shortcut",

    # Fonts
    ".ttf": "font",
    ".otf": "font",
    ".woff": "font",
    ".woff2": "font",

    # Database
    ".db": "database",
    ".sqlite": "database",
    ".sqlite3": "database",
    ".mdb": "database",
    ".accdb": "database",

    # Disk images / forensics
    ".pcapng": "forensics",
    ".pcap": "forensics",
    ".mem": "forensics",
    ".raw": "forensics",
    ".e01": "forensics",
}

# Directories that are almost always safe to delete
JUNK_DIRS = {
    "$recycle.bin", "system volume information", "__pycache__",
    "node_modules", ".cache", "thumbs.db", "desktop.ini",
    ".ds_store", "temp", "tmp",
}

# Known large game folders (for smart detection)
GAME_INDICATORS = {
    "steamapps", "epic games", "ubisoft game launcher", "ea games",
    "riot games", "battlestate games", "star citizen", "fivem",
    "gog galaxy", "origin games",
}

# System-protected files — NEVER suggest for deletion
SYSTEM_PROTECTED_FILES = {
    "pagefile.sys", "hiberfil.sys", "swapfile.sys",
    "$mft", "$mftmirr", "$logfile", "$bitmap", "$badclus",
    "$secure", "$upcase", "$extend", "$volume",
    "bootmgr", "bootnxt", "bootsect.bak",
    "ntldr", "ntdetect.com", "bootfont.bin",
    "dumpstack.log.bin", "dumpstack.log",
    "ntuser.dat", "ntuser.dat.log", "ntuser.dat.log1", "ntuser.dat.log2",
    "usrclass.dat", "usrclass.dat.log1", "usrclass.dat.log2",
}

SYSTEM_PROTECTED_DIRS = {
    "$recycle.bin", "system volume information",
    "windows", "recovery", "$windows.~bt", "$windows.~ws",
    "perflogs", "config.msi",
    "msocache", "intel", "amd",
}

# Developer directories — skip entirely during scanning (too large, user-managed)
DEV_SKIP_DIRS = {
    "node_modules", "__pycache__", ".venv", "venv", ".env",
    ".next", ".nuxt", ".cache", ".npm", ".yarn",
    ".gradle", ".cargo", ".m2",
    ".tox", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".parcel-cache", ".turbo", ".angular", ".svelte-kit",
    ".expo", "bower_components", ".sass-cache",
    "coverage", ".nyc_output",
    ".idea", ".vs",
    "vendor",
    "target",
}

SYSTEM_PROTECTED_PATH_FRAGMENTS = [
    "\\windows\\",
    "\\program files\\",
    "\\program files (x86)\\",
]


def categorize_file(filepath, ext):
    """Determine the category of a file based on extension and path."""
    ext_lower = ext.lower()
    path_lower = filepath.lower()
    fname_lower = os.path.basename(filepath).lower()

    # System-protected files — never suggest for deletion
    if fname_lower in SYSTEM_PROTECTED_FILES:
        return "system_protected"
    if any(frag in path_lower for frag in SYSTEM_PROTECTED_PATH_FRAGMENTS):
        return "system_protected"

    # Path-based categories
    if any(g in path_lower for g in GAME_INDICATORS):
        return "game"
    if "\\appdata\\local\\temp" in path_lower:
        return "temp"
    if "\\cache\\" in path_lower or "\\caches\\" in path_lower:
        return "cache"
    if "node_modules" in path_lower:
        return "dependency"
    if "__pycache__" in path_lower:
        return "cache"

    return CATEGORY_MAP.get(ext_lower, "other")


def safe_stat(filepath):
    """Get file stats safely, returning None on error."""
    try:
        stat = os.stat(filepath)
        return {
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "accessed": datetime.fromtimestamp(stat.st_atime).isoformat(),
        }
    except (OSError, ValueError, OverflowError):
        return None


def scan_drive(drive_letter, progress_callback=None, skip_dirs=None, cancel_flag=None):
    """
    Scan a drive and store all file metadata in the database.

    Args:
        drive_letter: e.g. "C"
        progress_callback: function(files_scanned, current_path) called periodically
        skip_dirs: set of directory names to skip (lowercase)
        cancel_flag: threading.Event — if set, abort the scan

    Returns:
        (scan_id, total_files, total_size)
    """
    root = f"{drive_letter}:\\"
    if not os.path.exists(root):
        return None, 0, 0

    if skip_dirs is None:
        skip_dirs = set(SYSTEM_PROTECTED_DIRS) | DEV_SKIP_DIRS
    else:
        skip_dirs = skip_dirs | SYSTEM_PROTECTED_DIRS | DEV_SKIP_DIRS

    scan_id = start_scan(drive_letter)
    total_files = 0
    total_size = 0
    batch = []
    batch_size = 500

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        if cancel_flag and cancel_flag.is_set():
            break

        # Skip system/junk directories
        dirnames[:] = [
            d for d in dirnames
            if (d.lower() not in skip_dirs and not d.startswith("."))
            or d.lower() in {".git", ".vscode"}
        ]

        for fname in filenames:
            if cancel_flag and cancel_flag.is_set():
                break
            filepath = os.path.join(dirpath, fname)
            stats = safe_stat(filepath)
            if stats is None:
                continue

            _, ext = os.path.splitext(fname)
            category = categorize_file(filepath, ext)

            batch.append((
                scan_id,
                drive_letter,
                filepath,
                fname,
                ext.lower() if ext else "",
                stats["size"],
                stats["created"],
                stats["modified"],
                stats["accessed"],
                category,
            ))

            total_files += 1
            total_size += stats["size"]

            if len(batch) >= batch_size:
                insert_files_batch(batch)
                batch = []

                if progress_callback and total_files % 500 == 0:
                    progress_callback(total_files, filepath)

    # Insert remaining
    if batch:
        insert_files_batch(batch)

    finish_scan(scan_id, total_files, total_size)

    # Save drive info
    try:
        import shutil
        usage = shutil.disk_usage(root)
        label = get_volume_label(drive_letter)
        save_drive_purpose(drive_letter, label, "", usage.total, usage.free)
    except Exception:
        pass

    return scan_id, total_files, total_size


def get_volume_label(drive_letter):
    """Get the volume label for a drive using ctypes (no terminal window)."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        buf = ctypes.create_unicode_buffer(261)
        ret = kernel32.GetVolumeInformationW(
            f"{drive_letter}:\\", buf, 261, None, None, None, None, 0
        )
        if ret and buf.value:
            return buf.value
    except Exception:
        pass
    return ""


def hash_file(filepath, chunk_size=8192):
    """Compute MD5 hash of a file for duplicate detection."""
    h = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def get_available_drives():
    """Return list of drive letters that exist on the system."""
    drives = []
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        if os.path.exists(f"{letter}:\\"):
            drives.append(letter)
    return drives
