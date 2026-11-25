"""DestoService: runs scripts in tmux sessions and tracks them in Redis, independent of any UI.

The web dashboard (desto.app) and the terminal UI (desto.tui) are both thin front ends on top
of this class. It never talks to a UI directly: user-facing messages go through ``notify``,
and ``on_sessions_changed`` tells the front end that the sessions list changed.
"""

import getpass
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

from desto.app.config import config as ui_settings
from desto.core.formatting import ScheduledJobRow, SessionRow, count_by_category, decode_hash, metrics_key, scheduled_job_rows, session_rows, summarize_jobs
from desto.core.scheduled_jobs import ScheduledJobsMixin
from desto.core.session_metrics import read_history, read_summaries
from desto.redis.client import DestoRedisClient
from desto.redis.desto_manager import DestoManager
from desto.redis.job_manager import JobManager
from desto.redis.models import SessionStatus
from desto.redis.pubsub import SessionPubSub

# notify(message, level) with level one of "positive", "negative", "warning" or "info"
Notifier = Callable[[str, str], None]

_LOG_LEVELS = {"positive": "INFO", "info": "INFO", "warning": "WARNING", "negative": "ERROR"}


def _log_notifier(message: str, level: str) -> None:
    logger.log(_LOG_LEVELS.get(level, "INFO"), message)


@dataclass
class Snapshot:
    """Everything a sessions view shows, gathered in one go.

    rows: the sessions matching the status filter, newest first. counts covers all sessions.
    scheduled: the scheduled jobs still waiting to run.
    """

    rows: list[SessionRow] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=lambda: {"total": 0, "running": 0, "finished": 0, "failed": 0})
    scheduled: list[ScheduledJobRow] = field(default_factory=list)
    usage: dict[str, dict] = field(default_factory=dict)  # metrics key -> usage summary, see session_usage()


