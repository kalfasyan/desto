import getpass
import json
import os
import shlex
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from loguru import logger
from nicegui import ui

from desto.redis.client import DestoRedisClient
from desto.redis.desto_manager import DestoManager
from desto.redis.pubsub import SessionPubSub


class TmuxManager:
    def __init__(self, ui_instance, instance_logger, log_dir=None, scripts_dir=None):
        if not ui_instance or not instance_logger:
            raise ValueError("ui_instance and instance_logger are required")

        scripts_dir_env = os.environ.get("DESTO_SCRIPTS_DIR")
        logs_dir_env = os.environ.get("DESTO_LOGS_DIR")
        self.SCRIPTS_DIR = Path(scripts_dir_env) if scripts_dir_env else Path(scripts_dir or Path.cwd() / "desto_scripts")
        self.LOG_DIR = Path(logs_dir_env) if logs_dir_env else Path(log_dir or Path.cwd() / "desto_logs")
        self.ui = ui_instance
        self.sessions_container = ui_instance.column().style("margin-top: 20px;")
        self.logger = instance_logger
        self.pause_updates = None  # Function to pause updates
        self.resume_updates = None  # Function to resume updates

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
            self.desto_manager = DestoManager(self.redis_client)
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

    def confirm_cancel_scheduled_job_by_id(self, at_job_id):
        """Show a confirmation dialog before canceling a scheduled job by at_job_id.
        Pauses updates while dialog is open.
        """
        from nicegui import ui

        if self.pause_updates:
            self.pause_updates()

        def do_cancel():
            self.cancel_scheduled_job(at_job_id)
            dialog.close()
            if self.resume_updates:
                self.resume_updates()
            # Force UI refresh
            self.update_sessions_status()

        def cancel():
            dialog.close()
            if self.resume_updates:
                self.resume_updates()

        with ui.dialog() as dialog, ui.card().style("min-width: 400px;"):
            # Telemetry: dialog opened
            self.telemetry_event("confirm_cancel_scheduled_job.open", {"at_job_id": str(at_job_id)})
            ui.label(f"Are you sure you want to cancel scheduled job {at_job_id}?").style("font-size: 1.1em; font-weight: bold; color: #d32f2f; margin-bottom: 10px;")

            def _cancel():
                cancel()
                self.telemetry_event("confirm_cancel_scheduled_job.cancel", {"at_job_id": str(at_job_id)})

            def _confirm():
                do_cancel()
                self.telemetry_event("confirm_cancel_scheduled_job.confirm", {"at_job_id": str(at_job_id)})

            with ui.row().style("gap: 10px; justify-content: flex-end; width: 100%; margin-top: 20px;"):
                ui.button("Cancel", on_click=_cancel).props("color=grey")
                ui.button("Confirm Cancel", color="red", on_click=_confirm).props("icon=delete_forever")
        dialog.open()

    def cancel_scheduled_job(self, at_job_id, session_name=None):
        """Cancels a scheduled job using AtJobManager and optionally updates the session status in Redis.
        If session_name is not provided, attempts to find the session by at_job_id in Redis.
        """
        from nicegui import ui

        from desto.redis.at_job_manager import AtJobManager

        try:
            at_job_manager = AtJobManager(self.redis_client)
            success = at_job_manager.cancel(str(at_job_id))
            if success:
                ui.notification(f"Cancelled scheduled job {at_job_id}", type="positive")
                # Try to update status in Redis
                session_obj = None
                if session_name and self.desto_manager:
                    session_obj = self.desto_manager.session_manager.get_session_by_name(session_name)
                elif self.desto_manager:
                    # Try to find session by at_job_id
                    for s in self.desto_manager.session_manager.list_all_sessions():
                        if getattr(s, "at_job_id", None) == str(at_job_id):
                            session_obj = s
                            break
                if session_obj:
                    session_obj.status = "failed"
                    session_obj.at_job_id = None
                    self.desto_manager.session_manager._update_session(session_obj)
            else:
                ui.notification(f"Failed to cancel scheduled job {at_job_id}", type="negative")
        except Exception as e:
            ui.notification(f"Failed to cancel scheduled job {at_job_id}: {e}", type="negative")

    def is_tmux_session_active(self, session_name: str) -> bool:
        """Check if a tmux session with the given name exists."""
        try:
            result = subprocess.run(["tmux", "has-session", "-t", session_name], capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error checking tmux session '{session_name}': {e}")
            return False

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
                        session_info = {k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in session_data.items()}
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

    def render_sessions_controls_and_stats(self, sessions_status, ui_manager=None):
        """Render the stats cards and control buttons (Refresh, Clear History, Clear Logs)."""
        from nicegui import ui

        # --- Control Buttons (Refresh, Clear History, Clear Logs) ---
        with ui.row().style("width: 100%; justify-content: space-between; align-items: center; margin-bottom: 20px;"):
            ui.label("Sessions Dashboard").style("font-size: 1.5em; font-weight: bold;")
            with ui.row().style("gap: 10px;"):
                ui.button("Refresh", icon="refresh", on_click=self.update_sessions_status).props("flat")
                ui.button("Clear History", icon="delete_sweep", color="red", on_click=self.confirm_clear_history).props("flat")
                ui.button("Clear Logs", icon="folder_delete", color="orange", on_click=self.confirm_clear_logs).props("flat")

        # --- Stats Cards (Total, Finished, Failed, Running) ---
        total_sessions = len(sessions_status)
        finished_jobs = 0
        failed_jobs = 0
        running_jobs = 0
        for session_name, session in sessions_status.items():
            job_status = None
            if self.desto_manager:
                try:
                    job_status = self.desto_manager.get_job_status(session_name)
                except Exception:
                    pass
            if job_status == "finished":
                finished_jobs += 1
            elif job_status == "failed":
                failed_jobs += 1
            else:
                running_jobs += 1

        with ui.row().style("gap: 30px; margin-bottom: 20px; flex-wrap: wrap;"):
            with ui.card().style("padding: 15px; min-width: 120px; text-align: center;"):
                ui.label(str(total_sessions)).style("font-size: 2em; font-weight: bold; color: #2196F3;")
                ui.label("Total Sessions").style("color: #666; font-size: 0.9em;")
            with ui.card().style("padding: 15px; min-width: 120px; text-align: center;"):
                ui.label(str(finished_jobs)).style("font-size: 2em; font-weight: bold; color: #4CAF50;")
                ui.label("Finished").style("color: #666; font-size: 0.9em;")
            with ui.card().style("padding: 15px; min-width: 120px; text-align: center;"):
                ui.label(str(failed_jobs)).style("font-size: 2em; font-weight: bold; color: #F44336;")
                ui.label("Failed").style("color: #666; font-size: 0.9em;")
            with ui.card().style("padding: 15px; min-width: 120px; text-align: center;"):
                ui.label(str(running_jobs)).style("font-size: 2em; font-weight: bold; color: #FF9800;")
                ui.label("Running").style("color: #666; font-size: 0.9em;")

    def confirm_clear_history(self):
        """Show confirmation dialog before clearing session history. Pauses updates while dialog is open."""
        from nicegui import ui

        if self.pause_updates:
            self.pause_updates()

        def close_dialog():
            dialog.close()
            if self.resume_updates:
                self.resume_updates()

        with ui.dialog() as dialog, ui.card().style("min-width: 400px;"):
            self.telemetry_event("confirm_clear_history.open", {})
            ui.label("⚠️ Clear Session History").style("font-size: 1.3em; font-weight: bold; color: #d32f2f; margin-bottom: 10px;")
            ui.label("This will permanently delete all session history from Redis.").style("margin-bottom: 15px;")
            ui.label("This action cannot be undone.").style("color: #666; margin-bottom: 20px;")

            def _close_and_telemetry_cancel():
                close_dialog()
                self.telemetry_event("confirm_clear_history.cancel", {})

            def _clear_and_telemetry_confirm():
                self.clear_session_history()
                close_dialog()
                self.telemetry_event("confirm_clear_history.confirm", {})

            with ui.row().style("gap: 10px; justify-content: flex-end; width: 100%;"):
                ui.button("Cancel", on_click=_close_and_telemetry_cancel).props("color=grey")
                ui.button("Clear History", color="red", on_click=_clear_and_telemetry_confirm).props("icon=delete_forever")
        dialog.open()

    def clear_session_history(self):
        """Clear all session history from Redis."""
        try:
            all_keys = list(self.redis_client.redis.scan_iter(match="desto:session:*"))
            if not all_keys:
                ui.notification("No session history to clear", type="info")
                return
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
                ui.notification(msg, type="positive")
                self.update_sessions_status()
            else:
                ui.notification("No sessions were cleared", type="warning")
        except Exception as e:
            error_msg = f"Error clearing session history: {e}"
            logger.error(error_msg)
            ui.notification(error_msg, type="negative")

    def confirm_clear_logs(self):
        """Show confirmation dialog before clearing log files. Pauses updates while dialog is open."""
        from nicegui import ui

        log_dir = self.LOG_DIR
        log_files = []
        if log_dir.exists():
            log_files = list(log_dir.glob("*.log"))
        if not log_files:
            ui.notification("No log files found to clear", type="info")
            return
        if self.pause_updates:
            self.pause_updates()

        def close_dialog():
            dialog.close()
            if self.resume_updates:
                self.resume_updates()

        with ui.dialog() as dialog, ui.card().style("min-width: 400px;"):
            self.telemetry_event("confirm_clear_logs.open", {"num_files": len(log_files)})
            ui.label("🗂️ Clear Log Files").style("font-size: 1.3em; font-weight: bold; color: #ff9800; margin-bottom: 10px;")
            ui.label(f"This will permanently delete {len(log_files)} log file(s) from:").style("margin-bottom: 10px;")
            ui.label(str(log_dir)).style("font-family: monospace; background: #f5f5f5; padding: 5px; border-radius: 3px; margin-bottom: 15px;")
            if len(log_files) <= 5:
                ui.label("Files to be deleted:").style("font-weight: bold; margin-bottom: 5px;")
                for log_file in log_files:
                    ui.label(f"• {log_file.name}").style("margin-left: 10px; font-family: monospace; font-size: 0.9em;")
            else:
                ui.label("Files to be deleted:").style("font-weight: bold; margin-bottom: 5px;")
                for log_file in log_files[:3]:
                    ui.label(f"• {log_file.name}").style("margin-left: 10px; font-family: monospace; font-size: 0.9em;")
                ui.label(f"• ... and {len(log_files) - 3} more files").style("margin-left: 10px; color: #666; font-size: 0.9em;")

            def _close_logs_cancel():
                close_dialog()
                self.telemetry_event("confirm_clear_logs.cancel", {})

            def _confirm_clear_logs():
                self.clear_log_files()
                close_dialog()
                self.telemetry_event("confirm_clear_logs.confirm", {})

            with ui.row().style("gap: 10px; justify-content: flex-end; width: 100%; margin-top: 20px;"):
                ui.button("Cancel", on_click=_close_logs_cancel).props("color=grey")
                ui.button("Clear Log Files", color="orange", on_click=_confirm_clear_logs).props("icon=folder_delete")
        dialog.open()

    def clear_log_files(self):
        """Clear all log files from the logs directory."""
        log_dir = self.LOG_DIR
        if not log_dir.exists():
            ui.notification("Logs directory not found", type="warning")
            return
        try:
            log_files = list(log_dir.glob("*.log"))
            finished_files = list(log_dir.glob("*.finished"))
            all_files = log_files + finished_files
            if not all_files:
                ui.notification("No log files found to clear", type="info")
                return
            deleted_count = 0
            errors = []
            for file_path in all_files:
                try:
                    file_path.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted log file: {file_path}")
                except Exception as e:
                    error_msg = f"Failed to delete {file_path.name}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
            if deleted_count > 0:
                msg = f"Successfully deleted {deleted_count} log file(s)"
                if errors:
                    msg += f" ({len(errors)} errors)"
                logger.info(msg)
                ui.notification(msg, type="positive")
                self.update_sessions_status()
            if errors:
                error_summary = "; ".join(errors[:3])
                if len(errors) > 3:
                    error_summary += f" (+{len(errors) - 3} more)"
                ui.notification(f"Errors: {error_summary}", type="warning")
        except Exception as e:
            error_msg = f"Error clearing log files: {e}"
            logger.error(error_msg)
            ui.notification(error_msg, type="negative")

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

    def clear_sessions_container(self):
        """Clears the sessions container."""
        self.sessions_container.clear()

    def add_to_sessions_container(self, content):
        """Adds content to the sessions container."""
        with self.sessions_container:
            content()

    def get_log_file(self, session_name):
        return self.LOG_DIR / f"{session_name}.log"

    def get_script_file(self, script_name):
        return self.SCRIPTS_DIR / script_name

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

        except subprocess.CalledProcessError as e:
            error_output = e.stderr.strip() if e.stderr else "No stderr output"
            msg = f"Failed to start session '{session_name}': {error_output}"
            logger.warning(msg)
            ui.notification(msg, type="negative")
        except Exception as e:
            msg = f"Unexpected error starting session '{session_name}': {str(e)}"
            logger.error(msg)
            ui.notification(msg, type="negative")

    def update_sessions_status(self, ui_manager=None):
        """Updates the sessions table with detailed information and adds a kill button and a view log button for each session.
        Also renders the stats cards and control buttons above the table, as in the history tab.
        Shows all sessions (active, finished, failed, scheduled) by aggregating from Redis, not just active tmux sessions.
        """
        sessions_status = self.get_all_sessions_status()

        self.clear_sessions_container()

        def render():
            self.render_sessions_controls_and_stats(sessions_status, ui_manager)
            self.add_sessions_table(sessions_status, self.ui)

        self.add_to_sessions_container(render)

    def kill_tmux_session(self, session_name):
        """Kills a tmux session by name."""
        try:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=True)
            logger.info(f"Successfully killed tmux session '{session_name}'")
        except subprocess.CalledProcessError as e:
            msg = f"Failed to kill tmux session '{session_name}': {e}"
            logger.warning(msg)
            ui.notification(msg, type="negative")

    def confirm_kill_session(self, session_name):
        """Displays a confirmation dialog before killing a tmux session and pauses updates."""
        logger.debug(f"User requested to kill session: {session_name}")
        if self.pause_updates:
            self.pause_updates()  # Pause the global timer

        with self.ui.dialog() as dialog, self.ui.card():
            # Telemetry: dialog opened
            self.telemetry_event("confirm_kill_session.open", {"session": session_name})
            self.ui.label(f"Are you sure you want to kill the session '{session_name}'?")

            def _confirm_kill():
                logger.info(f"User confirmed killing session: {session_name}")
                self.telemetry_event("confirm_kill_session.confirm", {"session": session_name})
                self.kill_tmux_session(session_name)
                dialog.close()
                self.resume_updates()  # Resume updates after killing

            def _cancel_kill():
                logger.debug(f"User cancelled killing session: {session_name}")
                self.telemetry_event("confirm_kill_session.cancel", {"session": session_name})
                dialog.close()
                self.resume_updates()  # Resume updates if canceled

            with self.ui.row():
                self.ui.button("Yes", on_click=_confirm_kill).props("color=red")
                self.ui.button("No", on_click=_cancel_kill)

        dialog.open()

    # single-session confirmation shown above; do not open the 'kill all' dialog here

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

    def add_sessions_table(self, sessions_status, ui):
        """Adds the sessions table to the UI, using the history tab's columns plus an Actions column."""
        # Table header
        with ui.row().style("width: 100%; min-width: 1100px; background-color: #f5f5f5; padding: 12px; border-radius: 4px; margin-bottom: 10px; font-weight: bold;"):
            ui.label("Session Name").style("flex: 2; min-width: 150px;")
            ui.label("Status").style("flex: 1; min-width: 100px;")
            ui.label("Job Duration").style("flex: 1; min-width: 120px;")
            ui.label("Session Duration").style("flex: 1; min-width: 130px;")
            ui.label("Started").style("flex: 2; min-width: 140px;")
            ui.label("Finished").style("flex: 2; min-width: 140px;")
            ui.label("Tmux Active").style("flex: 1; min-width: 100px;")
            ui.label("Actions").style("flex: 1; min-width: 120px;")

        # --- Only show non-scheduled sessions in the main table ---
        display_sessions = {}
        for session_name, session in sessions_status.items():
            status_field = session.get("status", "").lower()
            job_status_field = session.get("job_status", "").lower()
            if status_field == "scheduled" or job_status_field == "scheduled":
                continue  # Skip scheduled sessions
            display_sessions[session_name] = session

        for session_name, session in display_sessions.items():
            # Determine status for display
            status = "unknown"
            status_color = "#FF9800"
            job_status = session.get("job_status", "") or session.get("status", "")
            status_field = (session.get("status", "") or "").lower()
            job_status_field = (session.get("job_status", "") or "").lower()
            if job_status_field == "finished" or status_field == "finished":
                status = "✅ Finished"
                status_color = "#4CAF50"
            elif job_status_field == "failed" or status_field == "failed":
                status = "❌ Failed"
                status_color = "#F44336"
            elif job_status_field == "running" or status_field == "running":
                status = "🟡 Running"
                status_color = "#FF9800"
            elif job_status_field == "scheduled" or status_field == "scheduled":
                status = "📅 Scheduled"
                status_color = "#9C27B0"
            else:
                status = "🟡 Running"
                status_color = "#FF9800"

            # Tmux active status: always check live tmux for accuracy
            tmux_active = self.is_tmux_session_active(session_name)

            # If tmux is not active, session cannot be 'Running'
            if not tmux_active and (status_field == "running" or job_status_field == "running"):
                # If Redis indicates the session has already finished (end_time present) or the
                # job/session status is 'finished', prefer that authoritative state and show
                # Finished instead of Failed even when tmux is no longer active.
                if status_field == "finished" or job_status_field == "finished" or session.get("end_time"):
                    status = "✅ Finished"
                    status_color = "#4CAF50"
                else:
                    # As a fallback, ask the DestoManager whether the session is finished.
                    try:
                        if self.desto_manager and self.desto_manager.is_session_finished(session_name):
                            status = "✅ Finished"
                            status_color = "#4CAF50"
                        else:
                            status = "❌ Failed (tmux closed)"
                            status_color = "#F44336"
                    except Exception:
                        status = "❌ Failed (tmux closed)"
                        status_color = "#F44336"

            # Times and durations
            created_time = session.get("created")
            start_time = session.get("start_time")
            end_time = session.get("end_time")
            # Fallback for start_time
            if not start_time and created_time:
                start_time = datetime.fromtimestamp(float(created_time)).isoformat()

            # Format start time
            if start_time:
                try:
                    dt = datetime.fromisoformat(str(start_time).replace("Z", "+00:00"))
                    formatted_start_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    formatted_start_time = str(start_time)[:19] if len(str(start_time)) > 19 else str(start_time)
            else:
                formatted_start_time = "Unknown"

            # Format end time
            if end_time:
                try:
                    dt = datetime.fromisoformat(str(end_time).replace("Z", "+00:00"))
                    formatted_end_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    formatted_end_time = str(end_time)[:19] if len(str(end_time)) > 19 else str(end_time)
            else:
                formatted_end_time = "Running" if job_status == "running" else "N/A"

            # --- Job Duration (script execution time) ---
            job_duration = "N/A"
            # Try to calculate from start_time and end_time
            if start_time and end_time:
                try:
                    start_dt = datetime.fromisoformat(str(start_time).replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(str(end_time).replace("Z", "+00:00"))
                    elapsed_seconds = int((end_dt - start_dt).total_seconds())
                    if elapsed_seconds >= 0:
                        hours, remainder = divmod(elapsed_seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        job_duration = f"{hours}h {minutes}m {seconds}s" if hours > 0 else (f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s")
                except Exception:
                    pass
            # Fallback to job_elapsed or elapsed fields
            if job_duration == "N/A":
                job_duration = session.get("job_elapsed", session.get("elapsed", "N/A"))

            # --- Session Duration (total session time) ---
            session_duration = None
            if start_time:
                try:
                    start_dt = datetime.fromisoformat(str(start_time).replace("Z", "+00:00"))
                    if end_time:
                        end_dt = datetime.fromisoformat(str(end_time).replace("Z", "+00:00"))
                        elapsed_seconds = int((end_dt - start_dt).total_seconds())
                    else:
                        now_dt = datetime.now(start_dt.tzinfo) if start_dt.tzinfo else datetime.now()
                        elapsed_seconds = int((now_dt - start_dt).total_seconds())
                    if elapsed_seconds >= 0:
                        hours, remainder = divmod(elapsed_seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        session_duration = f"{hours}h {minutes}m {seconds}s" if hours > 0 else (f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s")
                    else:
                        session_duration = "N/A"
                except Exception:
                    session_duration = "N/A"
            else:
                session_duration = "N/A"

            def format_duration(duration_str):
                if duration_str in ["N/A", "unknown", "Ongoing"]:
                    return duration_str
                if ":" in str(duration_str):
                    try:
                        if "day" in str(duration_str):
                            parts = str(duration_str).split(", ")
                            days_part = parts[0]
                            time_part = parts[1] if len(parts) > 1 else "0:00:00"
                            days = int(days_part.split()[0])
                        else:
                            days = 0
                            time_part = str(duration_str)
                        time_components = time_part.split(":")
                        if len(time_components) >= 3:
                            hours = int(time_components[0]) + (days * 24)
                            minutes = int(time_components[1])
                            seconds = int(float(time_components[2]))
                            if hours > 0:
                                return f"{hours}h {minutes}m {seconds}s"
                            elif minutes > 0:
                                return f"{minutes}m {seconds}s"
                            else:
                                return f"{seconds}s"
                    except Exception:
                        pass
                return str(duration_str)

            job_duration = format_duration(job_duration)
            session_duration = format_duration(session_duration)

            with ui.row().style("width: 100%; min-width: 1100px; padding: 10px 12px; border-bottom: 1px solid #eee; " "align-items: center; hover:background-color: #f9f9f9;"):
                ui.label(session.get("session_name", session_name)).style("flex: 2; min-width: 150px; font-weight: 500;")
                ui.label(status).style(f"flex: 1; min-width: 100px; color: {status_color}; font-weight: 500;")
                ui.label(job_duration).style("flex: 1; min-width: 120px; color: #666;")
                ui.label(session_duration).style("flex: 1; min-width: 130px; color: #666;")
                ui.label(formatted_start_time).style("flex: 2; min-width: 140px; color: #666; font-size: 0.9em;")
                ui.label(formatted_end_time).style("flex: 2; min-width: 140px; color: #666; font-size: 0.9em;")
                # Tmux Active column
                icon = "check_circle" if tmux_active else "cancel"
                color = "#4CAF50" if tmux_active else "#F44336"
                ui.icon(icon).style(f"flex: 1; min-width: 100px; color: {color}; font-size: 1.5em; text-align: center;")
                with ui.row().style("flex: 1; min-width: 120px; gap: 8px;"):
                    if tmux_active:
                        ui.button(
                            "Kill",
                            on_click=lambda s=session_name: self.confirm_kill_session(s),
                        ).props("color=red flat")
                    else:
                        ui.button(
                            "Kill",
                            on_click=lambda: ui.notification("Cannot kill: no active tmux session for this entry.", type="warning"),
                        ).props("color=red flat disabled")
                    ui.button(
                        "View Log",
                        on_click=lambda s=session_name: self.view_log(s, ui),
                    ).props("color=blue flat")
                    ui.button(
                        "Clear",
                        on_click=lambda s=session_name: self.confirm_clear_session(s, ui),
                    ).props("color=orange flat")

        # --- Scheduled Jobs Table (from atq + Redis metadata) ---
        scheduled_jobs = self.get_scheduled_jobs()
        if scheduled_jobs:
            from desto.redis.at_job_manager import AtJobManager

            at_job_manager = AtJobManager(self.redis_client)

            with ui.row().style("margin-top: 40px; margin-bottom: 10px;"):
                ui.label("Scheduled Jobs (with metadata)").style("font-size: 1.2em; font-weight: bold;")

            # Table header for scheduled jobs
            with ui.row().style("width: 100%; min-width: 700px; background-color: #f5f5f5; padding: 10px; border-radius: 4px; font-weight: bold;"):
                ui.label("Job ID").style("flex: 1; min-width: 80px;")
                ui.label("Scheduled Time").style("flex: 2; min-width: 180px;")
                ui.label("User").style("flex: 1; min-width: 100px;")
                ui.label("Status").style("flex: 1; min-width: 100px;")
                ui.label("Actions").style("flex: 1; min-width: 120px;")

            for job in scheduled_jobs:
                job_id = job.get("id", "?")
                metadata = at_job_manager.get_job_metadata(str(job_id)) if at_job_manager else None
                scheduled_time = metadata.get("scheduled_time", job.get("datetime", "?")) if metadata else job.get("datetime", "?")
                user = metadata.get("user", job.get("user", "?")) if metadata else job.get("user", "?")
                status = metadata.get("status", "scheduled") if metadata else "scheduled"

                def show_metadata_dialog(job_id=job_id, metadata=metadata):
                    if self.pause_updates:
                        self.pause_updates()

                    def close_dialog():
                        dialog.close()
                        if self.resume_updates:
                            self.resume_updates()

                    with ui.dialog() as dialog, ui.card().style("min-width: 400px;"):
                        ui.label(f"Job Metadata for ID: {job_id}").style("font-weight: bold; font-size: 1.1em;")
                        if metadata:
                            for k in sorted(metadata.keys()):
                                v = metadata[k]
                                if k == "script_path":
                                    try:
                                        v_list = json.loads(v) if isinstance(v, str) else v
                                        v = ", ".join(str(item) for item in v_list)
                                    except Exception:
                                        pass
                                with ui.row():
                                    ui.label(f"{k}:").style("font-weight: bold; width: 120px;")
                                    ui.label(str(v)).style("flex: 1;")
                        else:
                            ui.label("No metadata found.")
                        ui.button("Close", on_click=close_dialog)
                    dialog.open()

                with ui.row().style("width: 100%; min-width: 700px; padding: 8px 10px; border-bottom: 1px solid #eee; align-items: center;"):
                    ui.button(str(job_id), on_click=show_metadata_dialog, color="primary", icon="info").style("flex: 1; min-width: 80px; font-weight: 500;")
                    ui.label(str(scheduled_time)).style("flex: 2; min-width: 180px; color: #666;")
                    ui.label(str(user)).style("flex: 1; min-width: 100px; color: #666;")
                    ui.label(str(status)).style("flex: 1; min-width: 100px; color: #666;")
                    with ui.row().style("flex: 1; min-width: 120px; gap: 8px;"):
                        ui.button(
                            "Cancel",
                            on_click=lambda j=job_id: self.confirm_cancel_scheduled_job_by_id(j),
                        ).props("color=red flat")

    def confirm_clear_session(self, session_name, ui):
        """Show confirmation dialog before clearing a session (deletes log and removes from Redis)."""
        if self.pause_updates:
            self.pause_updates()

        def do_clear():
            self.clear_session(session_name, ui)
            dialog.close()
            if self.resume_updates:
                self.resume_updates()

        def cancel():
            dialog.close()
            if self.resume_updates:
                self.resume_updates()

        with ui.dialog() as dialog, ui.card().style("min-width: 400px;"):
            self.telemetry_event("confirm_clear_session.open", {"session": session_name})
            ui.label(f"Are you sure you want to clear session '{session_name}'?").style("font-size: 1.1em; font-weight: bold; color: #ff9800; margin-bottom: 10px;")
            ui.label("This will delete its log file and remove it from the sessions table.").style("margin-bottom: 15px;")

            def _cancel_clear_session():
                cancel()
                self.telemetry_event("confirm_clear_session.cancel", {"session": session_name})

            def _confirm_clear_session():
                do_clear()
                self.telemetry_event("confirm_clear_session.confirm", {"session": session_name})

            with ui.row().style("gap: 10px; justify-content: flex-end; width: 100%; margin-top: 20px;"):
                ui.button("Cancel", on_click=_cancel_clear_session).props("color=grey")
                ui.button("Clear Session", color="orange", on_click=_confirm_clear_session).props("icon=delete_forever")
        dialog.open()

    def clear_session(self, session_name, ui):
        """Deletes the session's log file and removes the session from Redis, then refreshes the UI."""
        # Delete log file
        log_file = self.get_log_file(session_name)
        log_deleted = False
        try:
            if log_file.exists():
                log_file.unlink()
                log_deleted = True
                logger.info(f"Deleted log file for session: {session_name}")
        except Exception as e:
            logger.warning(f"Failed to delete log file for session {session_name}: {e}")

        # Remove session from Redis (find correct key)
        redis_deleted = False
        try:
            # Find the correct Redis key for this session
            all_keys = list(self.redis_client.redis.scan_iter(match="desto:session:*"))
            found_key = None
            for key in all_keys:
                session_data = self.redis_client.redis.hgetall(key)
                if session_data:
                    session_info = {k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in session_data.items()}
                    display_session_name = session_info.get("session_name", key.replace("desto:session:", ""))
                    if display_session_name == session_name:
                        found_key = key
                        break
            if found_key:
                result = self.redis_client.redis.delete(found_key)
                if result:
                    redis_deleted = True
                    logger.info(f"Deleted Redis session: {session_name} (key: {found_key})")
            else:
                logger.warning(f"Could not find Redis key for session '{session_name}'")
        except Exception as e:
            logger.warning(f"Failed to delete Redis session {session_name}: {e}")

        # Notify user
        if log_deleted and redis_deleted:
            ui.notification(f"Session '{session_name}' cleared (log and Redis entry deleted)", type="positive")
        elif log_deleted:
            ui.notification(f"Session '{session_name}' log deleted, but failed to remove from Redis", type="warning")
        elif redis_deleted:
            ui.notification(f"Session '{session_name}' removed from Redis, but log file not found/deleted", type="warning")
        else:
            ui.notification(f"Failed to clear session '{session_name}' (see logs)", type="negative")

        # Refresh UI
        self.update_sessions_status(ui)

    def view_log(self, session_name, ui):
        """Pauses the app and opens a dialog to display the last 100 lines of the session's log file."""
        logger.debug(f"User requested to view log for session: {session_name}")
        if self.pause_updates:
            self.pause_updates()  # Pause the global timer

        log_file = self.get_log_file(session_name)
        try:
            with log_file.open("r") as f:
                lines = f.readlines()[-100:]  # Get the last 100 lines
            log_content = "".join(lines)
            logger.debug(f"Successfully read {len(lines)} lines from log file for session: {session_name}")
        except FileNotFoundError:
            log_content = f"Log file for session '{session_name}' not found."
            logger.warning(f"Log file not found for session: {session_name}")
        except Exception as e:
            log_content = f"Error reading log file: {e}"
            logger.error(f"Error reading log file for session {session_name}: {e}")

        with (
            ui.dialog() as dialog,
            ui.card().style("width: 100%; height: 80%;"),
        ):
            ui.label(f"Log for session '{session_name}'").style("font-weight: bold;")
            with ui.scroll_area().style("width: 100%; height: 100%;"):
                ui.label(log_content).style("white-space: pre-wrap;")
            ui.button(
                "Close",
                on_click=lambda: [
                    logger.debug(f"User closed log view for session: {session_name}"),
                    dialog.close(),
                    self.resume_updates(),  # Resume updates when the dialog is closed
                ],
            ).props("color=primary")
        dialog.open()

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

    def confirm_kill_all_sessions(self):
        """Displays a confirmation dialog before killing all tmux sessions and scheduled jobs, and pauses updates."""
        if self.pause_updates:
            self.pause_updates()  # Pause the global timer

        sessions_status = self.check_sessions()
        session_count = len(sessions_status)

        # Get scheduled jobs
        scheduled_jobs = self.get_scheduled_jobs()
        job_count = len(scheduled_jobs)

        if session_count == 0 and job_count == 0:
            msg = "No active sessions or scheduled jobs to clear."
            logger.info(msg)
            self.ui.notification(msg, type="info")
            if self.resume_updates:
                self.resume_updates()
            return

        # Get session status from Redis
        running_sessions = []
        finished_sessions = []

        for session_name in sessions_status.keys():
            try:
                job_status = self.desto_manager.get_job_status(session_name)
                if job_status in ["finished", "failed"]:
                    finished_sessions.append(session_name)
                else:
                    running_sessions.append(session_name)
            except Exception as e:
                logger.warning(f"Could not get status for session {session_name}: {e}")
                # Assume running if we can't determine status
                running_sessions.append(session_name)

        running_count = len(running_sessions)
        finished_count = len(finished_sessions)

        def do_kill_all():
            session_success, session_total, job_success, job_total, error_messages = self.kill_all_sessions_and_jobs()

            results = []
            if session_total > 0:
                if session_success == session_total:
                    results.append(f"Successfully cleared all {session_total} sessions")
                else:
                    results.append(f"Cleared {session_success}/{session_total} sessions")

            if job_total > 0:
                if job_success == job_total:
                    results.append(f"Successfully cancelled all {job_total} scheduled jobs")
                else:
                    results.append(f"Cancelled {job_success}/{job_total} scheduled jobs")

            if not results:
                results.append("No items to clear")

            msg = ". ".join(results) + "."

            if error_messages:
                msg += f" Errors: {'; '.join(error_messages[:3])}"  # Show first 3 errors
                logger.warning(msg)
                self.ui.notification(msg, type="warning")
            else:
                logger.success(msg)
                self.ui.notification(msg, type="positive")

            dialog.close()
            if self.resume_updates:
                self.resume_updates()

        def cancel_kill_all():
            logger.debug("User cancelled kill all sessions operation")
            dialog.close()
            if self.resume_updates:
                self.resume_updates()

        with self.ui.dialog() as dialog, self.ui.card().style("min-width: 500px;"):
            self.ui.label("⚠️ Clear All Jobs").style("font-size: 1.3em; font-weight: bold; color: #d32f2f; margin-bottom: 10px;")

            # Build warning text
            warning_parts = []
            if session_count > 0:
                if running_count > 0 and finished_count > 0:
                    warning_parts.append(f"{session_count} sessions ({running_count} running, {finished_count} finished)")
                elif running_count > 0:
                    warning_parts.append(f"{running_count} RUNNING sessions")
                else:
                    warning_parts.append(f"{finished_count} finished sessions")

            if job_count > 0:
                warning_parts.append(f"{job_count} scheduled jobs")

            warning_text = "This will clear:\n• " + "\n• ".join(warning_parts)
            if running_count > 0:
                warning_text += "\n\n⚠️ This may interrupt active processes!"

            self.ui.label(warning_text).style("margin-bottom: 15px; white-space: pre-line;")

            # Show running sessions
            if running_count > 0:
                self.ui.label("Running sessions:").style("font-weight: bold; margin-bottom: 5px;")
                for session in running_sessions[:5]:  # Show max 5 sessions
                    self.ui.label(f"• {session}").style("margin-left: 10px; color: #d32f2f;")
                if len(running_sessions) > 5:
                    self.ui.label(f"• ... and {len(running_sessions) - 5} more").style("margin-left: 10px; color: #666;")

            # Show scheduled jobs
            if job_count > 0:
                self.ui.label("Scheduled jobs:").style("font-weight: bold; margin-bottom: 5px; margin-top: 10px;")
                for job in scheduled_jobs[:5]:  # Show max 5 jobs
                    self.ui.label(f"• Job {job['id']}: {job['datetime']}").style("margin-left: 10px; color: #ff9800;")
                if len(scheduled_jobs) > 5:
                    self.ui.label(f"• ... and {len(scheduled_jobs) - 5} more").style("margin-left: 10px; color: #666;")

            with self.ui.row().style("margin-top: 20px; gap: 10px;"):
                self.ui.button("Cancel", on_click=cancel_kill_all).props("color=grey")
                self.ui.button("Clear All Jobs", color="red", on_click=do_kill_all).props("icon=delete_forever")

        dialog.open()

    def get_scheduled_jobs(self):
        """Get a list of scheduled jobs from the 'at' command.
        Returns a list of dictionaries with job info.
        """
        try:
            result = subprocess.run(["atq"], capture_output=True, text=True)
            if result.returncode != 0:
                self.logger.debug("No scheduled jobs found or 'at' command failed")
                return []

            jobs = []
            for line in result.stdout.splitlines():
                if line.strip():
                    # Parse atq output: job_id date time queue user
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        job_id = parts[0]
                        # Combine date and time parts (Mon Jul 14 07:59:00 2025)
                        date_time = " ".join(parts[1:6]) if len(parts) >= 6 else " ".join(parts[1:5])
                        user = parts[-1]

                        # Try to get the actual command for this job
                        command = self._get_scheduled_job_command(job_id)

                        # Format the datetime for better display
                        formatted_datetime = self._format_scheduled_datetime(date_time)

                        jobs.append({"id": job_id, "datetime": formatted_datetime, "raw_datetime": date_time, "user": user, "command": command})

            return jobs
        except Exception as e:
            self.logger.warning(f"Failed to get scheduled jobs: {e}")
            return []

    def _get_scheduled_job_command(self, job_id):
        """Get the actual command for a scheduled job."""
        try:
            result = subprocess.run(["at", "-c", job_id], capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.splitlines()
                # The actual command is usually the last non-empty line
                for line in reversed(lines):
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("cd ") and "export" not in line:
                        # Truncate very long commands
                        if len(line) > 60:
                            return line[:57] + "..."
                        return line
                return "Unknown command"
            else:
                return "Unknown command"
        except Exception:
            return "Unknown command"

    def _format_scheduled_datetime(self, date_time):
        """Format datetime from atq output for better display."""
        try:
            from datetime import datetime

            # Parse format like "Mon Jul 14 07:59:00 2025"
            dt = datetime.strptime(date_time, "%a %b %d %H:%M:%S %Y")
            return dt.isoformat()
        except Exception:
            # Fallback to original if parsing fails
            return date_time

    def kill_scheduled_jobs(self):
        """Kill all scheduled jobs and return summary.
        Returns a tuple: (success_count, total_count, error_messages).
        """
        jobs = self.get_scheduled_jobs()
        total_count = len(jobs)
        success_count = 0
        error_messages = []

        if total_count == 0:
            logger.debug("No scheduled jobs found to kill")
            return (0, 0, [])

        logger.info(f"Attempting to cancel {total_count} scheduled jobs")

        for job in jobs:
            try:
                subprocess.run(["atrm", job["id"]], check=True)
                success_count += 1
                logger.info(f"Successfully removed scheduled job: {job['id']}")
            except subprocess.CalledProcessError as e:
                error_msg = f"Failed to remove job '{job['id']}': {e}"
                error_messages.append(error_msg)
                logger.warning(error_msg)
            except Exception as e:
                error_msg = f"Unexpected error removing job '{job['id']}': {str(e)}"
                error_messages.append(error_msg)
                logger.error(error_msg)

        logger.info(f"Cancelled {success_count}/{total_count} scheduled jobs")
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

        # Use dedicated script to mark job completion in Redis
        # First try relative path from project root
        script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "mark_job_finished.py"

        # If that doesn't exist, try from current working directory (Docker case)
        if not script_path.exists():
            script_path = Path.cwd() / "scripts" / "mark_job_finished.py"

        # If still not found, try to find project root by looking for pyproject.toml
        if not script_path.exists():
            current = Path(__file__).parent
            while current != current.parent:
                if (current / "pyproject.toml").exists():
                    script_path = current / "scripts" / "mark_job_finished.py"
                    break
                current = current.parent

        # Determine the correct Python command
        # In Docker with uv, use 'uv run python', otherwise use 'python3'
        if Path("/usr/local/bin/uv").exists():
            python_cmd = "uv run python"
        else:
            python_cmd = "python3"

        return f"{python_cmd} '{script_path}' '{session_name}' {exit_code_ref}"

    def get_session_start_command(self, session_name: str, command: str):
        """Get the appropriate command to mark session start using Redis.

        Args:
            session_name: Name of the session
            command: Command being executed in the session
        """
        # Use dedicated script to mark session start
        # First try relative path from project root
        script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "mark_session_started.py"

        # If that doesn't exist, try from current working directory (Docker case)
        if not script_path.exists():
            script_path = Path.cwd() / "scripts" / "mark_session_started.py"

        # If still not found, try to find project root by looking for pyproject.toml
        if not script_path.exists():
            current = Path(__file__).parent
            while current != current.parent:
                if (current / "pyproject.toml").exists():
                    script_path = current / "scripts" / "mark_session_started.py"
                    break
                current = current.parent

        # Determine the correct Python command
        # In Docker with uv, use 'uv run python', otherwise use 'python3'
        if Path("/usr/local/bin/uv").exists():
            python_cmd = "uv run python"
        else:
            python_cmd = "python3"

        # Escape quotes in command string for shell safety
        escaped_command = command.replace("'", "'\"'\"'")

        return f"{python_cmd} '{script_path}' '{session_name}' '{escaped_command}'"
