"""CLI-specific session manager using Redis-backed session management."""

import getpass
import os
import shlex
import socket
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from subprocess import CalledProcessError
from typing import Dict, List, Optional, Tuple

from loguru import logger

from desto.redis.client import DestoRedisClient
from desto.redis.session_manager import SessionManager


class CLISessionManager:
    """Session manager adapted for CLI use, with full Redis integration and proper logging."""

    def __init__(self, log_dir: Optional[Path] = None, scripts_dir: Optional[Path] = None):
        self.scripts_dir_env = os.environ.get("DESTO_SCRIPTS_DIR")
        self.logs_dir_env = os.environ.get("DESTO_LOGS_DIR")

        self.scripts_dir = Path(self.scripts_dir_env) if self.scripts_dir_env else Path(scripts_dir or Path.cwd() / "desto_scripts")
        self.log_dir = Path(self.logs_dir_env) if self.logs_dir_env else Path(log_dir or Path.cwd() / "desto_logs")

        self.sessions: Dict[str, str] = {}

        try:
            self.log_dir.mkdir(exist_ok=True)
            self.scripts_dir.mkdir(exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create log/scripts directory: {e}")
            raise

    def _get_redis_and_manager(self):
        redis_client = DestoRedisClient()
        session_manager = SessionManager(redis_client)
        return redis_client, session_manager

    def _build_info_block(self, session_name: str, scripts: List[str]) -> str:
        username = getpass.getuser()
        hostname = socket.gethostname()
        cwd = os.getcwd()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        info_lines = [
            f"# Session: {session_name}",
            f"# User: {username}@{hostname}",
            f"# Working Directory: {cwd}",
            f"# Started: {now_str}",
            f"# Scripts: {', '.join(scripts)}",
            "",
        ]
        return "\n".join(info_lines)

    def start_session(self, session_name: str, command: str) -> bool:
        """Start a new session using the Redis-based SessionManager and launch the command in tmux.
        Also removes any existing .finished marker file for test compatibility.
        """
        # Check for duplicate session in-memory (for test compatibility)
        if session_name in self.sessions:
            logger.error(f"Session '{session_name}' already exists (in-memory check).")
            return False

        # Check if session already exists in Redis
        redis_client, session_manager = self._get_redis_and_manager()
        existing_session = session_manager.get_session_by_name(session_name)
        if existing_session:
            logger.error(f"Session '{session_name}' already exists in Redis.")
            return False

        # Create session in Redis with metadata
        session = session_manager.create_session(session_name, tmux_session_name=session_name)
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

    def start_chain_session(self, scripts_with_args: List[List[str]], continue_on_error: bool = False) -> Optional[str]:
        """Start a chain session: runs multiple scripts in a single tmux session, logs info blocks, and registers in Redis.
        scripts_with_args: List of [script_name, arg1, arg2, ...]
        Returns the session name if started, else None.
        """
        session_name = f"chain_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
        script_names = [" ".join(map(str, s)) for s in scripts_with_args]
        log_file = self.get_log_file(session_name)
        quoted_log_file = shlex.quote(str(log_file))

        # Build info block
        info_block = self._build_info_block(session_name, script_names)
        # Write info block to log file immediately so it always exists
        try:
            log_file.parent.mkdir(exist_ok=True)
            with log_file.open("w") as f:
                f.write(info_block + "\n")
        except Exception as e:
            logger.error(f"Failed to write info block to log file '{log_file}': {e}")
            return None
        cmd_parts = []

        # For each script, add markers and execution
        for idx, parts in enumerate(scripts_with_args):
            if not parts:
                continue
            script_name, *script_args = parts
            script_path = None
            for candidate in [script_name, f"{script_name}.sh", f"{script_name}.py"]:
                candidate_path = self.get_script_file(candidate)
                if candidate_path.exists():
                    script_path = candidate_path
                    break
            if not script_path:
                logger.error(f"Script '{script_name}' not found in {self.scripts_dir}")
                return None
            if not os.access(script_path, os.X_OK):
                script_path.chmod(script_path.stat().st_mode | 0o111)
            # Determine interpreter
            if script_path.suffix == ".py":
                cmd = ["python3", str(script_path)]
            else:
                cmd = ["bash", str(script_path)]
            cmd.extend(script_args)
            script_cmd = " ".join(shlex.quote(arg) for arg in cmd)
            # Script info block
            script_info = f"printf '\\n=== SCRIPT {idx + 1}: {script_path.name} STARTING at %s ===\\n' \"$(date)\" >> {quoted_log_file}"
            cmd_parts.append(script_info)
            # Script execution with output redirection
            cmd_parts.append(f"({script_cmd}) >> {quoted_log_file} 2>&1")
            cmd_parts.append("SCRIPT_EXIT_CODE=$?")
            script_end = f"printf '\\n=== SCRIPT {idx + 1}: {script_path.name} FINISHED at %s (exit code: %s) ===\\n' " f'"$(date)" "$SCRIPT_EXIT_CODE" >> {quoted_log_file}'
            cmd_parts.append(script_end)
            if not continue_on_error:
                cmd_parts.append("if [ $SCRIPT_EXIT_CODE -ne 0 ]; then exit $SCRIPT_EXIT_CODE; fi")

        chain_command = " && ".join(cmd_parts) if not continue_on_error else " ; ".join(cmd_parts)

        # Register chain session in Redis
        redis_client, session_manager = self._get_redis_and_manager()
        # metadata variable removed as it's not used by SessionManager.create_session
        session = session_manager.create_session(session_name, tmux_session_name=session_name)
        session_manager.start_session(session.session_id)

        try:
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_name, chain_command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            logger.info(f"Chain session '{session_name}' started in tmux and registered in Redis.")
            self.sessions[session_name] = chain_command
            return session_name
        except CalledProcessError as e:
            error_output = e.stderr.strip() if e.stderr else "No stderr output"
            logger.error(f"Failed to start chain session '{session_name}' in tmux: {error_output}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error starting chain session '{session_name}': {e}")
            return None

    def list_sessions(self) -> Dict[str, Dict]:
        """List all sessions using the Redis-based SessionManager."""
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
        """Mark a session as finished using the Redis-based SessionManager."""
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
        """Mark all sessions as finished using the Redis-based SessionManager.

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
