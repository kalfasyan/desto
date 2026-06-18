"""Unified manager that coordinates sessions and jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Tuple

from loguru import logger

from .client import DestoRedisClient
from .favorites_manager import FavoriteCommandsManager
from .job_manager import JobManager
from .models import DestoJob, DestoSession, SessionStatus
from .session_manager import SessionManager

if TYPE_CHECKING:
    from .sqlite_store import SQLiteStore


class DestoManager:
    """High-level manager that coordinates sessions and jobs."""

    def __init__(self, redis_client: DestoRedisClient, sqlite_store: Optional["SQLiteStore"] = None):
        self.redis = redis_client
        self.session_manager = SessionManager(redis_client)
        self.job_manager = JobManager(redis_client)
        self.favorites_manager = FavoriteCommandsManager(redis_client)
        self.sqlite_store = sqlite_store

    def start_session_with_job(self, session_name: str, command: str, script_path: str, status=None) -> Tuple[DestoSession, DestoJob]:
        """Start a new session with an initial job. If status is SCHEDULED, do not start immediately."""
        session_status = status if status is not None else SessionStatus.STARTING
        session = self.session_manager.create_session(
            session_name=session_name,
            tmux_session_name=session_name,  # Use same name for tmux
            status=session_status,
        )

        # Create and queue the first job
        job = self.job_manager.queue_job(session_id=session.session_id, command=command, script_path=script_path)

        # Add job to session
        self.session_manager.add_job_to_session(session.session_id, job.job_id)

        # Only start the session if not scheduled
        if session_status != SessionStatus.SCHEDULED:
            self.session_manager.start_session(session.session_id)
            logger.info(f"Started session {session_name} with job {job.job_id}")
        else:
            logger.info(f"Scheduled session {session_name} with job {job.job_id}")

        # Archive to SQLite for long-term persistence
        # Re-fetch the session to get the updated status (RUNNING, not STARTING)
        updated_session = self.session_manager.get_session(session.session_id)
        self._sqlite_save_session(updated_session or session)
        self._sqlite_save_job(job)

        return session, job

    def add_job_to_session(self, session_name: str, command: str, script_path: str) -> Optional[DestoJob]:
        """Add a job to an existing session (for chaining)."""
        session = self.session_manager.get_session_by_name(session_name)
        if not session:
            logger.error(f"Session {session_name} not found")
            return None

        # Queue the job
        job = self.job_manager.queue_job(session_id=session.session_id, command=command, script_path=script_path)

        # Add to session
        self.session_manager.add_job_to_session(session.session_id, job.job_id)

        logger.info(f"Added job {job.job_id} to session {session_name}")
        return job

    def finish_session(self, session_name: str, exit_code: int = 0) -> bool:
        """Finish a session (when tmux session ends)."""
        session = self.session_manager.get_session_by_name(session_name)
        if not session:
            return False
        # Only finish if not already failed
        if session.status == SessionStatus.FAILED:
            logger.info(f"Session {session_name} already failed, not marking as finished.")
            return False
        result = self.session_manager.finish_session(session.session_id, exit_code)

        # Archive final state to SQLite
        if result:
            updated_session = self.session_manager.get_session(session.session_id)
            if updated_session:
                self._sqlite_save_session(updated_session)

        return result

    def finish_job(self, session_name: str, exit_code: int = 0) -> bool:
        """Finish the current job in a session."""
        session = self.session_manager.get_session_by_name(session_name)
        if not session:
            return False

        current_job = self.job_manager.get_current_job_for_session(session.session_id)
        if not current_job:
            logger.warning(f"No running job found for session {session_name}")
            return False

        # Finish the job via JobManager
        success = self.job_manager.finish_job(current_job.job_id, exit_code)

        # Archive job to SQLite
        if success:
            updated_job = self.job_manager.get_job(current_job.job_id)
            if updated_job:
                self._sqlite_save_job(updated_job)

        # If finished successfully, try to send a notification (Pushbullet) for redundancy.
        if success:
            try:
                # Import lazily so notifications remain optional and don't add a hard dependency.
                from desto.notifications import notify_job_finished
            except Exception:
                notify_job_finished = None

            if notify_job_finished:
                try:
                    # Re-read the job to obtain the authoritative end_time set by JobManager
                    job = self.job_manager.get_job(current_job.job_id)
                    finished_at = None
                    if job and getattr(job, "end_time", None):
                        end = job.end_time
                        # end may be a datetime or string
                        if hasattr(end, "isoformat"):
                            finished_at = end.isoformat()
                        else:
                            finished_at = str(end)

                    notify_job_finished(session_name, exit_code, finished_at)
                except Exception as e:
                    logger.debug(f"Failed to send notification for job finish: {e}", exc_info=True)

        return success

    def fail_job(self, session_name: str, error_message: str) -> bool:
        """Fail the current job in a session."""
        session = self.session_manager.get_session_by_name(session_name)
        if not session:
            return False

        current_job = self.job_manager.get_current_job_for_session(session.session_id)
        if not current_job:
            logger.warning(f"No running job found for session {session_name}")
            return False

        result = self.job_manager.fail_job(current_job.job_id, error_message)

        # Archive failed job to SQLite
        if result:
            updated_job = self.job_manager.get_job(current_job.job_id)
            if updated_job:
                self._sqlite_save_job(updated_job)

        return result

    def get_session_status(self, session_name: str) -> Optional[str]:
        """Get session status by name."""
        session = self.session_manager.get_session_by_name(session_name)
        return session.status.value if session else None

    def get_job_status(self, session_name: str) -> str:
        """Get job status for a session."""
        session = self.session_manager.get_session_by_name(session_name)
        if not session:
            return "unknown"

        return self.job_manager.get_session_job_status(session.session_id)

    def is_session_finished(self, session_name: str) -> bool:
        """Check if session is finished."""
        status = self.get_session_status(session_name)
        return status in ["finished", "failed"] if status else False

    def update_heartbeat(self, session_name: str) -> bool:
        """Update session heartbeat."""
        session = self.session_manager.get_session_by_name(session_name)
        if not session:
            return False

        return self.session_manager.update_heartbeat(session.session_id)

    def get_all_active_sessions(self):
        """Get all active sessions with their job information."""
        sessions = self.session_manager.list_active_sessions()
        result = {}

        for session in sessions:
            jobs = self.job_manager.get_jobs_for_session(session.session_id)
            current_job = self.job_manager.get_current_job_for_session(session.session_id)

            session_data = session.to_dict()
            session_data.update(
                {
                    "job_count": len(jobs),
                    "current_job_status": current_job.status.value if current_job else "none",
                    "overall_job_status": self.job_manager.get_session_job_status(session.session_id),
                }
            )

            result[session.session_name] = session_data

        return result

    # ─── SQLite Persistence Helpers ───────────────────────────────────────

    def _sqlite_save_session(self, session: DestoSession):
        """Persist session to SQLite if the store is enabled."""
        if self.sqlite_store and self.sqlite_store.enabled:
            try:
                self.sqlite_store.save_session(session)
            except Exception as e:
                logger.debug(f"SQLite archive failed for session {session.session_id}: {e}")

    def _sqlite_save_job(self, job: DestoJob):
        """Persist job to SQLite if the store is enabled."""
        if self.sqlite_store and self.sqlite_store.enabled:
            try:
                self.sqlite_store.save_job(job)
            except Exception as e:
                logger.debug(f"SQLite archive failed for job {job.job_id}: {e}")
