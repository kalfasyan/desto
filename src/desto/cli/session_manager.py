"""CLI-specific session manager using Redis-backed session management."""

import os
import shlex
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger

from desto.core import scripts as core_scripts
from desto.store.client import DestoRedisClient
from desto.store.session_manager import SessionManager

_LOG_LEVELS = {"positive": "SUCCESS", "negative": "ERROR", "warning": "WARNING"}


def _log_notifier(message: str, level: str) -> None:
    logger.log(_LOG_LEVELS.get(level, "INFO"), message)


class CLISessionManager:
    """Session manager adapted for CLI use, with full Redis integration and proper logging."""

    def __init__(self, log_dir: Optional[Path] = None, scripts_dir: Optional[Path] = None):
        self.scripts_dir_env = os.environ.get("DESTO_SCRIPTS_DIR")
        self.logs_dir_env = os.environ.get("DESTO_LOGS_DIR")

        self.scripts_dir = Path(self.scripts_dir_env) if self.scripts_dir_env else Path(scripts_dir or Path.cwd() / "desto_scripts")
        self.log_dir = Path(self.logs_dir_env) if self.logs_dir_env else Path(log_dir or Path.cwd() / "desto_logs")

        self._service = None

        try:
            self.log_dir.mkdir(exist_ok=True)
            self.scripts_dir.mkdir(exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create log/scripts directory: {e}")
            raise

    @property
    def service(self):
        """The shared desto service, created on first use so read-only commands stay fast."""
        if self._service is None:
            from desto.core.service import DestoService

            self._service = DestoService(log_dir=self.log_dir, scripts_dir=self.scripts_dir, notifier=_log_notifier)
        return self._service

    def find_script(self, name: str) -> Optional[Path]:
        """Resolve a script name, with or without its .sh/.py extension, in the scripts directory."""
        for candidate in (name, f"{name}.sh", f"{name}.py"):
            path = self.get_script_file(candidate)
            if path.exists():
                return path
        return None

    def start_session(self, session_name: str, command: str) -> bool:
        """Start command in a new tmux session, the same way the dashboard and TUI do."""
        return self.service.start_tmux_session(session_name, command)

    def start_chain_session(self, scripts_with_args: List[List[str]], continue_on_error: bool = False) -> Optional[str]:
        """Run several scripts one after another in a single new tmux session.

        scripts_with_args: List of [script_name, arg1, arg2, ...]
        Returns the session name if started, else None.
        """
        chain = []
        for parts in scripts_with_args:
            if not parts:
                continue
            script_name, *script_args = parts
            script_path = self.find_script(script_name)
            if not script_path:
                logger.error(f"Script '{script_name}' not found in {self.scripts_dir}")
                return None
            chain.append((script_path, shlex.join(script_args)))
        if not chain:
            logger.error("No scripts given for the chain.")
            return None

        session_name = f"chain_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
        command = core_scripts.chain_command(chain, self.service.python_executable, continue_on_error=continue_on_error)
        return session_name if self.service.start_tmux_session(session_name, command) else None

    def list_sessions(self) -> Dict[str, Dict]:
        """List all sessions recorded in Redis."""
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
        """Stop the session's tmux session and mark it finished."""
        return self.service.kill_session(session_name)

    def kill_all_sessions(self) -> Tuple[int, int, list]:
        """Kill every desto session that is still running in tmux.

        Unlike the dashboard's "kill all", tmux sessions that desto did not start are left alone.

        Returns:
            Tuple of (success_count, total_count, error_messages)
        """
        running = [name for name in self.list_sessions() if self.service.is_tmux_session_active(name)]
        if not running:
            logger.info("No running desto sessions found")
            return (0, 0, [])

        success_count = 0
        error_messages = []
        for session_name in running:
            if self.kill_session(session_name):
                success_count += 1
            else:
                error_messages.append(f"Failed to kill session '{session_name}'")
        return (success_count, len(running), error_messages)

    def attach_session(self, session_name: str) -> bool:
        """Attach to an existing session (checks Redis, but still uses tmux for terminal attach)."""
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
        """Get log content for a session.

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
        """Follow log output for a session (like tail -f).

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
        """Get the log file path for a session.

        Args:
            session_name: Name of the session
        Returns:
            Path to the log file
        """
        return self.log_dir / f"{session_name}.log"

    def get_script_file(self, script_name: str) -> Path:
        """Get the script file path.

        Args:
            script_name: Name of the script file
        Returns:
            Path to the script file
        """
        return self.scripts_dir / script_name

    def session_exists(self, session_name: str) -> bool:
        """Check if a session exists.

        Args:
            session_name: Name of the session to check
        Returns:
            True if session exists, False otherwise
        """
        sessions = self.list_sessions()
        return session_name in sessions
