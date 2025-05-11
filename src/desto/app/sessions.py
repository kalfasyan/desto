import subprocess
import shlex
from datetime import datetime


class TmuxManager:
    def __init__(self, ui, logger):
        self.sessions = {}
        self.ui = ui
        self.sessions_container = ui.column().style("margin-top: 20px;")
        self.logger = logger
        self.pause_updates = None  # Function to pause updates
        self.resume_updates = None  # Function to resume updates

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
        print(f"Attempting to kill session: '{session_name}'")
        escaped_session_name = shlex.quote(session_name)  # Escape the session name
        result = subprocess.run(
            ["tmux", "kill-session", "-t", escaped_session_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0:
            print(f"Session '{session_name}' killed successfully.")
            if session_name in self.sessions:
                del self.sessions[session_name]
        else:
            print(f"Failed to kill session '{session_name}': {result.stderr}")

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

    @staticmethod
    def start_tmux_session(session_name, command, logger):
        """
        Starts a new tmux session with the given name and command, redirecting output to a log file.
        """
        log_file = f"{session_name}.log"  # Log file path
        try:
            # Start a detached tmux session
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_name, command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            logger.info(
                f"Tmux session '{session_name}' started with command: {command}"
            )

            # Redirect output to the log file
            subprocess.run(
                ["tmux", "pipe-pane", "-t", session_name, f"cat > {log_file}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to start tmux session '{session_name}': {e}")

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
            self.logger.success(f"Tmux session '{session_name}' killed successfully.")
            self.update_sessions_status()
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to kill tmux session '{session_name}': {e}")

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
        # Add table headers
        with ui.row().style("font-weight: bold; margin-bottom: 10px;"):
            ui.label("Session ID").style("width: 100px;")
            ui.label("Name").style("width: 150px;")
            ui.label("Created").style("width: 200px;")
            ui.label("Attached").style("width: 100px;")
            ui.label("Windows").style("width: 100px;")
            ui.label("Group").style("width: 100px;")
            ui.label("Group Size").style("width: 100px;")
            ui.label("Actions").style("width: 200px;")

        # Add rows for each session
        for session_name, session in sessions_status.items():
            with ui.row().style("align-items: center; margin-bottom: 10px;"):
                ui.label(session["id"]).style("width: 100px;")
                ui.label(session_name).style("width: 150px;")
                ui.label(
                    datetime.fromtimestamp(session["created"]).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                ).style("width: 200px;")
                ui.label("Yes" if session["attached"] else "No").style("width: 100px;")
                ui.label(str(session["windows"])).style("width: 100px;")
                ui.label(session["group"] or "N/A").style("width: 100px;")
                ui.label(str(session["group_size"])).style("width: 100px;")
                ui.button(
                    "Kill",
                    on_click=lambda s=session_name: self.confirm_kill_session(
                        s,
                    ),
                ).props("color=red flat")
                ui.button(
                    "View Log",
                    on_click=lambda s=session_name: self.view_log(
                        s,
                        ui,
                    ),
                ).props("color=blue flat")

    def view_log(self, session_name, ui):
        """
        Pauses the app and opens a dialog to display the last 100 lines of the session's log file.
        """
        if self.pause_updates:
            self.pause_updates()  # Pause the global timer

        log_file = f"{session_name}.log"  # Log file path
        try:
            with open(log_file, "r") as f:
                lines = f.readlines()[-100:]  # Get the last 100 lines
            log_content = "".join(lines)
        except FileNotFoundError:
            log_content = f"Log file for session '{session_name}' not found."

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
