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
            logger.warning("Redis is not available - running in limited mode")
            self.desto_manager = None
            self.pubsub = None
        else:
            self.desto_manager = DestoManager(self.redis_client)
            self.pubsub = SessionPubSub(self.redis_client)
            logger.info("Redis enabled for session tracking")

        # For backward compatibility with tests
        self.sessions = {}
        # For backward compatibility - use_redis attribute
        self.use_redis = self.redis_client.is_connected()

        logger.info(f"TmuxManager initialized - log_dir: {self.LOG_DIR}, scripts_dir: {self.SCRIPTS_DIR}")

    def _start_redis_monitoring(self, session_name):
        """Monitor tmux session and update Redis"""
        
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
        logger.debug("Checking tmux sessions")
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
        else:
            logger.debug("No active tmux sessions found or tmux not running")

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
        """
        Clears the sessions container.
        """
        self.sessions_container.clear()

    def add_to_sessions_container(self, content):
        """
        Adds content to the sessions container.
        """
        with self.sessions_container:
            content()

    def get_log_file(self, session_name):
        return self.LOG_DIR / f"{session_name}.log"

    def get_script_file(self, script_name):
        return self.SCRIPTS_DIR / script_name

    def start_tmux_session(self, session_name, command, instance_logger, keep_alive=False):
        """
        Starts a new tmux session with the given name and command, redirecting output to a log file.
        Shows notifications for success or failure.
        Only appends 'tail -f /dev/null' if keep_alive is True.
        """
        # Check if session already exists
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
{f"tail -f /dev/null >> {quoted_log_file} 2>&1" if keep_alive else ""}
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
                session, job = self.desto_manager.start_session_with_job(
                    session_name=session_name, command=command, script_path=command, keep_alive=keep_alive
                )
                self._start_redis_monitoring(session_name)
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

    def update_sessions_status(self):
        """
        Updates the sessions table with detailed information and adds a kill button and a view log button for each session.
        """
        sessions_status = self.check_sessions()
        logger.debug(f"Updating UI with {len(sessions_status)} active sessions")

        self.clear_sessions_container()
        self.add_to_sessions_container(lambda: self.add_sessions_table(sessions_status, self.ui))

    def kill_tmux_session(self, session_name):
        """
        Kills a tmux session by name.
        """
        try:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=True)
            logger.info(f"Successfully killed tmux session '{session_name}'")
        except subprocess.CalledProcessError as e:
            msg = f"Failed to kill tmux session '{session_name}': {e}"
            logger.warning(msg)
            ui.notification(msg, type="negative")

    def confirm_kill_session(self, session_name):
        """
        Displays a confirmation dialog before killing a tmux session and pauses updates.
        """
        logger.debug(f"User requested to kill session: {session_name}")
        if self.pause_updates:
            self.pause_updates()  # Pause the global timer

        with self.ui.dialog() as dialog, self.ui.card():
            self.ui.label(f"Are you sure you want to kill the session '{session_name}'?")
            with self.ui.row():
                self.ui.button(
                    "Yes",
                    on_click=lambda: [
                        logger.info(f"User confirmed killing session: {session_name}"),
                        self.kill_tmux_session(session_name),
                        dialog.close(),
                        self.resume_updates(),  # Resume updates after killing
                    ],
                ).props("color=red")
                self.ui.button(
                    "No",
                    on_click=lambda: [
                        logger.debug(f"User cancelled killing session: {session_name}"),
                        dialog.close(),
                        self.resume_updates(),  # Resume updates if canceled
                    ],
                )

        dialog.open()

    def get_script_run_time(self, created_time, session_name):
        """
        Returns the elapsed time for a session using Redis data.
        """
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
        """
        Adds the sessions table to the UI.
        """
        header_style = "width: 150px; font-size: 1.2em; font-weight: bold;"
        cell_style = "width: 150px; font-size: 1.2em;"

        with ui.row().style("margin-bottom: 10px;"):
            ui.label("Session ID").style(header_style)
            ui.label("Name").style(header_style)
            ui.label("Created").style(header_style)
            ui.label("Elapsed").style(header_style)
            ui.label("Attached").style(header_style)
            ui.label("Status").style(header_style)
            ui.label("Actions").style(header_style)

        for session_name, session in sessions_status.items():
            created_time = session["created"]
            elapsed_seconds = self.get_script_run_time(created_time, session_name)
            hours, remainder = divmod(elapsed_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            elapsed_str = f"{hours}:{minutes:02}:{seconds:02}"

            # Get job status from Redis if available, otherwise fall back to file markers
            if self.desto_manager:
                job_status = self.desto_manager.get_job_status(session_name)
                if job_status in ["finished", "failed"]:
                    status = "Finished"
                else:
                    status = "Running"
            else:
                # Fall back to file-based status checking
                finished_marker = self.LOG_DIR / f"{session_name}.finished"
                failed_marker = self.LOG_DIR / f"{session_name}.failed"
                if finished_marker.exists() or failed_marker.exists():
                    status = "Finished"
                else:
                    status = "Running"

            with ui.row().style("align-items: center; margin-bottom: 10px;"):
                ui.label(session["id"]).style(cell_style)
                ui.label(session_name).style(cell_style)
                ui.label(datetime.fromtimestamp(created_time).strftime("%Y-%m-%d %H:%M:%S")).style(cell_style)
                ui.label(elapsed_str).style(cell_style)
                ui.label("Yes" if session["attached"] else "No").style(cell_style)
                ui.label(status).style(cell_style)
                ui.button(
                    "Kill",
                    on_click=lambda s=session_name: self.confirm_kill_session(s),
                ).props("color=red flat")
                ui.button(
                    "View Log",
                    on_click=lambda s=session_name: self.view_log(s, ui),
                ).props("color=blue flat")

    def view_log(self, session_name, ui):
        """
        Pauses the app and opens a dialog to display the last 100 lines of the session's log file.
        """
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
        """
        Kill all active tmux sessions.
        Returns a tuple: (success_count, total_count, error_messages)
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
        """
        Displays a confirmation dialog before killing all tmux sessions and scheduled jobs, and pauses updates.
        """
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
        """
        Get a list of scheduled jobs from the 'at' command.
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
                        # Combine date and time parts
                        date_time = " ".join(parts[1:5])
                        user = parts[-1]
                        jobs.append({"id": job_id, "datetime": date_time, "user": user})

            self.logger.debug(f"Found {len(jobs)} scheduled jobs")
            return jobs
        except Exception as e:
            self.logger.warning(f"Failed to get scheduled jobs: {e}")
            return []

    def kill_scheduled_jobs(self):
        """
        Kill all scheduled jobs and return summary.
        Returns a tuple: (success_count, total_count, error_messages)
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
        """
        Kill all active tmux sessions and scheduled jobs.
        Returns a tuple: (session_success, session_total, job_success, job_total, all_error_messages)
        """
        # Kill tmux sessions
        session_success, session_total, session_errors = self.kill_all_sessions()

        # Kill scheduled jobs
        job_success, job_total, job_errors = self.kill_scheduled_jobs()

        all_errors = session_errors + job_errors

        return (session_success, session_total, job_success, job_total, all_errors)

    def get_job_completion_command(self, session_name, use_variable=False):
        """
        Get the appropriate command to mark job completion.

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
        """
        Get the appropriate command to mark session start using Redis.

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
