"""
Smart analysis engine — actually thinks about what's safe to delete.

Instead of dumping raw file lists, categorizes files into confidence tiers:
  SAFE        - Definitely deletable (caches, temp, node_modules, old logs)
  RECOMMENDED - Very likely safe (re-downloadable, outdated versions, old installers)
  SUGGESTED   - Probably fine but user should glance (stale files in non-personal dirs)
  ASK         - User should decide (old media, abandoned projects)

Each file gets a reason explaining WHY it's suggested for deletion.
"""

import os
import re
from datetime import datetime, timedelta
from collections import defaultdict
from database import query_all, query_aggregate

# ── Confidence tiers ──────────────────────────────────────────────
SAFE = "SAFE"              # auto-checked, no brainer
RECOMMENDED = "RECOMMENDED"  # auto-checked, but user can review
SUGGESTED = "SUGGESTED"      # unchecked, user should look
ASK = "ASK"                  # unchecked, needs human judgment
MISPLACED = "MISPLACED"      # file on wrong drive (from organize panel)

TIER_ORDER = {SAFE: 0, RECOMMENDED: 1, SUGGESTED: 2, ASK: 3, MISPLACED: 4}

# ── System exclusion (same as analyzer.py) ────────────────────────
SYS_EXCL = "category != 'system_protected'"

# ── Known re-downloadable / junk patterns ─────────────────────────

# Folders whose ENTIRE contents are safe to nuke (reinstallable)
REINSTALLABLE_FOLDERS = {
    "node_modules", "__pycache__", ".next", ".nuxt", ".cache",
    "venv", ".venv", ".tox", ".pytest_cache", ".mypy_cache",
    ".parcel-cache", ".turbo", ".angular",
}

# Known temp/junk extensions
JUNK_EXTENSIONS = {
    ".tmp", ".temp", ".log", ".bak", ".old", ".cache", ".dmp",
    ".etl", ".chk", ".gid", ".fts", ".ftg",
}

# Installer extensions (re-downloadable)
INSTALLER_EXTENSIONS = {".exe", ".msi", ".iso", ".img"}

# Known piracy / activator patterns (security risk + legal liability)
PIRACY_PATTERNS = [
    "kmspico", "kmsauto", "kms_", "activator", "crack", "keygen",
    "patch.exe", "loader.exe", "fitgirl", "repack",
    "crackingpatching", "tech-tools",
]

# Known game launchers whose content is re-downloadable
REDOWNLOADABLE_GAME_PATHS = [
    "\\steamapps\\common\\",
    "\\epic games\\",
    "\\ubisoft game launcher\\games\\",
    "\\ea games\\",
    "\\origin games\\",
    "\\riot games\\",
    "\\battlestate games\\",
]

# Personal / precious file indicators (DON'T suggest deleting)
PRECIOUS_INDICATORS = [
    "\\photos\\", "\\pictures\\", "\\billeder\\",
    "\\documents\\ansøgninger\\",  # job applications
    "\\documents\\forretning\\",   # business docs
    "\\documents\\github\\",       # active code
    "\\desktop\\",
    "\\onedrive\\",
]

PRECIOUS_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff",
    ".cr2", ".nef", ".dng", ".raw",  # photos
    ".doc", ".docx", ".pdf", ".pptx", ".xlsx",  # documents
    ".kdbx",  # password databases
}

# ── Version detection pattern ─────────────────────────────────────
VERSION_RE = re.compile(
    r'[_\-\s]v?(\d+[\.\-]\d+(?:[\.\-]\d+)*)',
    re.IGNORECASE
)


