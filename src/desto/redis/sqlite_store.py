"""SQLite-based long-term persistence store for desto sessions, jobs, and favorites.

This module provides an optional SQLite backend that complements Redis by offering
durable, long-term storage of session history. While Redis handles real-time state
and pub/sub with auto-expiring keys (7 days), SQLite persists data indefinitely.

Enable via the SQLITE_ENABLED environment variable or config setting.
"""

import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from .models import DestoJob, DestoSession, FavoriteCommand, JobStatus, SessionStatus

# Default database path
_DEFAULT_DB_DIR = os.getenv("DESTO_DATA_DIR", os.path.join(os.getcwd(), "desto_data"))
_DEFAULT_DB_PATH = os.path.join(_DEFAULT_DB_DIR, "desto.db")


class SQLiteStore:
    """SQLite-based persistent store for long-term session and job history.

    This store is designed to work alongside Redis: Redis handles real-time state,
    pub/sub, and short-term caching, while SQLite provides durable long-term storage.

    Usage:
        store = SQLiteStore(db_path="/path/to/desto.db")
        store.save_session(session)
        sessions = store.get_all_sessions(limit=100)
    """

    def __init__(self, db_path: Optional[str] = None, enabled: bool = True):
        """Initialize the SQLite store.

        Args:
            db_path: Path to the SQLite database file. Defaults to desto_data/desto.db.
            enabled: Whether the store is active. If False, all operations are no-ops.
        """
        self.enabled = enabled
        self.db_path = db_path or os.getenv("SQLITE_DB_PATH", _DEFAULT_DB_PATH)
        self._local = threading.local()

        if not self.enabled:
            logger.info("SQLite store is disabled")
            return

        # Ensure parent directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            Path(db_dir).mkdir(parents=True, exist_ok=True)

        # Initialize schema
        self._initialize_schema()
        logger.info(f"SQLite store initialized at {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = sqlite3.connect(self.db_path, timeout=30)
            self._local.connection.row_factory = sqlite3.Row
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            self._local.connection.execute("PRAGMA foreign_keys=ON")
        return self._local.connection

    def _initialize_schema(self):
        """Create database tables if they don't exist."""
        conn = self._get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                session_name TEXT NOT NULL,
                tmux_session_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'starting',
                start_time TEXT,
                end_time TEXT,
                last_heartbeat TEXT,
                job_ids TEXT DEFAULT '',
                tmux_active INTEGER DEFAULT 0,
                at_job_id TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                command TEXT NOT NULL DEFAULT '',
                script_path TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'queued',
                start_time TEXT,
                end_time TEXT,
                exit_code INTEGER,
                error_message TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS favorites (
                favorite_id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                command TEXT NOT NULL DEFAULT '',
                created_at TEXT,
                last_used_at TEXT,
                use_count INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
            CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON sessions(start_time);
            CREATE INDEX IF NOT EXISTS idx_sessions_session_name ON sessions(session_name);
            CREATE INDEX IF NOT EXISTS idx_jobs_session_id ON jobs(session_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_favorites_name ON favorites(name);
        """)
        conn.commit()

    # ─── Session Operations ───────────────────────────────────────────────

    def save_session(self, session: DestoSession) -> bool:
        """Save or update a session record.

        Args:
            session: DestoSession object to persist.

        Returns:
            True if successful, False otherwise.
        """
        if not self.enabled:
            return False

        try:
            conn = self._get_connection()
            conn.execute(
                """
                INSERT INTO sessions (session_id, session_name, tmux_session_name, status,
                                      start_time, end_time, last_heartbeat, job_ids,
                                      tmux_active, at_job_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(session_id) DO UPDATE SET
                    session_name=excluded.session_name,
                    tmux_session_name=excluded.tmux_session_name,
                    status=excluded.status,
                    start_time=excluded.start_time,
                    end_time=excluded.end_time,
                    last_heartbeat=excluded.last_heartbeat,
                    job_ids=excluded.job_ids,
                    tmux_active=excluded.tmux_active,
                    at_job_id=excluded.at_job_id,
                    updated_at=datetime('now')
                """,
                (
                    session.session_id,
                    session.session_name,
                    session.tmux_session_name,
                    session.status.value,
                    session.start_time.isoformat() if session.start_time else None,
                    session.end_time.isoformat() if session.end_time else None,
                    session.last_heartbeat.isoformat() if session.last_heartbeat else None,
                    ",".join(session.job_ids),
                    1 if session.tmux_active else 0,
                    session.at_job_id or "",
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"SQLite: Failed to save session {session.session_id}: {e}")
            return False

    def get_session(self, session_id: str) -> Optional[DestoSession]:
        """Get a session by ID.

        Args:
            session_id: The session UUID.

        Returns:
            DestoSession if found, None otherwise.
        """
        if not self.enabled:
            return None

        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_session(row)
            return None
        except Exception as e:
            logger.error(f"SQLite: Failed to get session {session_id}: {e}")
            return None

    def get_session_by_name(self, session_name: str) -> Optional[DestoSession]:
        """Get the most recent session by name.

        Args:
            session_name: The session name.

        Returns:
            DestoSession if found, None otherwise.
        """
        if not self.enabled:
            return None

        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE session_name = ? ORDER BY created_at DESC LIMIT 1",
                (session_name,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_session(row)
            return None
        except Exception as e:
            logger.error(f"SQLite: Failed to get session by name {session_name}: {e}")
            return None

    def get_all_sessions(self, limit: int = 100, offset: int = 0, status: Optional[str] = None) -> List[DestoSession]:
        """Get all sessions with pagination.

        Args:
            limit: Maximum number of sessions to return.
            offset: Number of sessions to skip.
            status: Optional status filter.

        Returns:
            List of DestoSession objects.
        """
        if not self.enabled:
            return []

        try:
            conn = self._get_connection()
            if status:
                cursor = conn.execute(
                    "SELECT * FROM sessions WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (status, limit, offset),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            return [self._row_to_session(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"SQLite: Failed to get sessions: {e}")
            return []

    def get_session_count(self, status: Optional[str] = None) -> int:
        """Get total number of sessions.

        Args:
            status: Optional status filter.

        Returns:
            Number of sessions matching the criteria.
        """
        if not self.enabled:
            return 0

        try:
            conn = self._get_connection()
            if status:
                cursor = conn.execute("SELECT COUNT(*) FROM sessions WHERE status = ?", (status,))
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM sessions")
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"SQLite: Failed to count sessions: {e}")
            return 0

    def search_sessions(self, name_query: str, limit: int = 100, offset: int = 0, status: Optional[str] = None) -> List[DestoSession]:
        """Search sessions by name using SQL LIKE.

        Args:
            name_query: Substring to match against session_name.
            limit: Maximum number of sessions to return.
            offset: Number of sessions to skip.
            status: Optional status filter.

        Returns:
            List of matching DestoSession objects.
        """
        if not self.enabled:
            return []

        try:
            conn = self._get_connection()
            pattern = f"%{name_query}%"
            if status:
                cursor = conn.execute(
                    "SELECT * FROM sessions WHERE session_name LIKE ? AND status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (pattern, status, limit, offset),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM sessions WHERE session_name LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (pattern, limit, offset),
                )
            return [self._row_to_session(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"SQLite: Failed to search sessions: {e}")
            return []

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its associated jobs.

        Args:
            session_id: The session UUID to delete.

        Returns:
            True if successful, False otherwise.
        """
        if not self.enabled:
            return False

        try:
            conn = self._get_connection()
            conn.execute("DELETE FROM jobs WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"SQLite: Failed to delete session {session_id}: {e}")
            return False

    # ─── Job Operations ───────────────────────────────────────────────────

    def save_job(self, job: DestoJob) -> bool:
        """Save or update a job record.

        Args:
            job: DestoJob object to persist.

        Returns:
            True if successful, False otherwise.
        """
        if not self.enabled:
            return False

        try:
            conn = self._get_connection()
            conn.execute(
                """
                INSERT INTO jobs (job_id, session_id, command, script_path, status,
                                  start_time, end_time, exit_code, error_message, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(job_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    command=excluded.command,
                    script_path=excluded.script_path,
                    status=excluded.status,
                    start_time=excluded.start_time,
                    end_time=excluded.end_time,
                    exit_code=excluded.exit_code,
                    error_message=excluded.error_message,
                    updated_at=datetime('now')
                """,
                (
                    job.job_id,
                    job.session_id,
                    job.command,
                    job.script_path,
                    job.status.value,
                    job.start_time.isoformat() if job.start_time else None,
                    job.end_time.isoformat() if job.end_time else None,
                    job.exit_code,
                    job.error_message or "",
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"SQLite: Failed to save job {job.job_id}: {e}")
            return False

    def get_job(self, job_id: str) -> Optional[DestoJob]:
        """Get a job by ID.

        Args:
            job_id: The job UUID.

        Returns:
            DestoJob if found, None otherwise.
        """
        if not self.enabled:
            return None

        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_job(row)
            return None
        except Exception as e:
            logger.error(f"SQLite: Failed to get job {job_id}: {e}")
            return None

    def get_jobs_for_session(self, session_id: str) -> List[DestoJob]:
        """Get all jobs for a session.

        Args:
            session_id: The session UUID.

        Returns:
            List of DestoJob objects.
        """
        if not self.enabled:
            return []

        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT * FROM jobs WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            )
            return [self._row_to_job(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"SQLite: Failed to get jobs for session {session_id}: {e}")
            return []

    # ─── Favorites Operations ─────────────────────────────────────────────

    def save_favorite(self, favorite: FavoriteCommand) -> bool:
        """Save or update a favorite command.

        Args:
            favorite: FavoriteCommand object to persist.

        Returns:
            True if successful, False otherwise.
        """
        if not self.enabled:
            return False

        try:
            conn = self._get_connection()
            conn.execute(
                """
                INSERT INTO favorites (favorite_id, name, command, created_at,
                                       last_used_at, use_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(favorite_id) DO UPDATE SET
                    name=excluded.name,
                    command=excluded.command,
                    last_used_at=excluded.last_used_at,
                    use_count=excluded.use_count,
                    updated_at=datetime('now')
                """,
                (
                    favorite.favorite_id,
                    favorite.name,
                    favorite.command,
                    favorite.created_at.isoformat() if favorite.created_at else None,
                    favorite.last_used_at.isoformat() if favorite.last_used_at else None,
                    favorite.use_count,
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"SQLite: Failed to save favorite {favorite.favorite_id}: {e}")
            return False

    def get_all_favorites(self) -> List[FavoriteCommand]:
        """Get all favorite commands.

        Returns:
            List of FavoriteCommand objects.
        """
        if not self.enabled:
            return []

        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM favorites ORDER BY use_count DESC, name ASC")
            return [self._row_to_favorite(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"SQLite: Failed to get favorites: {e}")
            return []

    def delete_favorite(self, favorite_id: str) -> bool:
        """Delete a favorite command.

        Args:
            favorite_id: The favorite UUID to delete.

        Returns:
            True if successful, False otherwise.
        """
        if not self.enabled:
            return False

        try:
            conn = self._get_connection()
            conn.execute("DELETE FROM favorites WHERE favorite_id = ?", (favorite_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"SQLite: Failed to delete favorite {favorite_id}: {e}")
            return False

    # ─── Utility Methods ──────────────────────────────────────────────────

    def clear_sessions_and_jobs(self) -> bool:
        """Clear all sessions and jobs from the store, keeping favorites intact.

        Returns:
            True if successful, False otherwise.
        """
        if not self.enabled:
            return False

        try:
            conn = self._get_connection()
            conn.executescript("""
                DELETE FROM jobs;
                DELETE FROM sessions;
            """)
            conn.commit()
            logger.warning("SQLite: All sessions and jobs cleared")
            return True
        except Exception as e:
            logger.error(f"SQLite: Failed to clear sessions/jobs: {e}")
            return False

    def clear_all(self) -> bool:
        """Clear all data from the store. Use with caution.

        Returns:
            True if successful, False otherwise.
        """
        if not self.enabled:
            return False

        try:
            conn = self._get_connection()
            conn.executescript("""
                DELETE FROM jobs;
                DELETE FROM sessions;
                DELETE FROM favorites;
            """)
            conn.commit()
            logger.warning("SQLite: All data cleared")
            return True
        except Exception as e:
            logger.error(f"SQLite: Failed to clear data: {e}")
            return False

    def get_stats(self) -> Dict[str, int]:
        """Get storage statistics.

        Returns:
            Dictionary with counts for sessions, jobs, and favorites.
        """
        if not self.enabled:
            return {"sessions": 0, "jobs": 0, "favorites": 0}

        try:
            conn = self._get_connection()
            sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            favorites = conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]
            return {"sessions": sessions, "jobs": jobs, "favorites": favorites}
        except Exception as e:
            logger.error(f"SQLite: Failed to get stats: {e}")
            return {"sessions": 0, "jobs": 0, "favorites": 0}

    def close(self):
        """Close the database connection for the current thread."""
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

    # ─── Private Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> DestoSession:
        """Convert a database row to a DestoSession object."""
        return DestoSession(
            session_id=row["session_id"],
            session_name=row["session_name"],
            tmux_session_name=row["tmux_session_name"],
            status=SessionStatus(row["status"]),
            start_time=datetime.fromisoformat(row["start_time"]) if row["start_time"] else None,
            end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
            last_heartbeat=datetime.fromisoformat(row["last_heartbeat"]) if row["last_heartbeat"] else None,
            job_ids=[jid for jid in row["job_ids"].split(",") if jid] if row["job_ids"] else [],
            tmux_active=bool(row["tmux_active"]),
            at_job_id=row["at_job_id"] or None,
        )

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> DestoJob:
        """Convert a database row to a DestoJob object."""
        return DestoJob(
            job_id=row["job_id"],
            session_id=row["session_id"],
            command=row["command"],
            script_path=row["script_path"],
            status=JobStatus(row["status"]),
            start_time=datetime.fromisoformat(row["start_time"]) if row["start_time"] else None,
            end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
            exit_code=row["exit_code"],
            error_message=row["error_message"] or None,
        )

    @staticmethod
    def _row_to_favorite(row: sqlite3.Row) -> FavoriteCommand:
        """Convert a database row to a FavoriteCommand object."""
        return FavoriteCommand(
            favorite_id=row["favorite_id"],
            name=row["name"],
            command=row["command"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            last_used_at=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None,
            use_count=row["use_count"],
        )
