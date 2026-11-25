"""Wrapper for starting scheduled tmux sessions with proper Redis tracking.

This ensures scheduled jobs get the same Redis tracking as manually started sessions::

    DESTO_LOGS_DIR=<logs dir> python -m desto.hooks.start_scheduled_session <session_name> <command>
"""

import os
import subprocess
import sys

# Ensure loguru outputs to both stdout and a file, and set level to DEBUG
import sys as _sys
from pathlib import Path

from loguru import logger

logger.remove()
logger.add(_sys.stdout, level="DEBUG", enqueue=True)
# Use the dashboard's logs directory (passed via DESTO_LOGS_DIR), with error handling
_log_dir = Path(os.environ.get("DESTO_LOGS_DIR") or Path.cwd() / "desto_logs")
try:
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


def main():
    print("[SCHEDULED WRAPPER] main() entered", sys.argv)
    logger.info("[SCHEDULED WRAPPER] start_scheduled_session.py script started with args: {}", sys.argv)
    if len(sys.argv) < 3:
        print("[SCHEDULED WRAPPER] Not enough arguments", sys.argv)
        logger.debug("Usage: start_scheduled_session.py <session_name> <command>", file=sys.stderr)
        sys.exit(1)

    session_name = sys.argv[1]
    command = " ".join(sys.argv[2:])  # Join all remaining args as the command

    # FIRST: Check if tmux session already exists BEFORE any Redis operations
    # This prevents creating orphan jobs when the session is already running
    tmux_check = subprocess.run(["tmux", "has-session", "-t", session_name], capture_output=True, text=True)
    if tmux_check.returncode == 0:
        # Tmux session already exists - find existing Redis session and update it
        logger.info(f"[SCHEDULED WRAPPER] Tmux session '{session_name}' already exists. Checking Redis state.")
        try:
            from datetime import datetime

            from desto.redis.client import DestoRedisClient
            from desto.redis.desto_manager import DestoManager
            from desto.redis.models import SessionStatus

            client = DestoRedisClient()
            if client.is_connected():
                manager = DestoManager(client)

                # Try to find existing session
                existing_session = None
                try:
                    existing_session = manager.session_manager.get_session_by_name(session_name)
                except Exception as e:
                    logger.warning(f"[SCHEDULED WRAPPER] Could not check for existing session: {e}")

                if existing_session:
                    # Update existing session status to RUNNING
                    session = existing_session
                    session.status = SessionStatus.RUNNING
                    session.start_time = datetime.now()
                    manager.session_manager._update_session(session)
                    logger.info(f"[SCHEDULED WRAPPER] Updated existing session '{session_name}' to RUNNING")

                    # Update job status to RUNNING if needed
                    if hasattr(session, "job_ids") and session.job_ids:
                        first_job_id = session.job_ids.split(",")[0] if isinstance(session.job_ids, str) else session.job_ids[0]
                        if first_job_id:
                            job_key = f"desto:job:{first_job_id}"
                            job_data = client.redis.hgetall(job_key)
                            if job_data:
                                current_status = job_data.get("status", "")
                                if isinstance(current_status, bytes):
                                    current_status = current_status.decode()
                                if current_status not in ["running", "finished", "failed"]:
                                    client.redis.hset(job_key, "status", "running")
                                    logger.info(f"[SCHEDULED WRAPPER] Set job {first_job_id} status to RUNNING")
                                else:
                                    logger.info(f"[SCHEDULED WRAPPER] Job {first_job_id} already in status {current_status}")
                            else:
                                logger.warning(f"[SCHEDULED WRAPPER] Job {first_job_id} not found in Redis")
                else:
                    logger.warning(f"[SCHEDULED WRAPPER] Tmux session '{session_name}' exists but no Redis session found. Session may have been cleared.")

                sys.exit(0)
        except Exception as e:
            logger.error(f"[SCHEDULED WRAPPER] Error handling existing tmux session: {e}")
            sys.exit(0)  # Exit gracefully anyway since tmux session is running

    try:
        from desto.redis.client import DestoRedisClient
        from desto.redis.desto_manager import DestoManager

        # Initialize Redis tracking
        client = DestoRedisClient()
        if client.is_connected():
            manager = DestoManager(client)
            from datetime import datetime

            from desto.redis.models import SessionStatus

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
                    logger.info(f"[SCHEDULED WRAPPER] Existing session found but not SCHEDULED, creating new session '{session_name}' in Redis with status SCHEDULED")
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
                        from desto.redis.client import DestoRedisClient

                        redis_client = DestoRedisClient()
                    redis_client.redis.hset(job_key, "start_time", session.start_time.isoformat())
                    # FIX: Also update job status to RUNNING so mark_job_finished.py can find it
                    redis_client.redis.hset(job_key, "status", "running")
                    logger.info(f"[SCHEDULED WRAPPER] Set job {first_job_id} start_time to session start_time {session.start_time.isoformat()}")
                    logger.info(f"[SCHEDULED WRAPPER] Set job {first_job_id} status to RUNNING")

            # Log job info if available
            if "job" in locals():
                logger.info(f"[SCHEDULED WRAPPER] Job object: id={getattr(job, 'job_id', None)}, session_id={getattr(job, 'session_id', None)}, status={getattr(job, 'status', None)}")

            # Same wrapper as sessions started from the dashboard, TUI and CLI: banners, log file, exit code to Redis
            from desto.core.scripts import session_script

            log_file = _log_dir / f"{session_name}.log"
            bash_cmd = session_script(session_name, command, log_file)

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