def smart_scan(months_stale=12, min_size_mb=1):
    """
    Run a comprehensive smart analysis across all drives.

    Returns a list of dicts, each with:
        path, filename, size, drive, category, accessed_at,
        tier (SAFE/RECOMMENDED/SUGGESTED/ASK),
        reason (human-readable explanation),
        auto_check (bool)
    """
    results = []
    seen_paths = set()
    now = datetime.now()
    stale_cutoff = (now - timedelta(days=months_stale * 30)).isoformat()
    min_size = min_size_mb * 1024 * 1024

    # ── 1. Junk files (temp, cache, logs) → SAFE ─────────────────
    junk = query_all(
        f"""SELECT path, filename, size, drive, category, accessed_at, extension
            FROM files
            WHERE {SYS_EXCL} AND category IN ('temp', 'cache', 'dependency')
              AND size >= ?
            ORDER BY size DESC LIMIT 500""",
        (min_size,)
    )
    for row in junk:
        d = dict(row)
        if d["path"] in seen_paths:
            continue
        seen_paths.add(d["path"])
        if "node_modules" in d["path"].lower():
            reason = "node_modules — reinstall with npm install"
        elif "__pycache__" in d["path"].lower():
            reason = "Python cache — auto-regenerated"
        elif d["category"] == "cache":
            reason = "Cache file — auto-regenerated"
        elif d["category"] == "dependency":
            reason = "Dependency folder — reinstallable"
        else:
            reason = f"Temp/junk file ({d['extension']})"

        results.append(_make_result(d, SAFE, reason, auto_check=False))

    # ── 2. Old installers in download-like locations → RECOMMENDED ──
    installers = query_all(
        f"""SELECT path, filename, size, drive, category, accessed_at, extension
            FROM files
            WHERE {SYS_EXCL}
              AND extension IN ('.exe', '.msi', '.iso', '.img')
              AND size >= ?
              AND accessed_at < ?
              AND (
                  LOWER(path) LIKE '%download%'
                  OR LOWER(path) LIKE '%installer%'
                  OR LOWER(path) LIKE '%setup%'
                  OR LOWER(path) LIKE '%torrent%'
              )
            ORDER BY size DESC LIMIT 300""",
        (min_size, stale_cutoff)
    )
    for row in installers:
        d = dict(row)
        if d["path"] in seen_paths:
            continue
        seen_paths.add(d["path"])

        fname_lower = d["filename"].lower()

        # Check for piracy/activators — extra reason to delete
        is_piracy = any(p in fname_lower for p in PIRACY_PATTERNS)
        if is_piracy:
            reason = "Pirated software / activator — security risk, delete immediately"
            tier = SAFE
        else:
            reason = f"Old installer, not accessed in {months_stale}+ months — re-downloadable"
            tier = RECOMMENDED

        results.append(_make_result(d, tier, reason, auto_check=False))

    # ── 3. Torrent files → RECOMMENDED ───────────────────────────
    torrents = query_all(
        f"""SELECT path, filename, size, drive, category, accessed_at, extension
            FROM files
            WHERE {SYS_EXCL} AND extension = '.torrent'
            ORDER BY size DESC LIMIT 200""",
        ()
    )
    for row in torrents:
        d = dict(row)
        if d["path"] in seen_paths:
            continue
        seen_paths.add(d["path"])
        results.append(_make_result(d, RECOMMENDED,
                                    "Torrent file — no longer needed after download",
                                    auto_check=False))

    # ── 4. Piracy artifacts anywhere → SAFE ──────────────────────
    for pattern in PIRACY_PATTERNS:
        piracy_files = query_all(
            f"""SELECT path, filename, size, drive, category, accessed_at, extension
                FROM files
                WHERE {SYS_EXCL} AND LOWER(filename) LIKE ?
                  AND size >= ?
                ORDER BY size DESC LIMIT 50""",
            (f"%{pattern}%", min_size)
        )
        for row in piracy_files:
            d = dict(row)
            if d["path"] in seen_paths:
                continue
            seen_paths.add(d["path"])
            results.append(_make_result(d, SAFE,
                                        "Pirated software / crack — security risk + legal liability",
                                        auto_check=False))

    # ── 5. Outdated versions (same base name, different versions) → RECOMMENDED
    _find_outdated_versions(results, seen_paths, min_size)

    # ── 6. Duplicate files across drives → RECOMMENDED (keep newest) ─
    _find_smart_duplicates(results, seen_paths, min_size)

    # ── 7. Stale large files (not personal) → SUGGESTED ──────────
    stale = query_all(
        f"""SELECT path, filename, size, drive, category, accessed_at, extension
            FROM files
            WHERE {SYS_EXCL}
              AND accessed_at < ?
              AND size >= ?
              AND category NOT IN ('temp', 'cache', 'dependency')
            ORDER BY size DESC LIMIT 500""",
        (stale_cutoff, min_size)
    )
    for row in stale:
        d = dict(row)
        if d["path"] in seen_paths:
            continue
        seen_paths.add(d["path"])

        path_lower = d["path"].lower()

        # Skip precious files
        if _is_precious(path_lower, d["extension"]):
            continue

        # Games in steam/epic are re-downloadable
        is_game_redownloadable = any(gp in path_lower for gp in REDOWNLOADABLE_GAME_PATHS)
        if is_game_redownloadable:
            reason = f"Game file not accessed in {months_stale}+ months — re-downloadable from store"
            tier = RECOMMENDED
            auto = True
        elif d["category"] in ("archive", "vm"):
            reason = f"Large archive/VM not accessed in {months_stale}+ months"
            tier = SUGGESTED
            auto = False
        elif d["category"] in ("video", "audio"):
            reason = f"Media file not accessed in {months_stale}+ months"
            tier = ASK
            auto = False
        else:
            age_str = _age_string(d["accessed_at"])
            reason = f"Not accessed in {age_str} — {d['category']} file"
            tier = SUGGESTED
            auto = False

        results.append(_make_result(d, tier, reason, auto_check=auto))

    # ── 8. Old phone backups where newer exists → SUGGESTED ──────
    _find_old_backups(results, seen_paths, min_size)

    # Sort by tier priority, then by size descending
    results.sort(key=lambda r: (TIER_ORDER.get(r["tier"], 99), -r["size"]))

    return results


