"""Session manager for handling tmux session lifecycle."""

import threading
import time
from datetime import datetime
from typing import List, Optional

from loguru import logger

from .client import DestoRedisClient
from .models import DestoSession, SessionStatus


class SessionManager:
    """Manages session lifecycle and tmux operations."""

    def __init__(self, redis_client: DestoRedisClient):
        """Initialize session manager with a Redis client.

        Args:
            redis_client: Connected `DestoRedisClient` instance used for persistence.
        """
        self.redis = redis_client
        self._monitoring_threads = {}

    def create_session(self, session_name: str, tmux_session_name: str, status: SessionStatus = SessionStatus.STARTING) -> DestoSession:
        """Create a new session. Status can be STARTING or SCHEDULED."""
        session = DestoSession(
            session_name=session_name,
            tmux_session_name=tmux_session_name,
            start_time=datetime.now(),
            last_heartbeat=datetime.now(),
            status=status,
        )

        # Store in Redis
        session_key = f"desto:session:{session.session_id}"
        self.redis.redis.hset(session_key, mapping=session.to_dict())

        # Auto-expire after 7 days
        expire_seconds = 7 * 86400
        self.redis.redis.expire(session_key, expire_seconds)

        logger.info(f"Created session {session.session_name} with ID {session.session_id}")
        return session

    def start_session(self, session_id: str) -> bool:
        """Mark session as running and start monitoring."""
        session = self.get_session(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            return False

        session.status = SessionStatus.RUNNING
        self._update_session(session)

        # Start monitoring thread
        self._start_monitoring(session)

        logger.info(f"Started session {session.session_name}")
        return True

    def finish_session(self, session_id: str, exit_code: int = 0) -> bool:
        """Mark session as finished."""
        session = self.get_session(session_id)
        if not session:
            return False

        session.status = SessionStatus.FINISHED
        session.end_time = datetime.now()
        self._update_session(session)

        # Stop monitoring
        self._stop_monitoring(session_id)

        logger.info(f"Finished session {session.session_name}")
        return True

    def fail_session(self, session_id: str, error_message: str) -> bool:
        """Mark session as failed."""
        session = self.get_session(session_id)
        if not session:
            return False

        session.status = SessionStatus.FAILED
        session.end_time = datetime.now()
        self._update_session(session)

        # Stop monitoring
        self._stop_monitoring(session_id)

        logger.info(f"Failed session {session.session_name}: {error_message}")
        return True

    def update_heartbeat(self, session_id: str) -> bool:
        """Update session heartbeat."""
        session = self.get_session(session_id)
        if not session:
            return False

        session.last_heartbeat = datetime.now()
        self._update_session(session)
        return True

    def get_session(self, session_id: str) -> Optional[DestoSession]:
        """Get session by ID."""
        session_key = f"desto:session:{session_id}"
        data = self.redis.redis.hgetall(session_key)
        return DestoSession.from_dict(data) if data else None

    def get_session_by_name(self, session_name: str) -> Optional[DestoSession]:
        """Get session by name (for backward compatibility)."""
        # Scan all sessions to find by name
        for key in self.redis.redis.scan_iter(match="desto:session:*"):
            data = self.redis.redis.hgetall(key)
            if data:
                session = DestoSession.from_dict(data)
                if session.session_name == session_name:
                    return session
        return None

    def list_active_sessions(self) -> List[DestoSession]:
        """List all active sessions."""
        sessions = []
        for key in self.redis.redis.scan_iter(match="desto:session:*"):
            data = self.redis.redis.hgetall(key)
            if data:
                session = DestoSession.from_dict(data)
                if session.status in [SessionStatus.STARTING, SessionStatus.RUNNING]:
                    sessions.append(session)
        return sessions

    def list_all_sessions(self) -> List[DestoSession]:
        """List all sessions."""
        sessions = []
        for key in self.redis.redis.scan_iter(match="desto:session:*"):
            data = self.redis.redis.hgetall(key)
            if data:
                sessions.append(DestoSession.from_dict(data))
        return sessions

    def add_job_to_session(self, session_id: str, job_id: str) -> bool:
        """Add a job ID to session's job list."""
        session = self.get_session(session_id)
        if not session:
            return False

        if job_id not in session.job_ids:
            session.job_ids.append(job_id)
            self._update_session(session)
        return True

    def _update_session(self, session: DestoSession):
        """Update session in Redis."""
        session_key = f"desto:session:{session.session_id}"
        self.redis.redis.hset(session_key, mapping=session.to_dict())

        # Publish update
        self._publish_update(session)

    def _publish_update(self, session: DestoSession):
        """Publish session update for real-time dashboard."""
        import json

        update_data = {
            "session_id": session.session_id,
            "session_name": session.session_name,
            "status": session.status.value,
            "timestamp": datetime.now().isoformat(),
        }
        self.redis.redis.publish("desto:session_updates", json.dumps(update_data))

    def _start_monitoring(self, session: DestoSession):
        """Start monitoring thread for session."""
        if session.session_id in self._monitoring_threads:
            return  # Already monitoring

        def monitor():
            logger.debug(f"Starting monitoring for session {session.session_name}")
            while True:
                try:
                    current_session = self.get_session(session.session_id)
                    if not current_session or current_session.status not in [SessionStatus.RUNNING]:
                        logger.info(f"Stopping monitoring for session {session.session_name}")
                        break

                    # Update heartbeat
                    self.update_heartbeat(session.session_id)
                    time.sleep(5)

                except Exception as e:
                    logger.error(f"Error monitoring session {session.session_name}: {e}")
                    time.sleep(10)

            # Clean up thread reference
            if session.session_id in self._monitoring_threads:
                del self._monitoring_threads[session.session_id]

        thread = threading.Thread(target=monitor, daemon=True)
        self._monitoring_threads[session.session_id] = thread
        thread.start()

    def _stop_monitoring(self, session_id: str):
        """Stop monitoring thread for session."""
        if session_id in self._monitoring_threads:
            # Thread will stop automatically when session status changes
            del self._monitoring_threads[session_id]
