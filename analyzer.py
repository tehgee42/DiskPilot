"""Analysis engine - finds stale files, duplicates, large files, and cleanup candidates."""
from datetime import datetime, timedelta
from collections import defaultdict

from database import query_files, query_all, query_aggregate

# Every user-facing query must exclude system-protected files
SYS_EXCL = "category != 'system_protected'"


def format_size(size_bytes):
    """Human-readable file size."""
    if size_bytes < 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def format_age(iso_date):
    """Human-readable age from ISO date string."""
    try:
        dt = datetime.fromisoformat(iso_date)
        delta = datetime.now() - dt
        days = delta.days
        if days < 1:
            return "today"
        if days < 30:
            return f"{days} days ago"
        if days < 365:
            months = days // 30
            return f"{months} month{'s' if months != 1 else ''} ago"
        years = days // 365
        months = (days % 365) // 30
        if months:
            return f"{years}y {months}m ago"
        return f"{years} year{'s' if years != 1 else ''} ago"
    except (ValueError, TypeError):
        return "unknown"


# ---------------------------------------------------------------------------
# Stale / unused files
# ---------------------------------------------------------------------------

def find_stale_files(months=12, min_size_mb=1, drive=None, limit=500):
    """Find files not accessed in the given number of months."""
    cutoff = (datetime.now() - timedelta(days=months * 30)).isoformat()
    min_size = min_size_mb * 1024 * 1024

    where = f"accessed_at < ? AND size >= ? AND {SYS_EXCL}"
    params = [cutoff, min_size]
    if drive:
        where += " AND drive = ?"
        params.append(drive)

    return query_files(where, tuple(params), order_by="size DESC", limit=limit)


def find_stale_summary(months=12, min_size_mb=1):
    """Get a summary of stale files per drive."""
    cutoff = (datetime.now() - timedelta(days=months * 30)).isoformat()
    min_size = min_size_mb * 1024 * 1024

    rows = query_all(
        f"""SELECT drive, COUNT(*) as count, SUM(size) as total_size
           FROM files
           WHERE accessed_at < ? AND size >= ? AND {SYS_EXCL}
           GROUP BY drive ORDER BY drive""",
        (cutoff, min_size)
    )
    return rows


# ---------------------------------------------------------------------------
# Large files
# ---------------------------------------------------------------------------

def find_largest_files(drive=None, limit=50):
    """Find the largest files, optionally filtered by drive."""
    where = SYS_EXCL
    params = ()
    if drive:
        where += " AND drive = ?"
        params = (drive,)
    return query_files(where, params, order_by="size DESC", limit=limit)


# ---------------------------------------------------------------------------
# Category breakdown
# ---------------------------------------------------------------------------

def category_breakdown(drive=None):
    """Get file count and total size per category."""
    where = f"WHERE {SYS_EXCL}"
    params = ()
    if drive:
        where += " AND drive = ?"
        params = (drive,)

    rows = query_all(
        f"""SELECT category, COUNT(*) as count, SUM(size) as total_size
            FROM files {where}
            GROUP BY category
            ORDER BY total_size DESC""",
        params
    )
    return rows


def extension_breakdown(drive=None, limit=30):
    """Get file count and total size per extension."""
    where = f"WHERE {SYS_EXCL}"
    params = ()
    if drive:
        where += " AND drive = ?"
        params = (drive,)

    rows = query_all(
        f"""SELECT extension, COUNT(*) as count, SUM(size) as total_size
            FROM files {where}
            GROUP BY extension
            ORDER BY total_size DESC
            LIMIT ?""",
        params + (limit,)
    )
    return rows


# ---------------------------------------------------------------------------
# Duplicates (by size, then by name+size)
# ---------------------------------------------------------------------------

def find_potential_duplicates(min_size_mb=10, drive=None, limit=200):
    """Find files with identical names and sizes (likely duplicates)."""
    where = ""
    params = ()
    if drive:
        where = f"WHERE f.drive = ?"
        params = (drive,)

    min_size = min_size_mb * 1024 * 1024

    rows = query_all(
        f"""SELECT f.filename, f.size, f.drive, f.path, f.accessed_at, f.category
            FROM files f
            INNER JOIN (
                SELECT filename, size
                FROM files
                {"WHERE drive = ?" if drive else ""}
                GROUP BY filename, size
                HAVING COUNT(*) > 1 AND size >= ?
            ) d ON f.filename = d.filename AND f.size = d.size
            ORDER BY f.size DESC, f.filename, f.path
            LIMIT ?""",
        (params + (min_size, limit)) if drive else ((min_size, limit))
    )
    return rows