def smart_scan_summary(results):
    """Summarize smart scan results by tier."""
    summary = {}
    for tier in [SAFE, RECOMMENDED, SUGGESTED, ASK, MISPLACED]:
        items = [r for r in results if r["tier"] == tier]
        summary[tier] = {
            "count": len(items),
            "total_size": sum(r["size"] for r in items),
            "auto_checked": sum(1 for r in items if r["auto_check"]),
        }
    return summary


# ── Internal helpers ──────────────────────────────────────────────

def _make_result(d, tier, reason, auto_check=False):
    return {
        "path": d.get("path", ""),
        "filename": d.get("filename", ""),
        "size": d.get("size", 0) or 0,
        "drive": d.get("drive", ""),
        "category": d.get("category", ""),
        "accessed_at": d.get("accessed_at", ""),
        "extension": d.get("extension", ""),
        "tier": tier,
        "reason": reason,
        "auto_check": auto_check,
    }


def _is_precious(path_lower, extension):
    """Check if a file is likely personal/precious and should not be suggested."""
    ext = (extension or "").lower()
    if ext in PRECIOUS_EXTENSIONS:
        return True
    for indicator in PRECIOUS_INDICATORS:
        if indicator in path_lower:
            return True
    return False


def _age_string(iso_date):
    """Human readable age from ISO date."""
    try:
        dt = datetime.fromisoformat(iso_date)
        days = (datetime.now() - dt).days
        if days < 30:
            return f"{days} days"
        if days < 365:
            return f"{days // 30} months"
        years = days // 365
        months = (days % 365) // 30
        if months:
            return f"{years}y {months}m"
        return f"{years} years"
    except (ValueError, TypeError):
        return "unknown time"


