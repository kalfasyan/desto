from pathlib import Path
import subprocess
import shlex
from datetime import datetime
import time
from nicegui import ui
import os


class TmuxManager:
    def __init__(self, ui, logger, log_dir=None, scripts_dir=None):
        scripts_dir_env = os.environ.get("DESTO_SCRIPTS_DIR")
        logs_dir_env = os.environ.get("DESTO_LOGS_DIR")
        self.SCRIPTS_DIR = (
            Path(scripts_dir_env)
            if scripts_dir_env
            else Path(scripts_dir or Path.cwd() / "desto_scripts")
        )
        self.LOG_DIR = (
            Path(logs_dir_env)
            if logs_dir_env
            else Path(log_dir or Path.cwd() / "desto_logs")
        )
        self.sessions = {}
        self.ui = ui
        self.sessions_container = ui.column().style("margin-top: 20px;")
        self.logger = logger
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

    def start_session(self, session_name, command):
        """Start a new tmux session with the given command."""
        if session_name in self.sessions:
            raise ValueError(f"Session '{session_name}' already exists.")

        subprocess.run(["tmux", "new-session", "-d", "-s", session_name, command])
        self.sessions[session_name] = command

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

        return active_sessions

    def get_session_command(self, session_name):
        """Get the command associated with a specific session."""
        return self.sessions.get(session_name, None)

    def kill_session(self, session_name):
        """Kill a tmux session by name."""
        msg = f"Attempting to kill session: '{session_name}'"
        self.logger.info(msg)
        escaped_session_name = shlex.quote(session_name)  # Escape the session name
        result = subprocess.run(
            ["tmux", "kill-session", "-t", escaped_session_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0:
            msg = f"Session '{session_name}' killed successfully."
            self.logger.success(msg)
            ui.notification(msg, type="positive")
            if session_name in self.sessions:
                del self.sessions[session_name]
        else:
            msg = f"Failed to kill session '{session_name}': {result.stderr}"
            self.logger.warning(msg)
            ui.notification(msg, type="negative")

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

    def start_tmux_session(self, session_name, command, logger):
        """
        Starts a new tmux session with the given name and command, redirecting output to a log file.
        Shows notifications for success or failure.
        """
        log_file = self.get_log_file(session_name)
        try:
            log_file.parent.mkdir(exist_ok=True)
        except Exception as e:
            msg = f"Failed to create log directory '{log_file.parent}': {e}"
            logger.error(msg)
            ui.notification(msg, type="negative")
            return

        quoted_log_file = shlex.quote(str(log_file))
        full_command_for_tmux = f"{command} > {quoted_log_file} 2>&1"

        try:
            subprocess.run(
                [
                    "tmux",
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    full_command_for_tmux,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            msg = f"Tmux session '{session_name}' started. Command: '{full_command_for_tmux}'."
            logger.info(msg)
            ui.notification(msg, type="positive")
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

        self.clear_sessions_container()
        self.add_to_sessions_container(
            lambda: self.add_sessions_table(sessions_status, self.ui)
        )

    def kill_tmux_session(self, session_name):
        """
        Kills a tmux session by name.
        """
        try:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=True)
            msg = f"Tmux session '{session_name}' killed successfully."
            self.logger.success(msg)
            ui.notification(msg, type="positive")
            self.update_sessions_status()
        except subprocess.CalledProcessError as e:
            msg = f"Failed to kill tmux session '{session_name}': {e}"
            self.logger.warning(msg)
            ui.notification(msg, type="negative")

    def confirm_kill_session(self, session_name):
        """
        Displays a confirmation dialog before killing a tmux session and pauses updates.
        """
        if self.pause_updates:
            self.pause_updates()  # Pause the global timer

        with self.ui.dialog() as dialog, self.ui.card():
            self.ui.label(
                f"Are you sure you want to kill the session '{session_name}'?"
            )
            with self.ui.row():
                self.ui.button(
                    "Yes",
                    on_click=lambda: [
                        self.kill_tmux_session(session_name),
                        dialog.close(),
                        self.resume_updates(),  # Resume updates after killing
                    ],
                ).props("color=red")
                self.ui.button(
                    "No",
                    on_click=lambda: [
                        dialog.close(),
                        self.resume_updates(),  # Resume updates if canceled
                    ],
                )

        dialog.open()

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
            ui.label("Elapsed").style(header_style)  # New column
            ui.label("Attached").style(header_style)
            ui.label("Actions").style(header_style)

        now = time.time()
        for session_name, session in sessions_status.items():
            created_time = session["created"]
            elapsed_seconds = int(now - created_time)
            # Format elapsed as H:MM:SS
            hours, remainder = divmod(elapsed_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            elapsed_str = f"{hours}:{minutes:02}:{seconds:02}"

            with ui.row().style("align-items: center; margin-bottom: 10px;"):
                ui.label(session["id"]).style(cell_style)
                ui.label(session_name).style(cell_style)
                ui.label(
                    datetime.fromtimestamp(created_time).strftime("%Y-%m-%d %H:%M:%S")
                ).style(cell_style)
                ui.label(elapsed_str).style(cell_style)  # Elapsed column
                ui.label("Yes" if session["attached"] else "No").style(cell_style)
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
        if self.pause_updates:
            self.pause_updates()  # Pause the global timer

        log_file = self.get_log_file(session_name)
        try:
            with log_file.open("r") as f:
                lines = f.readlines()[-100:]  # Get the last 100 lines
            log_content = "".join(lines)
        except FileNotFoundError:
            log_content = f"Log file for session '{session_name}' not found."
        except Exception as e:
            log_content = f"Error reading log file: {e}"

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
                    dialog.close(),
                    self.resume_updates(),  # Resume updates when the dialog is closed
                ],
            ).props("color=primary")
        dialog.open()
