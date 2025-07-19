"""
CLI-specific session manager using Redis-backed session management.
"""

import os
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from subprocess import CalledProcessError
from typing import Dict, Optional, Tuple

from loguru import logger

# Frequently used Redis session management imports
from desto.redis.client import DestoRedisClient
from desto.redis.session_manager import SessionManager


class CLISessionManager:
    """Session manager adapted for CLI use without UI dependencies."""

    def __init__(self, log_dir: Optional[Path] = None, scripts_dir: Optional[Path] = None):
        """
        Initialize the CLI session manager.
        Args:
            log_dir: Directory for storing session logs
            scripts_dir: Directory containing scripts
        """
        self.scripts_dir_env = os.environ.get("DESTO_SCRIPTS_DIR")
        self.logs_dir_env = os.environ.get("DESTO_LOGS_DIR")

        self.scripts_dir = Path(self.scripts_dir_env) if self.scripts_dir_env else Path(scripts_dir or Path.cwd() / "desto_scripts")
        self.log_dir = Path(self.logs_dir_env) if self.logs_dir_env else Path(log_dir or Path.cwd() / "desto_logs")

        self.sessions: Dict[str, str] = {}

        # Ensure directories exist
        try:
            self.log_dir.mkdir(exist_ok=True)
            self.scripts_dir.mkdir(exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create log/scripts directory: {e}")
            raise

    def start_session(self, session_name: str, command: str, keep_alive: bool = False) -> bool:
        """
        Start a new session using the Redis-based SessionManager and launch the command in tmux.
        Also removes any existing .finished marker file for test compatibility.
        """

        # Check for duplicate session in-memory (for test compatibility)
        if session_name in self.sessions:
            logger.error(f"Session '{session_name}' already exists (in-memory check).")
            return False

        # Check if session already exists in Redis
        redis_client = DestoRedisClient()
        session_manager = SessionManager(redis_client)
        existing_session = session_manager.get_session_by_name(session_name)
        if existing_session:
            if hasattr(existing_session, "status") and getattr(existing_session, "status", None) and existing_session.status.value == "scheduled":
                logger.error(
                    f"Session '{session_name}' is already scheduled. Cannot start a new session with the same name until it runs or is cancelled."
                )
                # If UI notification system is available, trigger it here
                # Example: self.ui.notification(f"Session '{session_name}' is already scheduled.", type="warning")
                return False
            else:
                logger.error(f"Session '{session_name}' already exists in Redis.")
                return False

        # Create session in Redis
        session = session_manager.create_session(session_name, tmux_session_name=session_name, keep_alive=keep_alive)
        session_manager.start_session(session.session_id)

        # Launch the actual command in tmux (for CLI usability)
        log_file = self.get_log_file(session_name)
        try:
            log_file.parent.mkdir(exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create log directory '{log_file.parent}': {e}")
            return False

        quoted_log_file = shlex.quote(str(log_file))
        append_mode = log_file.exists()
        if append_mode:
            try:
                with log_file.open("a") as f:
                    f.write(f"\n---- NEW SESSION ({datetime.now()}) -----\n")
            except Exception as e:
                logger.error(f"Failed to write separator to log file: {e}")
                return False

        redir = ">>" if append_mode else ">"
        if keep_alive:
            full_command = f"{command} {redir} {quoted_log_file} 2>&1; tail -f /dev/null {redir} {quoted_log_file} 2>&1"
        else:
            full_command = f"{command} {redir} {quoted_log_file} 2>&1"

        try:
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_name, full_command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            logger.info(f"Session '{session_name}' started in tmux and registered in Redis.")
            self.sessions[session_name] = command
            return True
        except CalledProcessError as e:
            error_output = e.stderr.strip() if e.stderr else "No stderr output"
            logger.error(f"Failed to start session '{session_name}' in tmux: {error_output}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error starting session '{session_name}': {e}")
            return False

    def list_sessions(self) -> Dict[str, Dict]:
        """
        List all sessions using the Redis-based SessionManager.
        """
        try:
            redis_client = DestoRedisClient()
            session_manager = SessionManager(redis_client)
            sessions = session_manager.list_all_sessions()
            active_sessions = {}
            for session in sessions:
                # Compose a dictionary similar to the old output for compatibility
                active_sessions[session.session_name] = {
                    "id": session.session_id,
                    "name": session.session_name,
                    "created": int(session.start_time.timestamp()) if session.start_time else None,
                    "attached": False,  # Not tracked in Redis, can be extended if needed
                    "windows": 1,  # Not tracked in Redis, can be extended if needed
                    "group": None,  # Not tracked in Redis
                    "group_size": 1,  # Not tracked in Redis
                    "finished": session.status.value == "finished",
                    "runtime": int(((session.end_time or datetime.now()) - session.start_time).total_seconds()) if session.start_time else None,
                    "status": session.status.value,
                }
            return active_sessions
        except Exception as e:
            logger.error(f"Error listing sessions: {e}")
            return {}

    def kill_session(self, session_name: str) -> bool:
        """
        Mark a session as finished using the Redis-based SessionManager.
        """
        logger.info(f"Attempting to finish session: '{session_name}' (Redis-based)")
        redis_client = DestoRedisClient()
        session_manager = SessionManager(redis_client)

        # Find session by name
        session = session_manager.get_session_by_name(session_name)
        if not session:
            logger.error(f"Session '{session_name}' not found in Redis.")
            return False

        # Mark as finished
        result = session_manager.finish_session(session.session_id)
        if result:
            logger.success(f"Session '{session_name}' marked as finished in Redis.")
            if session_name in self.sessions:
                del self.sessions[session_name]
            return True
        else:
            logger.error(f"Failed to mark session '{session_name}' as finished in Redis.")
            return False

    def kill_all_sessions(self) -> Tuple[int, int, list]:
        """
        Mark all sessions as finished using the Redis-based SessionManager.
        Returns:
            Tuple of (success_count, total_count, error_messages)
        """
        sessions = self.list_sessions()
        total_count = len(sessions)
        success_count = 0
        error_messages = []

        if total_count == 0:
            logger.info("No active sessions found in Redis")
            return (0, 0, [])

        for session_name in sessions.keys():
            if self.kill_session(session_name):
                success_count += 1
            else:
                error_messages.append(f"Failed to finish session '{session_name}' in Redis")

        return (success_count, total_count, error_messages)

    def attach_session(self, session_name: str) -> bool:
        """
        Attach to an existing session (checks Redis, but still uses tmux for terminal attach).
        """
        # Check if session exists in Redis
        redis_client = DestoRedisClient()
        session_manager = SessionManager(redis_client)
        session = session_manager.get_session_by_name(session_name)
        if not session:
            logger.error(f"Session '{session_name}' not found in Redis.")
            return False

        # Still use tmux for actual terminal attach
        try:
            os.execvp("tmux", ["tmux", "attach-session", "-t", session_name])
        except FileNotFoundError:
            logger.error("tmux command not found")
            return False
        except Exception as e:
            logger.error(f"Error attaching to session '{session_name}': {e}")
            return False

    def get_log_content(self, session_name: str, lines: Optional[int] = None) -> Optional[str]:
        """
        Get log content for a session.
        Args:
            session_name: Name of the session
            lines: Number of lines to return from the end (None for all)
        Returns:
            Log content as string, or None if not found
        """
        log_file = self.get_log_file(session_name)

        if not log_file.exists():
            logger.warning(f"Log file not found for session '{session_name}'")
            return None

        try:
            if lines is None:
                # Return entire file
                with log_file.open("r") as f:
                    return f.read()
            else:
                # Return last N lines using tail
                result = subprocess.run(
                    ["tail", "-n", str(lines), str(log_file)],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                return result.stdout if result.returncode == 0 else None

        except Exception as e:
            logger.error(f"Error reading log file for session '{session_name}': {e}")
            return None

    def follow_log(self, session_name: str) -> bool:
        """
        Follow log output for a session (like tail -f).
        Args:
            session_name: Name of the session to follow
        Returns:
            True if follow started successfully, False otherwise
        """
        log_file = self.get_log_file(session_name)

        if not log_file.exists():
            logger.error(f"Log file not found for session '{session_name}'")
            return False

        try:
            # Use os.execvp to replace current process with tail -f
            os.execvp("tail", ["tail", "-f", str(log_file)])

        except FileNotFoundError:
            logger.error("tail command not found")
            return False
        except Exception as e:
            logger.error(f"Error following log for session '{session_name}': {e}")
            return False

    def get_log_file(self, session_name: str) -> Path:
        """
        Get the log file path for a session.
        Args:
            session_name: Name of the session
        Returns:
            Path to the log file
        """
        return self.log_dir / f"{session_name}.log"

    def get_script_file(self, script_name: str) -> Path:
        """
        Get the script file path.
        Args:
            script_name: Name of the script file
        Returns:
            Path to the script file
        """
        return self.scripts_dir / script_name

    def session_exists(self, session_name: str) -> bool:
        """
        Check if a session exists.
        Args:
            session_name: Name of the session to check
        Returns:
            True if session exists, False otherwise
        """
        sessions = self.list_sessions()
        return session_name in sessions