def _find_outdated_versions(results, seen_paths, min_size):
    """Find files that look like older versions of something."""
    # Look for files with version numbers in common directories
    versioned = query_all(
        f"""SELECT path, filename, size, drive, category, accessed_at, extension
            FROM files
            WHERE {SYS_EXCL}
              AND size >= ?
              AND (
                  LOWER(path) LIKE '%download%'
                  OR LOWER(path) LIKE '%installer%'
                  OR LOWER(path) LIKE '%desktop%'
              )
            ORDER BY filename, size DESC""",
        (min_size,)
    )

    # Group by base name (strip version numbers)
    groups = defaultdict(list)
    for row in versioned:
        d = dict(row)
        fname = d["filename"]
        base = VERSION_RE.sub("", fname).lower().strip(" _-.")
        ext = d.get("extension", "").lower()
        key = (base, ext)
        if base and len(base) > 3:  # skip very short base names
            groups[key].append(d)

    for key, files in groups.items():
        if len(files) < 2:
            continue
        # Sort by modified date or version — keep the newest
        files.sort(key=lambda f: f.get("accessed_at", ""), reverse=True)
        newest = files[0]
        for old in files[1:]:
            if old["path"] in seen_paths:
                continue
            if old["path"] == newest["path"]:
                continue
            seen_paths.add(old["path"])
            results.append(_make_result(
                old, RECOMMENDED,
                f"Older version — newer exists: {newest['filename']}",
                auto_check=False
            ))


def _find_smart_duplicates(results, seen_paths, min_size):
    """
    Find duplicate files efficiently and mark older copies for deletion.
    Uses a two-phase approach: first find candidate groups by size,
    then match by name within size groups.
    """
    # Phase 1: Find sizes that appear on multiple drives (fast query)
    dup_sizes = query_all(
        f"""SELECT filename, size, COUNT(DISTINCT drive) as drive_count
            FROM files
            WHERE {SYS_EXCL} AND size >= ?
            GROUP BY filename, size
            HAVING COUNT(*) > 1 AND COUNT(DISTINCT drive) > 1
            ORDER BY size DESC
            LIMIT 100""",
        (min_size,)
    )

    for dup in dup_sizes:
        fname = dup["filename"]
        fsize = dup["size"]

        # Phase 2: Get all copies of this file
        copies = query_all(
            f"""SELECT path, filename, size, drive, category, accessed_at, extension
                FROM files
                WHERE {SYS_EXCL} AND filename = ? AND size = ?
                ORDER BY accessed_at DESC""",
            (fname, fsize)
        )
        if len(copies) < 2:
            continue

        # Keep the most recently accessed copy, suggest deleting the rest
        copies_list = [dict(c) for c in copies]
        keep = copies_list[0]

        for dup_copy in copies_list[1:]:
            if dup_copy["path"] in seen_paths:
                continue
            # Don't suggest deleting from Desktop or Documents
            if _is_precious(dup_copy["path"].lower(), dup_copy.get("extension", "")):
                continue
            seen_paths.add(dup_copy["path"])
            results.append(_make_result(
                dup_copy, RECOMMENDED,
                f"Duplicate — keeping newer copy on {keep['drive']}: drive",
                auto_check=False
            ))


def _find_old_backups(results, seen_paths, min_size):
    """Find old phone/system backups where a newer one exists."""
    backup_patterns = ["%backup%", "%backup %"]

    for pattern in backup_patterns:
        backups = query_all(
            f"""SELECT path, filename, size, drive, category, accessed_at, extension
                FROM files
                WHERE {SYS_EXCL}
                  AND LOWER(path) LIKE ?
                  AND size >= ?
                ORDER BY path""",
            (pattern, min_size)
        )

        # Group by directory
        by_dir = defaultdict(list)
        for row in backups:
            d = dict(row)
            parent = os.path.dirname(d["path"])
            by_dir[parent].append(d)

        for parent_dir, files in by_dir.items():
            if len(files) < 2:
                continue
            files.sort(key=lambda f: f.get("accessed_at", ""), reverse=True)
            # Keep newest, suggest deleting older
            for old in files[1:]:
                if old["path"] in seen_paths:
                    continue
                seen_paths.add(old["path"])
                results.append(_make_result(
                    old, SUGGESTED,
                    "Older backup — newer version exists in same folder",
                    auto_check=False
                ))


