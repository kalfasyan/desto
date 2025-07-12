import json
from datetime import datetime, timedelta
from typing import Dict, Optional

from loguru import logger

from .client import DestoRedisClient


class SessionStatusTracker:
    def __init__(self, redis_client: DestoRedisClient):
        self.redis = redis_client

    def mark_session_started(self, session_name: str, command: str, script_path: str):
        """Replace your current session tracking logic"""
        # Ensure no None values
        session_data = {
            "session_name": session_name,
            "status": "running",
            "command": command or "",
            "script_path": script_path or "",
            "start_time": datetime.now().isoformat(),
            "last_heartbeat": datetime.now().isoformat(),
            "pid": "",  # Empty string instead of None
        }

        try:
            self.redis.redis.hset(self.redis.get_session_key(session_name), mapping=session_data)

            # Auto-expire after configured session history days (default 7 days)
            expire_seconds = 7 * 86400  # 7 days in seconds
            self.redis.redis.expire(self.redis.get_session_key(session_name), expire_seconds)

            # Publish to dashboard
            self._publish_status_update(session_name, session_data)

        except Exception as e:
            logger.error(f"Redis error in mark_session_started: {e}")
            # Don't crash - just log the error

    def mark_session_finished(self, session_name: str, exit_code: int = 0):
        """Mark the entire session as finished (tmux session ended)"""
        finish_data = {
            "status": "finished",
            "exit_code": str(exit_code),
            "end_time": datetime.now().isoformat(),
            "duration": self._calculate_duration(session_name),
            "elapsed": self._calculate_elapsed(session_name),  # This now uses job_finished_time if available
        }

        self.redis.redis.hset(self.redis.get_session_key(session_name), mapping=finish_data)

        # Publish to dashboard
        self._publish_status_update(session_name, finish_data)

    def mark_session_failed(self, session_name: str, error_message: str):
        """Mark session as failed"""
        fail_data = {
            "status": "failed",
            "error": error_message,
            "end_time": datetime.now().isoformat(),
            "duration": self._calculate_duration(session_name),
        }

        self.redis.redis.hset(self.redis.get_session_key(session_name), mapping=fail_data)

        self._publish_status_update(session_name, fail_data)

    def update_heartbeat(self, session_name: str):
        """Update session heartbeat - called by your monitoring loop"""
        self.redis.redis.hset(self.redis.get_session_key(session_name), "last_heartbeat", datetime.now().isoformat())

    def get_session_status(self, session_name: str) -> Optional[Dict]:
        """Get session status - replaces checking .finished files"""
        session_data = self.redis.redis.hgetall(self.redis.get_session_key(session_name))
        return session_data if session_data else None

    def is_session_finished(self, session_name: str) -> bool:
        """Replace your .finished file checking"""
        status = self.redis.redis.hget(self.redis.get_session_key(session_name), "status")
        return status in ["finished", "failed"]

    def get_all_active_sessions(self) -> Dict[str, Dict]:
        """Get all active sessions - replaces scanning directories"""
        sessions = {}
        for key in self.redis.redis.scan_iter(match=f"{self.redis.session_prefix}*"):
            session_name = key.replace(self.redis.session_prefix, "")
            session_data = self.redis.redis.hgetall(key)
            if session_data.get("status") == "running":
                sessions[session_name] = session_data
        return sessions

    def cleanup_old_sessions(self, hours_old: int = 24):
        """Clean up old session data"""
        cutoff_time = datetime.now() - timedelta(hours=hours_old)

        for key in self.redis.redis.scan_iter(match=f"{self.redis.session_prefix}*"):
            session_data = self.redis.redis.hgetall(key)
            if session_data.get("end_time"):
                end_time = datetime.fromisoformat(session_data["end_time"])
                if end_time < cutoff_time:
                    self.redis.redis.delete(key)

    def _calculate_duration(self, session_name: str) -> str:
        """Calculate session duration"""
        session_data = self.redis.redis.hgetall(self.redis.get_session_key(session_name))
        if session_data.get("start_time"):
            start_time = datetime.fromisoformat(session_data["start_time"])
            duration = datetime.now() - start_time
            return str(duration)
        return "unknown"

    def _calculate_elapsed(self, session_name: str) -> str:
        """Calculate elapsed time from start to job finish (script execution time only)"""
        try:
            session_data = self.redis.redis.hgetall(self.redis.get_session_key(session_name))
            if not session_data:
                return "N/A"

            # Handle bytes from Redis
            if isinstance(list(session_data.values())[0], bytes):
                session_data = {
                    k.decode("utf-8") if isinstance(k, bytes) else k: v.decode("utf-8") if isinstance(v, bytes) else v
                    for k, v in session_data.items()
                }

            start_time_str = session_data.get("start_time")
            if not start_time_str:
                return "N/A"

            start_time = datetime.fromisoformat(start_time_str)

            # Use job_finished_time if available (job completed), otherwise current time
            job_finished_time_str = session_data.get("job_finished_time")
            if job_finished_time_str:
                # Job is finished, use the stored job_finished_time (script execution time only)
                end_time = datetime.fromisoformat(job_finished_time_str)
            else:
                # Job is still running, use current time
                end_time = datetime.now()

            elapsed = end_time - start_time

            return str(elapsed)
        except Exception as e:
            logger.error(f"Error calculating elapsed time: {e}")
            return "N/A"

    def mark_job_finished(self, session_name: str, exit_code: int = 0):
        """Mark the job as finished (script completed) - separate from session end"""
        job_finish_data = {
            "job_status": "finished",
            "job_exit_code": str(exit_code),
            "job_finished_time": datetime.now().isoformat(),
            "job_elapsed": self._calculate_job_elapsed(session_name),
        }

        self.redis.redis.hset(self.redis.get_session_key(session_name), mapping=job_finish_data)

        # Publish to dashboard
        self._publish_status_update(session_name, job_finish_data)

    def mark_job_failed(self, session_name: str, error_message: str):
        """Mark the job as failed (script failed) - separate from session end"""
        job_fail_data = {
            "job_status": "failed",
            "job_error": error_message,
            "job_finished_time": datetime.now().isoformat(),
            "job_elapsed": self._calculate_job_elapsed(session_name),
        }

        self.redis.redis.hset(self.redis.get_session_key(session_name), mapping=job_fail_data)

        self._publish_status_update(session_name, job_fail_data)

    def _calculate_job_elapsed(self, session_name: str) -> str:
        """Calculate job elapsed time from start to job completion"""
        try:
            session_data = self.redis.redis.hgetall(self.redis.get_session_key(session_name))
            if not session_data:
                return "N/A"

            # Handle bytes from Redis
            if isinstance(list(session_data.values())[0], bytes):
                session_data = {
                    k.decode("utf-8") if isinstance(k, bytes) else k: v.decode("utf-8") if isinstance(v, bytes) else v
                    for k, v in session_data.items()
                }

            start_time_str = session_data.get("start_time")
            if not start_time_str:
                return "N/A"

            start_time = datetime.fromisoformat(start_time_str)

            # Use job_finished_time if available (job completed), otherwise current time
            job_finished_time_str = session_data.get("job_finished_time")
            if job_finished_time_str:
                # Job is finished, use the stored job_finished_time
                end_time = datetime.fromisoformat(job_finished_time_str)
            else:
                # Job is still running, use current time
                end_time = datetime.now()

            elapsed = end_time - start_time
            return str(elapsed)

        except Exception as e:
            logger.error(f"Error calculating job elapsed time: {e}")
            return "N/A"

    def get_job_status(self, session_name: str) -> str:
        """
        Get the current job status for a session.

        Args:
            session_name: The name of the session

        Returns:
            str: The job status ("running", "finished", "failed", or "unknown")
        """
        try:
            session_data = self.redis.redis.hgetall(self.redis.get_session_key(session_name))
            if not session_data:
                return "unknown"

            # Handle bytes from Redis
            if isinstance(list(session_data.values())[0], bytes):
                session_data = {
                    k.decode("utf-8") if isinstance(k, bytes) else k: v.decode("utf-8") if isinstance(v, bytes) else v
                    for k, v in session_data.items()
                }

            # Check job status - defaults to "running" if not set
            job_status = session_data.get("job_status", "running")
            return job_status

        except Exception as e:
            logger.error(f"Error getting job status for {session_name}: {e}")
            return "unknown"

    def _publish_status_update(self, session_name: str, data: Dict):
        """Publish status update for real-time dashboard"""
        update_data = {"session_name": session_name, "timestamp": datetime.now().isoformat(), **data}

        self.redis.redis.publish("desto:session_updates", json.dumps(update_data))