class DestoService(ScheduledJobsMixin):
    def __init__(self, log_dir=None, scripts_dir=None, notifier: Optional[Notifier] = None, instance_logger=None):
        scripts_dir_env = os.environ.get("DESTO_SCRIPTS_DIR")
        logs_dir_env = os.environ.get("DESTO_LOGS_DIR")
        self.SCRIPTS_DIR = Path(scripts_dir_env) if scripts_dir_env else Path(scripts_dir or Path.cwd() / "desto_scripts")
        self.LOG_DIR = Path(logs_dir_env) if logs_dir_env else Path(log_dir or Path.cwd() / "desto_logs")
        self.logger = instance_logger or logger
        self.notifier = notifier or _log_notifier

        try:
            self.LOG_DIR.mkdir(exist_ok=True)
            self.SCRIPTS_DIR.mkdir(exist_ok=True)
        except Exception as e:
            msg = f"Failed to create log/scripts directory: {e}"
            self.logger.error(msg)
            self.notify(msg, "negative")
            raise

        self.settings = ui_settings
        self.redis_client = DestoRedisClient(ui_settings.get("redis"))
        if not self.redis_client.is_connected():
            msg = "Redis is not available - cannot continue without Redis."
            logger.error(msg)
            self.notify(msg, "negative")
            raise RuntimeError(msg)

        # Optional SQLite store for long-term persistence
        sqlite_store = None
        sqlite_config = ui_settings.get("sqlite", {})
        if sqlite_config.get("enabled", False):
            from desto.redis.sqlite_store import SQLiteStore

            sqlite_store = SQLiteStore(db_path=sqlite_config.get("db_path") or None, enabled=True)
            logger.info("SQLite enabled for long-term session persistence")

        self.desto_manager = DestoManager(self.redis_client, sqlite_store=sqlite_store)
        self.pubsub = SessionPubSub(self.redis_client)
        self.job_manager = JobManager(self.redis_client)
        self.use_redis = True
        logger.info(f"desto service initialized - log_dir: {self.LOG_DIR}, scripts_dir: {self.SCRIPTS_DIR}")

    # --- Front-end hooks ------------------------------------------------------------

    def notify(self, message: str, level: str = "info") -> None:
        """Show a message to the user of whichever front end owns this service."""
        self.notifier(message, level)

    def on_sessions_changed(self) -> None:
        """Called after an action changed the sessions list; front ends override it to refresh."""

    @property
    def python_executable(self) -> str:
        return self.settings.get("script_settings", {}).get("python_executable", "python3")

    def telemetry_event(self, event_name: str, details: dict | None = None) -> None:
        """Emit a lightweight telemetry/log event as structured JSON (local log only, no network)."""
        try:
            payload = {
                "event": event_name,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "user": getpass.getuser(),
                "details": details or {},
            }
            logger.info("telemetry: {}".format(json.dumps(payload)))
        except Exception:
            logger.debug("Failed to emit telemetry event", exc_info=True)

    # --- tmux and Redis state -------------------------------------------------------

    def is_tmux_session_active(self, session_name: str) -> bool:
        """Check if a tmux session with the given name exists."""
        try:
            result = subprocess.run(["tmux", "has-session", "-t", session_name], capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error checking tmux session '{session_name}': {e}")
            return False

    def check_sessions(self):
        """Return the active tmux sessions as {name: details}."""
        active_sessions = {}
        result = subprocess.run(
            [
                "tmux",
                "list-sessions",
                "-F",
                "#{session_id}:#{session_name}:#{session_created}:#{session_attached}:#{session_windows}:#{session_group}:#{session_group_size}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                session_info = line.split(":")
                active_sessions[session_info[1]] = {
                    "id": session_info[0],
                    "name": session_info[1],
                    "created": int(session_info[2]),  # Epoch time
                    "attached": session_info[3] == "1",
                    "windows": int(session_info[4]),
                    "group": session_info[5] if session_info[5] else None,
                    "group_size": int(session_info[6]) if session_info[6] else 1,
                }
            logger.debug(f"Found {len(active_sessions)} active tmux sessions")
        return active_sessions

    def get_all_sessions_status(self):
        """Return every session known to Redis (any status), plus tmux sessions Redis does not know."""
        sessions = {}
        try:
            for key in list(self.redis_client.redis.scan_iter(match="desto:session:*")):
                try:
                    session_data = self.redis_client.redis.hgetall(key)
                    if session_data:
                        session_info = decode_hash(session_data)
                        sessions[session_info.get("session_name", key.replace("desto:session:", ""))] = session_info
                except Exception as e:
                    logger.error(f"Error processing session key {key}: {e}")
        except Exception as e:
            logger.error(f"Error getting all sessions from Redis: {e}")
        for sname, sdata in self.check_sessions().items():
            sessions.setdefault(sname, sdata)
        return sessions

    def _job_info_by_session(self):
        """Read every job once and summarise it per session id as {session_id: {"status", "exit_code", "command"}}."""
        result = {}
        try:
            r = self.redis_client.redis
            keys = list(r.scan_iter(match="desto:job:*", count=500))
            if not keys:
                return result
            pipe = r.pipeline(transaction=False)
            for key in keys:
                pipe.hgetall(key)
            jobs_by_session = {}
            for data in pipe.execute():
                if data:
                    job = decode_hash(data)
                    jobs_by_session.setdefault(job.get("session_id", ""), []).append(job)
        except Exception as e:
            logger.debug(f"Could not read jobs from Redis: {e}")
            return result
        for session_id, jobs in jobs_by_session.items():
            result[session_id] = summarize_jobs(jobs)
        return result

    def snapshot(self, status_filter: Optional[str] = None) -> Snapshot:
        """Gather sessions, per-category counts and scheduled jobs for a sessions view."""
        sessions_status = self.get_all_sessions_status()
        tmux_active = set(self.check_sessions().keys())
        job_info = self._job_info_by_session()
        all_rows = session_rows(sessions_status, tmux_active, job_info)
        rows = [row for row in all_rows if not status_filter or row.category == status_filter]
        return Snapshot(
            rows=rows,
            counts=count_by_category(all_rows),
            scheduled=scheduled_job_rows(self._get_scheduled_jobs_with_metadata()),
            usage=self.session_usage(rows),
        )

    def session_usage(self, rows) -> dict:
        """{metrics key: usage summary} for the given SessionRows, read in one Redis round trip."""
        try:
            return read_summaries(self.redis_client.redis, [metrics_key(row.name, row.session) for row in rows])
        except Exception as e:
            logger.debug(f"Could not read session usage: {e}")
            return {}

    def session_usage_history(self, row) -> list[dict]:
        """A session's usage points, oldest first (see desto.core.session_metrics.read_history)."""
        key = metrics_key(row.name, row.session)
        if not key:
            return []
        try:
            return read_history(self.redis_client.redis, key)
        except Exception as e:
            logger.debug(f"Could not read usage history of {row.name}: {e}")
            return []

    def _count_by_category(self, sessions_status, tmux_active=None, job_info=None):
        if tmux_active is None:
            tmux_active = set(self.check_sessions().keys())
        return count_by_category(session_rows(sessions_status, tmux_active, job_info or {}))

    def get_unique_session_name(self, base_name: str) -> str:
        """Return base_name, or base_name-2, -3, ... if it is taken by tmux or Redis."""
        taken = set(self.check_sessions().keys()) | self._redis_session_names()
        if base_name not in taken:
            return base_name
        idx = 2
        while f"{base_name}-{idx}" in taken:
            idx += 1
        return f"{base_name}-{idx}"

    def _redis_session_names(self) -> set:
        try:
            return {s.session_name for s in self.desto_manager.session_manager.list_all_sessions() if getattr(s, "session_name", None)}
        except Exception:
            return set()

    def get_log_file(self, session_name):
        return self.LOG_DIR / f"{session_name}.log"

    def get_script_file(self, script_name):
        return self.SCRIPTS_DIR / script_name

    # --- Launching ------------------------------------------------------------------

    def start_tmux_session(self, session_name, command, instance_logger=None) -> bool:
        """Start command in a new detached tmux session, logging its output to <LOG_DIR>/<session_name>.log.

        Refuses names already used by a scheduled session or an active tmux session.
        Returns True if the session started.
        """
        for session in self.desto_manager.session_manager.list_all_sessions():
            status = getattr(session, "status", None)
            if getattr(session, "session_name", None) == session_name and (status == SessionStatus.SCHEDULED or str(status).lower() == "scheduled"):
                msg = f"Session '{session_name}' is already scheduled. Cannot start a new session with the same name until it runs or is cancelled."
                logger.error(msg)
                self.notify(msg, "negative")
                return False

        if session_name in self.check_sessions():
            msg = f"Session '{session_name}' already exists. Please choose a different name."
            logger.error(msg)
            self.notify(msg, "negative")
            return False

        logger.info(f"Starting tmux session '{session_name}' with command: {command}")
        log_file = self.get_log_file(session_name)
        try:
            log_file.parent.mkdir(exist_ok=True)
        except Exception as e:
            msg = f"Failed to create log directory '{log_file.parent}': {e}"
            logger.error(msg)
            self.notify(msg, "negative")
            return False

        try:
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_name, "bash", "-c", self._logged_command(session_name, command, log_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            msg = f"Failed to start session '{session_name}': {e.stderr.strip() if e.stderr else 'No stderr output'}"
            logger.warning(msg)
            self.notify(msg, "negative")
            return False
        except Exception as e:
            msg = f"Unexpected error starting session '{session_name}': {str(e)}"
            logger.error(msg)
            self.notify(msg, "negative")
            return False

        logger.info(f"Tmux session '{session_name}' started successfully.")
        self.notify(f"Tmux session '{session_name}' started.", "positive")
        self.desto_manager.start_session_with_job(session_name=session_name, command=command, script_path=command)
        self._start_redis_monitoring(session_name)
        return True

    def _logged_command(self, session_name, command, log_file) -> str:
        """Wrap command so its output, start/finish banners and exit code end up in log_file and Redis."""
        quoted_log_file = shlex.quote(str(log_file))
        if log_file.exists():
            pre = f'printf \'\\n---- NEW SESSION (%s) -----\\n\' "$(date \'+%Y-%m-%d %H:%M:%S\')" >> {quoted_log_file} && printf "\\n=== SCRIPT STARTING at %s ===\\n" "$(date)" >> {quoted_log_file}'
        else:
            pre = f'printf "\\n=== SCRIPT STARTING at %s ===\\n" "$(date)" > {quoted_log_file}'
        return f"""
    {pre}
    ({command}) >> {quoted_log_file} 2>&1
    SCRIPT_EXIT_CODE=$?
    printf "\\n=== SCRIPT FINISHED at %s (exit code: $SCRIPT_EXIT_CODE) ===\\n" "$(date)" >> {quoted_log_file}
    {self.get_job_completion_command(session_name, use_variable=True)}
    """.strip()

    def _start_redis_monitoring(self, session_name):
        """Keep the session's heartbeat fresh and mark it finished once its tmux session is gone."""

        def monitor():
            time.sleep(2)  # Give the session a moment to start
            while True:
                try:
                    if session_name not in self.check_sessions():
                        self.desto_manager.finish_session(session_name, exit_code=0)
                        logger.info(f"Session {session_name} monitoring ended - tmux session terminated")
                        break
                    self.desto_manager.update_heartbeat(session_name)
                    time.sleep(5)
                except Exception as e:
                    self.logger.error(f"Error monitoring session {session_name}: {e}")
                    time.sleep(10)

        threading.Thread(target=monitor, daemon=True).start()

    def get_job_completion_command(self, session_name, use_variable=False):
        """Shell snippet that records the job's exit code in Redis.

        Args:
            session_name: Name of the session
            use_variable: If True, uses $SCRIPT_EXIT_CODE variable instead of $?
        """
        exit_code_ref = "$SCRIPT_EXIT_CODE" if use_variable else "$?"
        if not self.use_redis:
            return f"touch '{self.LOG_DIR}/{session_name}.finished'"
        # The bundled hook module works from an installed package, not just a source checkout
        return f"{shlex.quote(sys.executable)} -m desto.hooks.mark_job_finished {shlex.quote(session_name)} {exit_code_ref}"

    def rerun_session(self, session_name, command) -> bool:
        """Launch the same command again in a new session (name-2, name-3, ...)."""
        if not command:
            self.notify(f"No command recorded for '{session_name}', cannot re-run.", "warning")
            return False
        base = session_name
        match = re.match(r"^(.*)-(\d+)$", session_name)
        if match and match.group(1) in set(self.check_sessions().keys()) | self._redis_session_names():
            base = match.group(1)
        started = self.start_tmux_session(self.get_unique_session_name(base), command)
        self.on_sessions_changed()
        return started

    def run_favorite(self, favorite_id, name, command) -> Optional[str]:
        """Run a favorite command in a new 'fav-<name>' session and count the use. Returns the session name if it started."""
        session_name = self.get_unique_session_name(f"fav-{name}")
        self.desto_manager.favorites_manager.increment_usage(favorite_id)
        return session_name if self.start_tmux_session(session_name, command) else None

    def list_favorites(self, query: str = ""):
        """Favorites matching query (all of them when empty), most used first."""
        favorites = self.desto_manager.favorites_manager
        return favorites.search_favorites(query) if query else favorites.list_favorites(sort_by="use_count")

    def clear_all_favorites(self) -> int:
        """Delete every favorite from Redis (and SQLite when enabled). Returns how many were deleted."""
        deleted = self.desto_manager.favorites_manager.delete_all_favorites()
        store = getattr(self.desto_manager, "sqlite_store", None)
        if store and store.enabled:
            try:
                conn = store._get_connection()
                conn.execute("DELETE FROM favorites")
                conn.commit()
            except Exception as e:
                logger.debug(f"Could not clear favorites from SQLite: {e}")
        return deleted

    # --- Stopping and cleaning up ---------------------------------------------------

    def kill_session(self, session_name) -> bool:
        """Kill a tmux session by name."""
        self.logger.info(f"Attempting to kill session: '{session_name}'")
        result = subprocess.run(["tmux", "kill-session", "-t", shlex.quote(session_name)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            msg = f"Session '{session_name}' killed successfully."
            self.logger.info(msg)
            self.notify(msg, "positive")
            return True
        msg = f"Failed to kill session '{session_name}': {result.stderr}"
        self.logger.warning(msg)
        self.notify(msg, "negative")
        return False

    def kill_tmux_session(self, session_name) -> bool:
        """Kill a tmux session by name, only reporting failures."""
        try:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=True)
            logger.info(f"Successfully killed tmux session '{session_name}'")
            return True
        except subprocess.CalledProcessError as e:
            msg = f"Failed to kill tmux session '{session_name}': {e}"
            logger.warning(msg)
            self.notify(msg, "negative")
            return False

    def kill_all_sessions(self):
        """Kill all active tmux sessions. Returns (success_count, total_count, error_messages)."""
        sessions_status = self.check_sessions()
        total_count = len(sessions_status)
        if total_count == 0:
            msg = "No active tmux sessions found."
            logger.info(msg)
            self.notify(msg, "info")
            return (0, 0, [])

        logger.info(f"Attempting to kill {total_count} tmux sessions")
        success_count = 0
        error_messages = []
        for session_name in sessions_status.keys():
            try:
                subprocess.run(["tmux", "kill-session", "-t", session_name], check=True)
                success_count += 1
                logger.info(f"Successfully killed session: {session_name}")
            except subprocess.CalledProcessError as e:
                error_messages.append(f"Failed to kill session '{session_name}': {e}")
                logger.warning(error_messages[-1])
            except Exception as e:
                error_messages.append(f"Unexpected error killing session '{session_name}': {str(e)}")
                logger.error(error_messages[-1])
        logger.info(f"Killed {success_count}/{total_count} sessions")
        return (success_count, total_count, error_messages)

    def kill_all_sessions_and_jobs(self):
        """Kill all tmux sessions and scheduled jobs.

        Returns (session_success, session_total, job_success, job_total, all_error_messages).
        """
        session_success, session_total, session_errors = self.kill_all_sessions()
        job_success, job_total, job_errors = self.kill_scheduled_jobs()
        return (session_success, session_total, job_success, job_total, session_errors + job_errors)

    def kill_all_and_notify(self) -> None:
        """Kill all sessions and scheduled jobs, then notify one summary message."""
        session_success, session_total, job_success, job_total, error_messages = self.kill_all_sessions_and_jobs()
        results = []
        if session_total > 0:
            results.append(f"Successfully cleared all {session_total} sessions" if session_success == session_total else f"Cleared {session_success}/{session_total} sessions")
        if job_total > 0:
            results.append(f"Successfully cancelled all {job_total} scheduled jobs" if job_success == job_total else f"Cancelled {job_success}/{job_total} scheduled jobs")
        if not results:
            results.append("No items to clear")
        msg = ". ".join(results) + "."
        if error_messages:
            msg += f" Errors: {'; '.join(error_messages[:3])}"
            logger.warning(msg)
            self.notify(msg, "warning")
        else:
            logger.success(msg)
            self.notify(msg, "positive")
        self.on_sessions_changed()

    def clear_session(self, session_name) -> bool:
        """Delete the session's log file and its Redis record. Returns True if both went."""
        log_file = self.get_log_file(session_name)
        log_deleted = False
        try:
            if log_file.exists():
                log_file.unlink()
                log_deleted = True
                logger.info(f"Deleted log file for session: {session_name}")
        except Exception as e:
            logger.warning(f"Failed to delete log file for session {session_name}: {e}")

        redis_deleted = False
        try:
            found_key = self._find_session_key(session_name)
            if found_key:
                if self.redis_client.redis.delete(found_key):
                    redis_deleted = True
                    logger.info(f"Deleted Redis session: {session_name} (key: {found_key})")
            else:
                logger.warning(f"Could not find Redis key for session '{session_name}'")
        except Exception as e:
            logger.warning(f"Failed to delete Redis session {session_name}: {e}")

        if log_deleted and redis_deleted:
            self.notify(f"Session '{session_name}' cleared (log and Redis entry deleted)", "positive")
        elif log_deleted:
            self.notify(f"Session '{session_name}' log deleted, but failed to remove from Redis", "warning")
        elif redis_deleted:
            self.notify(f"Session '{session_name}' removed from Redis, but log file not found/deleted", "warning")
        else:
            self.notify(f"Failed to clear session '{session_name}' (see logs)", "negative")
        self.on_sessions_changed()
        return log_deleted and redis_deleted

    def _find_session_key(self, session_name):
        """Return the Redis key of the session hash whose display name is session_name, or None."""
        for key in list(self.redis_client.redis.scan_iter(match="desto:session:*")):
            session_data = self.redis_client.redis.hgetall(key)
            if session_data:
                session_info = decode_hash(session_data)
                if session_info.get("session_name", key.replace("desto:session:", "")) == session_name:
                    return key
        return None

    def clear_session_history(self) -> int:
        """Delete every session record from Redis. Returns how many were deleted."""
        try:
            all_keys = list(self.redis_client.redis.scan_iter(match="desto:session:*"))
            if not all_keys:
                self.notify("No session history to clear", "info")
                return 0
            deleted_count = 0
            for key in all_keys:
                try:
                    self.redis_client.redis.delete(key)
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Error deleting session key {key}: {e}")
            if deleted_count > 0:
                msg = f"Successfully cleared {deleted_count} session record(s) from history"
                logger.info(msg)
                self.notify(msg, "positive")
                self.on_sessions_changed()
            else:
                self.notify("No sessions were cleared", "warning")
            return deleted_count
        except Exception as e:
            error_msg = f"Error clearing session history: {e}"
            logger.error(error_msg)
            self.notify(error_msg, "negative")
            return 0

    def clear_log_files(self) -> int:
        """Delete every *.log and *.finished file in the logs directory. Returns how many were deleted."""
        log_dir = self.LOG_DIR
        if not log_dir.exists():
            self.notify("Logs directory not found", "warning")
            return 0
        try:
            all_files = list(log_dir.glob("*.log")) + list(log_dir.glob("*.finished"))
            if not all_files:
                self.notify("No log files found to clear", "info")
                return 0
            deleted_count = 0
            errors = []
            for file_path in all_files:
                try:
                    file_path.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted log file: {file_path}")
                except Exception as e:
                    errors.append(f"Failed to delete {file_path.name}: {str(e)}")
                    logger.error(errors[-1])
            if deleted_count > 0:
                msg = f"Successfully deleted {deleted_count} log file(s)"
                if errors:
                    msg += f" ({len(errors)} errors)"
                logger.info(msg)
                self.notify(msg, "positive")
                self.on_sessions_changed()
            if errors:
                error_summary = "; ".join(errors[:3])
                if len(errors) > 3:
                    error_summary += f" (+{len(errors) - 3} more)"
                self.notify(f"Errors: {error_summary}", "warning")
            return deleted_count
        except Exception as e:
            error_msg = f"Error clearing log files: {e}"
            logger.error(error_msg)
            self.notify(error_msg, "negative")
            return 0
