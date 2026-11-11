"""TmuxManager: runs scripts in tmux sessions and tracks them in Redis.

This module holds the tmux/session lifecycle. The rest of the dashboard behaviour is
split by concern and mixed into TmuxManager:

- scheduled_jobs.ScheduledJobsMixin: 'at' jobs and the internal fallback scheduler
- sessions_dashboard.SessionsDashboardMixin: stats cards and sessions/scheduled tables
- session_dialogs.SessionDialogsMixin: confirmation dialogs, log viewer and clean-up
- session_format: pure formatting/classification helpers
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
from datetime import datetime
from pathlib import Path

from loguru import logger
from nicegui import ui

from desto.app.scheduled_jobs import ScheduledJobsMixin
from desto.app.session_dialogs import SessionDialogsMixin
from desto.app.session_format import decode_hash
from desto.app.sessions_dashboard import SessionsDashboardMixin
from desto.redis.client import DestoRedisClient
from desto.redis.desto_manager import DestoManager
from desto.redis.pubsub import SessionPubSub


class TmuxManager(SessionsDashboardMixin, SessionDialogsMixin, ScheduledJobsMixin):
    def __init__(self, ui_instance, instance_logger, log_dir=None, scripts_dir=None):
        if not ui_instance or not instance_logger:
            raise ValueError("ui_instance and instance_logger are required")

        scripts_dir_env = os.environ.get("DESTO_SCRIPTS_DIR")
        logs_dir_env = os.environ.get("DESTO_LOGS_DIR")
        self.SCRIPTS_DIR = Path(scripts_dir_env) if scripts_dir_env else Path(scripts_dir or Path.cwd() / "desto_scripts")
        self.LOG_DIR = Path(logs_dir_env) if logs_dir_env else Path(log_dir or Path.cwd() / "desto_logs")
        self.ui = ui_instance
        self.sessions_container = ui_instance.column().classes("w-full mt-5 gap-4")
        self.logger = instance_logger
        self.pause_updates = None  # Function to pause updates
        self.resume_updates = None  # Function to resume updates
        self.status_filter = None  # None, "running", "finished" or "failed"
        self._last_render_signature = None  # Skip re-rendering when nothing changed
        self._live_duration_labels = []  # (label, start datetime) for running sessions
        self._atd_cache = (0.0, True)  # (checked_at, is_running)

        # Ensure log and scripts directories exist
        try:
            self.LOG_DIR.mkdir(exist_ok=True)
            self.SCRIPTS_DIR.mkdir(exist_ok=True)
        except Exception as e:
            msg = f"Failed to create log/scripts directory: {e}"
            self.logger.error(msg)
            ui.notification(msg, type="negative")
            raise

        # Initialize Redis components with config
        from desto.app.config import config as ui_settings

        self.redis_client = DestoRedisClient(ui_settings.get("redis"))

        # Check if Redis is available
        if not self.redis_client.is_connected():
            msg = "Redis is not available - cannot continue without Redis."
            logger.error(msg)
            ui.notification(msg, type="negative")
            raise RuntimeError(msg)
        else:
            # Initialize optional SQLite store for long-term persistence
            sqlite_store = None
            sqlite_config = ui_settings.get("sqlite", {})
            if sqlite_config.get("enabled", False):
                from desto.redis.sqlite_store import SQLiteStore

                sqlite_store = SQLiteStore(
                    db_path=sqlite_config.get("db_path") or None,
                    enabled=True,
                )
                logger.info("SQLite enabled for long-term session persistence")

            self.desto_manager = DestoManager(self.redis_client, sqlite_store=sqlite_store)
            self.pubsub = SessionPubSub(self.redis_client)
            # Attach JobManager for UI access
            from desto.redis.job_manager import JobManager

            self.job_manager = JobManager(self.redis_client)
            logger.info("Redis enabled for session tracking")

        # For backward compatibility with tests
        self.sessions = {}
        # For backward compatibility - use_redis attribute
        self.use_redis = self.redis_client.is_connected()

        logger.info(f"TmuxManager initialized - log_dir: {self.LOG_DIR}, scripts_dir: {self.SCRIPTS_DIR}")

    def telemetry_event(self, event_name: str, details: dict | None = None) -> None:
        """Emit a lightweight telemetry/log event as structured JSON.

        This helper intentionally only logs locally (no external network calls).
        """
        try:
            payload = {
                "event": event_name,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "user": getpass.getuser(),
                "details": details or {},
            }
            # Use a recognizable prefix to make telemetry entries easy to grep
            logger.info("telemetry: {}".format(json.dumps(payload)))
        except Exception:
            # Never raise from telemetry
            logger.debug("Failed to emit telemetry event", exc_info=True)

    def is_tmux_session_active(self, session_name: str) -> bool:
        """Check if a tmux session with the given name exists."""
        try:
            result = subprocess.run(["tmux", "has-session", "-t", session_name], capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error checking tmux session '{session_name}': {e}")
            return False

    def check_sessions(self):
        """Check the status of existing tmux sessions with detailed information."""
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
            session_count = 0
            for line in result.stdout.splitlines():
                session_info = line.split(":")
                session_id = session_info[0]
                session_name = session_info[1]
                session_created = int(session_info[2])  # Epoch time
                session_attached = session_info[3] == "1"
                session_windows = int(session_info[4])
                session_group = session_info[5] if session_info[5] else None
                session_group_size = int(session_info[6]) if session_info[6] else 1

                active_sessions[session_name] = {
                    "id": session_id,
                    "name": session_name,
                    "created": session_created,
                    "attached": session_attached,
                    "windows": session_windows,
                    "group": session_group,
                    "group_size": session_group_size,
                }
                session_count += 1

            logger.debug(f"Found {session_count} active tmux sessions")

        return active_sessions

    def get_all_sessions_status(self):
        """Return a list of all sessions (active, finished, failed, scheduled) from Redis, similar to the history tab, but independent of it."""
        sessions = {}
        try:
            # Get all session keys from Redis
            all_keys = list(self.redis_client.redis.scan_iter(match="desto:session:*"))
            for key in all_keys:
                try:
                    session_id = key.replace("desto:session:", "")
                    session_data = self.redis_client.redis.hgetall(key)
                    if session_data:
                        session_info = decode_hash(session_data)
                        # Use session_name if present, else fallback to id
                        display_session_name = session_info.get("session_name", session_id)
                        sessions[display_session_name] = session_info
                except Exception as e:
                    logger.error(f"Error processing session key {key}: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error getting all sessions from Redis: {e}")
        # Add active tmux sessions not in Redis (edge case)
        active_tmux = self.check_sessions()
        for sname, sdata in active_tmux.items():
            if sname not in sessions:
                sessions[sname] = sdata
        return sessions

    def get_unique_session_name(self, base_name: str) -> str:
        """Generate a unique session name by appending an incrementing index if needed."""
        taken = set(self.check_sessions().keys())
        # Also include Redis session names (scheduled, starting, running)
        if self.desto_manager:
            try:
                for s in self.desto_manager.session_manager.list_all_sessions():
                    name = getattr(s, "session_name", None)
                    if name:
                        taken.add(name)
            except Exception:
                pass
        if base_name not in taken:
            return base_name
        idx = 2
        while f"{base_name}-{idx}" in taken:
            idx += 1
        return f"{base_name}-{idx}"

    def get_log_file(self, session_name):
        return self.LOG_DIR / f"{session_name}.log"

    def get_script_file(self, script_name):
        return self.SCRIPTS_DIR / script_name

    def clear_sessions_container(self):
        """Clears the sessions container."""
        self.sessions_container.clear()

    def add_to_sessions_container(self, content):
        """Adds content to the sessions container."""
        with self.sessions_container:
            content()

    def start_tmux_session(self, session_name, command, instance_logger):
        """Starts a new tmux session with the given name and command, redirecting output to a log file.
        Shows notifications for success or failure.
        Enhanced: Checks Redis for existing session with SCHEDULED status and notifies user if found.
        """
        # Check Redis for any session with the same name and SCHEDULED status (block before tmux check)
        if self.desto_manager:
            from desto.redis.models import SessionStatus

            all_sessions = self.desto_manager.session_manager.list_all_sessions()
            for session in all_sessions:
                status = getattr(session, "status", None)
                name = getattr(session, "session_name", None)
                logger.info(f"Checking Redis session: {name} with status {status}")
                # Accept both enum and string for status
                if name == session_name and (status == SessionStatus.SCHEDULED or (isinstance(status, str) and str(status).lower() == "scheduled")):
                    msg = f"Session '{session_name}' is already scheduled. Cannot start a new session with the same name until it runs or is cancelled."
                    logger.error(msg)
                    ui.notification(msg, type="negative")
                    return

        # Check if tmux session already exists
        existing_sessions = self.check_sessions()
        if session_name in existing_sessions:
            msg = f"Session '{session_name}' already exists. Please choose a different name."
            logger.error(msg)
            ui.notification(msg, type="negative")
            return

        logger.info(f"Starting tmux session '{session_name}' with command: {command}")

        log_file = self.get_log_file(session_name)
        try:
            log_file.parent.mkdir(exist_ok=True)
        except Exception as e:
            msg = f"Failed to create log directory '{log_file.parent}': {e}"
            logger.error(msg)
            ui.notification(msg, type="negative")
            return

        quoted_log_file = shlex.quote(str(log_file))
        append_mode = log_file.exists()

        # Enhanced logging: Create a comprehensive command that handles all logging properly

        # Build the enhanced command with proper logging using printf for better compatibility
        cmd_parts = []

        # Add session separator if appending
        if append_mode:
            separator = f"printf '\\n---- NEW SESSION (%s) -----\\n' \"$(date '+%Y-%m-%d %H:%M:%S')\" >> {quoted_log_file}"
            cmd_parts.append(separator)
            # Add pre-script logging (append mode)
            pre_script_log = f'printf "\\n=== SCRIPT STARTING at %s ===\\n" "$(date)" >> {quoted_log_file}'
            cmd_parts.append(pre_script_log)
        else:
            # For new log file, create it with the start logging
            pre_script_log = f'printf "\\n=== SCRIPT STARTING at %s ===\\n" "$(date)" > {quoted_log_file}'
            cmd_parts.append(pre_script_log)

        # Create a robust bash command that ensures logging and keep-alive work regardless of script outcome
        pre_script_commands = " && ".join(cmd_parts) if cmd_parts else ""
        bash_script = f"""
    {pre_script_commands}
    ({command}) >> {quoted_log_file} 2>&1
    SCRIPT_EXIT_CODE=$?
    printf "\\n=== SCRIPT FINISHED at %s (exit code: $SCRIPT_EXIT_CODE) ===\\n" "$(date)" >> {quoted_log_file}
    {self.get_job_completion_command(session_name, use_variable=True)}
    """.strip()

        full_command_for_tmux = bash_script

        try:
            subprocess.run(
                [
                    "tmux",
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "bash",
                    "-c",
                    full_command_for_tmux,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            msg = f"Tmux session '{session_name}' started successfully."
            logger.info(msg)
            ui.notification(f"Tmux session '{session_name}' started.", type="positive")

            # Track in Redis using new manager if available
            if self.desto_manager:
                session, job = self.desto_manager.start_session_with_job(session_name=session_name, command=command, script_path=command)
                logger.debug(f"Redis tracking started for session '{session_name}'")

            # Start background monitoring to detect when the tmux session ends
            self._start_redis_monitoring(session_name)

        except subprocess.CalledProcessError as e:
            error_output = e.stderr.strip() if e.stderr else "No stderr output"
            msg = f"Failed to start session '{session_name}': {error_output}"
            logger.warning(msg)
            ui.notification(msg, type="negative")
        except Exception as e:
            msg = f"Unexpected error starting session '{session_name}': {str(e)}"
            logger.error(msg)
            ui.notification(msg, type="negative")

    def _start_redis_monitoring(self, session_name):
        """Monitor tmux session and update Redis."""
        # Skip monitoring if Redis is not available
        if not self.desto_manager:
            return

        def monitor():
            # Give the session a moment to start up before monitoring
            time.sleep(2)
            logger.debug(f"Starting Redis monitoring for session {session_name}")

            while True:
                try:
                    # Check if tmux session still exists
                    sessions = self.check_sessions()
                    if session_name not in sessions:
                        # Session finished (entire tmux session ended)
                        if self.desto_manager:
                            self.desto_manager.finish_session(session_name, exit_code=0)
                        logger.info(f"Session {session_name} monitoring ended - tmux session terminated")
                        break

                    # Update heartbeat
                    if self.desto_manager:
                        self.desto_manager.update_heartbeat(session_name)
                        logger.debug(f"Updated heartbeat for session {session_name}")

                    time.sleep(5)
                except Exception as e:
                    self.logger.error(f"Error monitoring session {session_name}: {e}")
                    time.sleep(10)

        threading.Thread(target=monitor, daemon=True).start()

    def get_job_completion_command(self, session_name, use_variable=False):
        """Get the appropriate command to mark job completion.

        Args:
            session_name: Name of the session
            use_variable: If True, uses $SCRIPT_EXIT_CODE variable instead of $?
        """
        exit_code_ref = "$SCRIPT_EXIT_CODE" if use_variable else "$?"

        # If Redis is not available, fall back to file-based markers
        if not self.use_redis:
            return f"touch '{self.LOG_DIR}/{session_name}.finished'"

        # Use the bundled hook module so this works from an installed package, not just a source checkout
        return f"{shlex.quote(sys.executable)} -m desto.hooks.mark_job_finished {shlex.quote(session_name)} {exit_code_ref}"

    def rerun_session(self, session_name, command):
        """Launch the same command again in a new session (name-2, name-3, ...)."""
        if not command:
            ui.notification(f"No command recorded for '{session_name}', cannot re-run.", type="warning")
            return
        base = session_name
        match = re.match(r"^(.*)-(\d+)$", session_name)
        if match:
            known = set(self.check_sessions().keys())
            if self.desto_manager:
                try:
                    known.update(getattr(s, "session_name", "") for s in self.desto_manager.session_manager.list_all_sessions())
                except Exception:
                    pass
            if match.group(1) in known:
                base = match.group(1)
        new_name = self.get_unique_session_name(base)
        self.start_tmux_session(new_name, command, logger)
        self.update_sessions_status(force=True)

    def kill_session(self, session_name):
        """Kill a tmux session by name."""
        msg = f"Attempting to kill session: '{session_name}'"
        self.logger.info(msg)
        escaped_session_name = shlex.quote(session_name)
        result = subprocess.run(
            ["tmux", "kill-session", "-t", escaped_session_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0:
            msg = f"Session '{session_name}' killed successfully."
            self.logger.info(msg)  # Changed from logger.success to logger.info
            self.ui.notification(msg, type="positive")
        else:
            msg = f"Failed to kill session '{session_name}': {result.stderr}"
            self.logger.warning(msg)
            self.ui.notification(msg, type="negative")

    def kill_tmux_session(self, session_name):
        """Kills a tmux session by name."""
        try:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=True)
            logger.info(f"Successfully killed tmux session '{session_name}'")
        except subprocess.CalledProcessError as e:
            msg = f"Failed to kill tmux session '{session_name}': {e}"
            logger.warning(msg)
            ui.notification(msg, type="negative")

    def kill_all_sessions(self):
        """Kill all active tmux sessions.
        Returns a tuple: (success_count, total_count, error_messages).
        """
        sessions_status = self.check_sessions()
        total_count = len(sessions_status)
        success_count = 0
        error_messages = []

        if total_count == 0:
            msg = "No active tmux sessions found."
            logger.info(msg)
            self.ui.notification(msg, type="info")
            return (0, 0, [])

        logger.info(f"Attempting to kill {total_count} tmux sessions")

        for session_name in sessions_status.keys():
            try:
                subprocess.run(["tmux", "kill-session", "-t", session_name], check=True)
                success_count += 1
                logger.info(f"Successfully killed session: {session_name}")

            except subprocess.CalledProcessError as e:
                error_msg = f"Failed to kill session '{session_name}': {e}"
                error_messages.append(error_msg)
                logger.warning(error_msg)
            except Exception as e:
                error_msg = f"Unexpected error killing session '{session_name}': {str(e)}"
                error_messages.append(error_msg)
                logger.error(error_msg)

        logger.info(f"Killed {success_count}/{total_count} sessions")
        return (success_count, total_count, error_messages)

    def kill_all_sessions_and_jobs(self):
        """Kill all active tmux sessions and scheduled jobs.
        Returns a tuple: (session_success, session_total, job_success, job_total, all_error_messages).
        """
        # Kill tmux sessions
        session_success, session_total, session_errors = self.kill_all_sessions()

        # Kill scheduled jobs
        job_success, job_total, job_errors = self.kill_scheduled_jobs()

        all_errors = session_errors + job_errors

        return (session_success, session_total, job_success, job_total, all_errors)

    def get_script_run_time(self, created_time, session_name):
        """Returns the elapsed time for a session using Redis data."""
        try:
            # Get session from Redis using new manager
            session = self.desto_manager.session_manager.get_session_by_name(session_name)
            if session and session.end_time:
                # Session has ended, use the recorded end time
                end_time = session.end_time.timestamp()
            else:
                # Session is still running, use current time
                end_time = time.time()

            return int(end_time - created_time)
        except Exception as e:
            logger.warning(f"Failed to get script run time for {session_name}: {e}")
            # Fallback to current time
            return int(time.time() - created_time)
