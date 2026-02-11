"""SQLite database layer for DiskPilot."""
import sqlite3
import os
import sys
from datetime import datetime

if getattr(sys, 'frozen', False):
    # Running as packaged exe — store DB in user's AppData
    _DB_DIR = os.path.join(os.environ.get("APPDATA", "."), "DiskPilot")
    os.makedirs(_DB_DIR, exist_ok=True)
    DB_PATH = os.path.join(_DB_DIR, "diskpilot.db")
else:
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drivemanager.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drive TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            total_files INTEGER DEFAULT 0,
            total_size INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL,
            drive TEXT NOT NULL,
            path TEXT NOT NULL,
            filename TEXT NOT NULL,
            extension TEXT,
            size INTEGER DEFAULT 0,
            created_at TEXT,
            modified_at TEXT,
            accessed_at TEXT,
            category TEXT DEFAULT 'other',
            hash TEXT,
            FOREIGN KEY (scan_id) REFERENCES scans(id)
        );

        CREATE INDEX IF NOT EXISTS idx_files_drive ON files(drive);
        CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension);
        CREATE INDEX IF NOT EXISTS idx_files_category ON files(category);
        CREATE INDEX IF NOT EXISTS idx_files_size ON files(size);
        CREATE INDEX IF NOT EXISTS idx_files_accessed ON files(accessed_at);
        CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);

        CREATE TABLE IF NOT EXISTS drive_purposes (
            drive TEXT PRIMARY KEY,
            label TEXT,
            purpose TEXT,
            total_bytes INTEGER DEFAULT 0,
            free_bytes INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS move_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL,
            dest_path TEXT NOT NULL,
            size INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS delete_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            size INTEGER DEFAULT 0,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


def start_scan(drive):
    conn = get_connection()
    # Clear old scan data for this drive
    old_scans = conn.execute("SELECT id FROM scans WHERE drive = ?", (drive,)).fetchall()
    for s in old_scans:
        conn.execute("DELETE FROM files WHERE scan_id = ?", (s["id"],))
    conn.execute("DELETE FROM scans WHERE drive = ?", (drive,))

    cursor = conn.execute(
        "INSERT INTO scans (drive, started_at) VALUES (?, ?)",
        (drive, datetime.now().isoformat())
    )
    scan_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return scan_id


def finish_scan(scan_id, total_files, total_size):
    conn = get_connection()
    conn.execute(
        "UPDATE scans SET finished_at = ?, total_files = ?, total_size = ? WHERE id = ?",
        (datetime.now().isoformat(), total_files, total_size, scan_id)
    )
    conn.commit()
    conn.close()


def insert_files_batch(rows):
    """Insert a batch of file records. Each row is a tuple:
    (scan_id, drive, path, filename, extension, size, created_at, modified_at, accessed_at, category)
    """
    conn = get_connection()
    conn.executemany(
        """INSERT INTO files
           (scan_id, drive, path, filename, extension, size, created_at, modified_at, accessed_at, category)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows
    )
    conn.commit()
    conn.close()


def save_drive_purpose(drive, label, purpose, total_bytes, free_bytes):
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO drive_purposes (drive, label, purpose, total_bytes, free_bytes)
           VALUES (?, ?, ?, ?, ?)""",
        (drive, label, purpose, total_bytes, free_bytes)
    )
    conn.commit()
    conn.close()


def get_drive_purposes():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM drive_purposes ORDER BY drive").fetchall()
    conn.close()
    return rows


def get_scan_info():
    conn = get_connection()
    rows = conn.execute(
        "SELECT drive, finished_at, total_files, total_size FROM scans WHERE finished_at IS NOT NULL ORDER BY drive"
    ).fetchall()
    conn.close()
    return rows


def query_files(where_clause="1=1", params=(), order_by="size DESC", limit=100):
    conn = get_connection()
    rows = conn.execute(
        f"SELECT * FROM files WHERE {where_clause} ORDER BY {order_by} LIMIT ?",
        params + (limit,)
    ).fetchall()
    conn.close()
    return rows


def query_aggregate(sql, params=()):
    conn = get_connection()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row


def query_all(sql, params=()):
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def add_to_delete_queue(path, size, reason):
    conn = get_connection()
    conn.execute(
        "INSERT INTO delete_queue (path, size, reason) VALUES (?, ?, ?)",
        (path, size, reason)
    )
    conn.commit()
    conn.close()


def add_to_move_queue(source, dest, size):
    conn = get_connection()
    conn.execute(
        "INSERT INTO move_queue (source_path, dest_path, size) VALUES (?, ?, ?)",
        (source, dest, size)
    )
    conn.commit()
    conn.close()


def get_delete_queue():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM delete_queue WHERE status = 'pending' ORDER BY size DESC").fetchall()
    conn.close()
    return rows


def get_move_queue():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM move_queue WHERE status = 'pending' ORDER BY size DESC").fetchall()
    conn.close()
    return rows


def update_queue_status(table, item_id, status):
    conn = get_connection()
    conn.execute(f"UPDATE {table} SET status = ? WHERE id = ?", (status, item_id))
    conn.commit()
    conn.close()


def delete_from_queue(table, item_ids):
    """Remove specific items from a queue by ID."""
    if not item_ids:
        return
    conn = get_connection()
    placeholders = ",".join("?" * len(item_ids))
    conn.execute(f"DELETE FROM {table} WHERE id IN ({placeholders})", list(item_ids))
    conn.commit()
    conn.close()


def clear_queue(table):
    conn = get_connection()
    conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()
