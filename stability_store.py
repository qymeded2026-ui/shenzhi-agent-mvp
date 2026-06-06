import json
import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = Path(os.getenv("SHENZHI_RUNTIME_DIR", BASE_DIR / "runtime"))
DB_PATH = RUNTIME_DIR / "shenzhi_sessions.db"
LOG_PATH = RUNTIME_DIR / "shenzhi_app.log"
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _backup_dir() -> Path:
    return RUNTIME_DIR / "backups"


def _connect() -> sqlite3.Connection:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            chat_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    return connection


def log_event(event: str, **fields) -> None:
    """Write one compact JSON line so failures remain inspectable after a crash."""
    payload = {"time": _now(), "event": event, **fields}
    with _LOCK:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def save_chat_session(chat_id: str, chat: Dict) -> bool:
    payload_json = json.dumps(chat, ensure_ascii=False, default=str)
    with _LOCK, _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO chat_sessions (chat_id, payload_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            WHERE chat_sessions.payload_json <> excluded.payload_json
            """,
            (chat_id, payload_json, _now()),
        )
    return cursor.rowcount > 0


def save_all_chat_sessions(chat_sessions: Dict[str, Dict], active_chat_id: str = "") -> int:
    changed_rows = 0
    with _LOCK, _connect() as connection:
        for chat_id, chat in chat_sessions.items():
            cursor = connection.execute(
                """
                INSERT INTO chat_sessions (chat_id, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                WHERE chat_sessions.payload_json <> excluded.payload_json
                """,
                (
                    chat_id,
                    json.dumps(chat, ensure_ascii=False, default=str),
                    _now(),
                ),
            )
            changed_rows += max(0, cursor.rowcount)
        if active_chat_id:
            cursor = connection.execute(
                """
                INSERT INTO app_meta (key, value) VALUES ('active_chat_id', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                WHERE app_meta.value <> excluded.value
                """,
                (active_chat_id,),
            )
            changed_rows += max(0, cursor.rowcount)
    return changed_rows


def load_chat_sessions(limit: int = 50) -> Dict[str, Dict]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT chat_id, payload_json
            FROM chat_sessions
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    sessions = {}
    for chat_id, payload_json in reversed(rows):
        try:
            sessions[chat_id] = json.loads(payload_json)
        except json.JSONDecodeError:
            log_event("session_load_skipped", chat_id=chat_id, reason="invalid_json")
    return sessions


def delete_chat_session(chat_id: str) -> None:
    with _LOCK, _connect() as connection:
        connection.execute("DELETE FROM chat_sessions WHERE chat_id = ?", (chat_id,))


def load_active_chat_id() -> Optional[str]:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT value FROM app_meta WHERE key = 'active_chat_id'"
        ).fetchone()
    return row[0] if row else None


def backup_database(retention: int = 10) -> Optional[Path]:
    """Create a consistent SQLite backup without exposing chat contents in logs."""
    with _LOCK:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        backup_dir = _backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)
        with _connect() as source:
            backup_path = backup_dir / (
                f"shenzhi_sessions_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.db"
            )
            with sqlite3.connect(backup_path) as target:
                source.backup(target)

        backup_files = sorted(
            backup_dir.glob("shenzhi_sessions_*.db"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for old_backup in backup_files[max(1, retention) :]:
            old_backup.unlink(missing_ok=True)
        log_event("database_backup_created", filename=backup_path.name)
        return backup_path


def ensure_periodic_backup(
    *,
    retention: int = 10,
    min_interval_seconds: int = 6 * 60 * 60,
) -> Optional[Path]:
    """Keep lightweight periodic backups while avoiding a copy on every rerun."""
    with _LOCK:
        backup_dir = _backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_files = sorted(
            backup_dir.glob("shenzhi_sessions_*.db"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if backup_files:
            elapsed = time.time() - backup_files[0].stat().st_mtime
            if elapsed < min_interval_seconds:
                return backup_files[0]
    return backup_database(retention=retention)