# ---------------------------------------------------------------------------
# Temp / cache / junk files
# ---------------------------------------------------------------------------

def find_junk_files(drive=None, limit=500):
    """Find temp files, caches, logs, and other junk."""
    junk_categories = ("temp", "cache", "dependency")
    placeholders = ",".join("?" * len(junk_categories))

    where = f"category IN ({placeholders}) AND {SYS_EXCL}"
    params = list(junk_categories)
    if drive:
        where += " AND drive = ?"
        params.append(drive)

    return query_files(where, tuple(params), order_by="size DESC", limit=limit)


def find_junk_summary():
    """Summary of junk files per drive."""
    rows = query_all(
        f"""SELECT drive, category, COUNT(*) as count, SUM(size) as total_size
           FROM files
           WHERE category IN ('temp', 'cache', 'dependency') AND {SYS_EXCL}
           GROUP BY drive, category
           ORDER BY drive, total_size DESC"""
    )
    return rows


# ---------------------------------------------------------------------------
# Old installers and archives
# ---------------------------------------------------------------------------

def find_old_installers(months=6, drive=None, limit=200):
    """Find .exe, .msi, .iso files that are likely old installers."""
    cutoff = (datetime.now() - timedelta(days=months * 30)).isoformat()
    installer_exts = (".exe", ".msi", ".iso", ".img")
    placeholders = ",".join("?" * len(installer_exts))

    where = f"extension IN ({placeholders}) AND accessed_at < ? AND size > 1048576 AND {SYS_EXCL}"
    params = list(installer_exts) + [cutoff]
    if drive:
        where += " AND drive = ?"
        params.append(drive)

    return query_files(where, tuple(params), order_by="size DESC", limit=limit)


# ---------------------------------------------------------------------------
# Drive-level stats
# ---------------------------------------------------------------------------

def drive_summary():
    """Get overall stats per drive from the scan data."""
    rows = query_all(
        f"""SELECT drive,
                  COUNT(*) as total_files,
                  SUM(size) as total_size,
                  MIN(accessed_at) as oldest_access,
                  MAX(accessed_at) as newest_access,
                  AVG(size) as avg_size
           FROM files
           WHERE {SYS_EXCL}
           GROUP BY drive
           ORDER BY drive"""
    )
    return rows


def age_distribution(drive=None):
    """Break down files by age buckets: <1mo, 1-6mo, 6-12mo, 1-2y, 2-5y, 5y+."""
    now = datetime.now()
    buckets = [
        ("< 1 month", (now - timedelta(days=30)).isoformat(), now.isoformat()),
        ("1-6 months", (now - timedelta(days=180)).isoformat(), (now - timedelta(days=30)).isoformat()),
        ("6-12 months", (now - timedelta(days=365)).isoformat(), (now - timedelta(days=180)).isoformat()),
        ("1-2 years", (now - timedelta(days=730)).isoformat(), (now - timedelta(days=365)).isoformat()),
        ("2-5 years", (now - timedelta(days=1825)).isoformat(), (now - timedelta(days=730)).isoformat()),
        ("5+ years", "2000-01-01", (now - timedelta(days=1825)).isoformat()),
    ]

    results = []
    for label, start, end in buckets:
        where = f"accessed_at >= ? AND accessed_at < ? AND {SYS_EXCL}"
        params = [start, end]
        if drive:
            where += " AND drive = ?"
            params.append(drive)

        row = query_aggregate(
            f"SELECT COUNT(*) as count, COALESCE(SUM(size), 0) as total_size FROM files WHERE {where}",
            tuple(params)
        )
        results.append({
            "label": label,
            "count": row["count"] if row else 0,
            "total_size": row["total_size"] if row else 0,
        })

    return results


# ---------------------------------------------------------------------------
# Folder-level analysis
# ---------------------------------------------------------------------------

def largest_folders(drive=None, depth=2, limit=30):
    """Find the largest top-level folders."""
    where = f"WHERE {SYS_EXCL}"
    params = ()
    if drive:
        where += " AND drive = ?"
        params = (drive,)

    # We'll extract the folder at the given depth and aggregate
    # For depth=2 on C:, this groups by C:\Users, C:\Windows, etc.
    rows = query_all(
        f"""SELECT
                SUBSTR(path, 1, INSTR(SUBSTR(path, 4), '\\') + 3) as folder,
                COUNT(*) as count,
                SUM(size) as total_size
            FROM files
            {where}
            GROUP BY folder
            HAVING folder != ''
            ORDER BY total_size DESC
            LIMIT ?""",
        params + (limit,)
    )
    return rows
