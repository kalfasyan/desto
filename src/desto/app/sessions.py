import subprocess
import shlex


class TmuxManager:
    def __init__(self):
        self.sessions = {}

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

    def get_session_cpu_load(self, session_name):
        """Retrieve the CPU load of a specific tmux session."""
        result = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-t",
                session_name,
                "-F",
                "#{pane_id}:#{pane_active}:#{pane_cpu}",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            cpu_loads = []
            for line in result.stdout.splitlines():
                pane_info = line.split(":")
                pane_id = pane_info[0]
                pane_active = pane_info[1] == "1"
                pane_cpu = float(pane_info[2])
                cpu_loads.append(
                    {"pane_id": pane_id, "active": pane_active, "cpu": pane_cpu}
                )

            return cpu_loads
        else:
            raise ValueError(
                f"Failed to retrieve CPU load for session '{session_name}'."
            )

    def get_session_layout(self, session_name):
        """Retrieve the layout of a specific tmux session."""
        result = subprocess.run(
            ["tmux", "display-message", "-p", "-t", session_name, "#{window_layout}"],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            return result.stdout.strip()
        else:
            raise ValueError(f"Failed to retrieve layout for session '{session_name}'.")
