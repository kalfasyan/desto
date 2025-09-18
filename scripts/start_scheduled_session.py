#!/usr/bin/env python3
"""Wrapper script for starting scheduled tmux sessions with proper Redis tracking.
This ensures scheduled jobs get the same Redis tracking as manually started sessions.
"""

import subprocess
import sys

# Ensure loguru outputs to both stdout and a file, and set level to DEBUG
import sys as _sys
import threading
import time
from pathlib import Path

from loguru import logger

logger.remove()
logger.add(_sys.stdout, level="DEBUG", enqueue=True)
# Use a logs directory relative to this script's location, with error handling
try:
    _log_dir = Path(__file__).parent.parent / "desto_logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_path = _log_dir / "desto_scheduled_wrapper.log"
except Exception as e:
    print(f"[SCHEDULED WRAPPER] ERROR: Could not create log directory '{_log_dir}': {e}")
    logger.error(f"[SCHEDULED WRAPPER] Could not create log directory '{_log_dir}': {e}")
    _log_path = "/tmp/desto_scheduled_wrapper.log"
    print(f"[SCHEDULED WRAPPER] Falling back to log file at {_log_path}")
    logger.warning(f"[SCHEDULED WRAPPER] Falling back to log file at {_log_path}")

try:
    logger.add(
        str(_log_path),
        level="DEBUG",
        rotation="10 MB",  # Rotate after 10 MB
        retention="7 days",  # Keep logs for 7 days
        enqueue=True,
    )
except Exception as e:
    print(f"[SCHEDULED WRAPPER] ERROR: Could not add log file handler for '{_log_path}': {e}")
    logger.error(f"[SCHEDULED WRAPPER] Could not add log file handler for '{_log_path}': {e}")


# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def start_redis_monitoring(session_name, desto_manager):
    """Monitor tmux session and update Redis - same logic as TmuxManager._start_redis_monitoring."""

    def monitor():
        try:
            while True:
                time.sleep(1)
                result = subprocess.run(
                    ["tmux", "list-sessions", "-F", "#{session_name}"],
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0 or session_name not in result.stdout:
                    # Session finished (entire tmux session ended)
                    try:
                        # Try to get exit status from Redis job
                        job_status = desto_manager.get_job_status(session_name)
                        if job_status not in ["finished", "failed"]:
                            # Session ended but job wasn't marked complete - mark as finished
                            desto_manager.finish_job(session_name, 0)
                            logger.debug(f"Session '{session_name}' ended - marked as finished in Redis")
                        else:
                            logger.debug(f"Session '{session_name}' ended - already marked as {job_status} in Redis")

                        # Mark session as finished
                        desto_manager.session_manager.finish_session(session_name)
                        break
                    except Exception as e:
                        logger.debug(f"Error updating Redis for finished session {session_name}: {e}")
                        break
        except Exception as e:
            logger.debug(f"Error in Redis monitoring for {session_name}: {e}")

    # Start monitoring in a daemon thread
    threading.Thread(target=monitor, daemon=True).start()


def main():
    print("[SCHEDULED WRAPPER] main() entered", sys.argv)
    logger.info("[SCHEDULED WRAPPER] start_scheduled_session.py script started with args: {}", sys.argv)
    if len(sys.argv) < 3:
        print("[SCHEDULED WRAPPER] Not enough arguments", sys.argv)
        logger.debug("Usage: start_scheduled_session.py <session_name> <command>", file=sys.stderr)
        sys.exit(1)

    session_name = sys.argv[1]
    command = " ".join(sys.argv[2:])  # Join all remaining args as the command

    try:
        from src.desto.redis.client import DestoRedisClient
        from src.desto.redis.desto_manager import DestoManager

        # Initialize Redis tracking
        client = DestoRedisClient()
        if client.is_connected():
            manager = DestoManager(client)
            from datetime import datetime

            from src.desto.redis.models import SessionStatus

            # Try to find an existing scheduled session with this name
            existing_session = None
            try:
                existing_session = manager.session_manager.get_session_by_name(session_name)
            except Exception as e:
                logger.warning(f"[SCHEDULED WRAPPER] Could not check for existing session: {e}")

            if existing_session:
                if getattr(existing_session, "status", None) == SessionStatus.SCHEDULED:
                    # Re-use the scheduled session: update status and start_time
                    session = existing_session
                    logger.info(f"[SCHEDULED WRAPPER] Found existing scheduled session '{session_name}' (id={session.session_id}), updating to RUNNING")
                else:
                    # Existing session is not scheduled, create a new SCHEDULED session
                    logger.info(f"[SCHEDULED WRAPPER] Existing session found but not SCHEDULED, " f"creating new session '{session_name}' in Redis with status SCHEDULED")
                    session, job = manager.start_session_with_job(
                        session_name=session_name,
                        command=command,
                        script_path=command,
                        status=SessionStatus.SCHEDULED,
                    )
            else:
                # No session exists, create a new SCHEDULED session
                logger.info(f"[SCHEDULED WRAPPER] No existing session found, creating session '{session_name}' in Redis with status SCHEDULED")
                session, job = manager.start_session_with_job(
                    session_name=session_name,
                    command=command,
                    script_path=command,
                    status=SessionStatus.SCHEDULED,
                )

            # Now, always update to RUNNING and set start_time
            logger.info(f"[SCHEDULED WRAPPER] Updating session '{session_name}' status to RUNNING and launching tmux")
            session.status = SessionStatus.RUNNING
            session.start_time = datetime.now()
            session_id = session.session_id
            session_key = f"desto:session:{session_id}"
            logger.info(f"[SCHEDULED WRAPPER] Session object: id={session_id}, name={session_name}, status={session.status}, start_time={session.start_time}")
            manager.session_manager._update_session(session)
            logger.info(f"[SCHEDULED WRAPPER] Session '{session_name}' status set to RUNNING, start_time set to {session.start_time.isoformat()}")

            # Patch: Set the first job's start_time to match the session's start_time
            # This ensures job and session durations are measured from the same moment
            if hasattr(session, "job_ids") and session.job_ids:
                first_job_id = session.job_ids.split(",")[0] if isinstance(session.job_ids, str) else session.job_ids[0]
                if first_job_id:
                    job_key = f"desto:job:{first_job_id}"
                    # Update job's start_time in Redis
                    redis_client = manager.client if hasattr(manager, "client") else None
                    if redis_client is None:
                        from src.desto.redis.client import DestoRedisClient

                        redis_client = DestoRedisClient()
                    redis_client.redis.hset(job_key, "start_time", session.start_time.isoformat())
                    logger.info(f"[SCHEDULED WRAPPER] Set job {first_job_id} start_time to session start_time {session.start_time.isoformat()}")

            # Log job info if available
            if "job" in locals():
                logger.info(f"[SCHEDULED WRAPPER] Job object: id={getattr(job, 'job_id', None)}, " f"session_id={getattr(job, 'session_id', None)}, status={getattr(job, 'status', None)}")

            # Compose the wrapped command to run in tmux
            # Find mark_job_finished.py script path
            from pathlib import Path

            script_path = Path(__file__).parent / "mark_job_finished.py"
            if not script_path.exists():
                # Try project root
                script_path = Path(__file__).parent.parent / "scripts" / "mark_job_finished.py"
            if not script_path.exists():
                # Try CWD (Docker)
                script_path = Path.cwd() / "scripts" / "mark_job_finished.py"
            if not script_path.exists():
                logger.error("[SCHEDULED WRAPPER] Could not find mark_job_finished.py script!")
                sys.exit(1)

            # Build the log file path in Python
            log_file = _log_dir / f"{session_name}.log"

            # Determine if this is a chain (multiple scripts separated by '&&')
            # For simplicity, if '&&' is in the command, treat as chain
            is_chain = "&&" in command

            def extract_script_name(parts):
                # Try to find a part that looks like a script file
                from pathlib import Path as _Path

                for p in parts:
                    if p.endswith(".py") or p.endswith(".sh") or (p.startswith("'./") and len(p) > 3):
                        return _Path(p.strip("'\"")).name
                # Fallback: look for first arg after 'python3' or 'bash'
                for i, p in enumerate(parts):
                    if p in ("python3", "bash") and i + 1 < len(parts):
                        return _Path(parts[i + 1].strip("'\"")).name
                # Fallback: last part
                return _Path(parts[-1]).name if parts else "script"

            if is_chain:
                # Split the command into scripts (naive split on '&&')
                script_cmds = [c.strip() for c in command.split("&&")]
                total_scripts = len(script_cmds)
                marked_cmds = []
                # Add SCRIPT STARTING marker with timestamp before the first script
                starting_marker = f'printf "\\n=== SCRIPT STARTING at %s ===\\n" "$(date)" >> \'{log_file}\''
                marked_cmds.append(starting_marker)
                for idx, scmd in enumerate(script_cmds):
                    parts = scmd.split()
                    script_name = extract_script_name(parts)
                    marker = f"printf \"\\n=== Running script {idx + 1} of {total_scripts}: {script_name} ===\\n\" >> '{log_file}'"
                    # Run the script and append its output to the log file
                    run_script = f"({scmd}) >> '{log_file}' 2>&1"
                    marked_cmds.append(f"{marker} && {run_script}")
                chained_cmd = " && ".join(marked_cmds)
                bash_cmd = (
                    f"{chained_cmd}; "
                    f"SCRIPT_EXIT_CODE=$?; "
                    f'printf "\n=== SCRIPT FINISHED at %s (exit code: $SCRIPT_EXIT_CODE) ===\n" "$(date)" >> \'{log_file}\'; '
                    f"python3 '{script_path}' '{session_name}' $SCRIPT_EXIT_CODE; "
                    "exit $SCRIPT_EXIT_CODE"
                )
            else:
                parts = command.split()
                script_name = extract_script_name(parts)
                starting_marker = f'printf "\\n=== SCRIPT STARTING at %s ===\\n" "$(date)" >> \'{log_file}\''
                marker = f"printf \"\\n=== Running script: {script_name} ===\\n\" >> '{log_file}'"
                run_script = f"({command}) >> '{log_file}' 2>&1"
                bash_cmd = (
                    f"{starting_marker} && {marker} && {run_script}; "
                    f"SCRIPT_EXIT_CODE=$?; "
                    f'printf "\n=== SCRIPT FINISHED at %s (exit code: $SCRIPT_EXIT_CODE) ===\n" "$(date)" >> \'{log_file}\'; '
                    f"python3 '{script_path}' '{session_name}' $SCRIPT_EXIT_CODE; "
                    "exit $SCRIPT_EXIT_CODE"
                )

            tmux_cmd = ["tmux", "new-session", "-d", "-s", session_name, "bash", "-c", bash_cmd]
            logger.info(f"[SCHEDULED WRAPPER] Running tmux command: {tmux_cmd}")

            # Start the tmux session
            logger.debug(f"[SCHEDULED WRAPPER] Starting scheduled tmux session: {session_name}")
            result = subprocess.run(tmux_cmd, capture_output=True, text=True)

            logger.info(f"[SCHEDULED WRAPPER] tmux stdout: {result.stdout}")
            logger.info(f"[SCHEDULED WRAPPER] tmux returncode: {result.returncode}")

            if result.returncode != 0:
                logger.error(f"[SCHEDULED WRAPPER] Failed to start tmux session: {result.stderr}")
                sys.exit(1)

            logger.info(f"[SCHEDULED WRAPPER] Tmux session '{session_name}' started successfully")
    except ImportError as e:
        print(f"[SCHEDULED WRAPPER] ImportError: {e}")
        logger.error(f"Import error: {e}. Ensure you have the destomodule installed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
