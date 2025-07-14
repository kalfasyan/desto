"""Job manager for handling script execution within sessions."""

from datetime import datetime
from typing import List, Optional

from loguru import logger

from .client import DestoRedisClient
from .models import DestoJob, JobStatus


class JobManager:
    """Manages job execution within sessions."""

    def __init__(self, redis_client: DestoRedisClient):
        self.redis = redis_client

    def create_job(self, session_id: str, command: str, script_path: str) -> DestoJob:
        """Create a new job within a session."""
        job = DestoJob(session_id=session_id, command=command, script_path=script_path, status=JobStatus.QUEUED)

        # Store in Redis
        job_key = f"desto:job:{job.job_id}"
        self.redis.redis.hset(job_key, mapping=job.to_dict())

        # Auto-expire after 7 days
        expire_seconds = 7 * 86400
        self.redis.redis.expire(job_key, expire_seconds)

        logger.info(f"Created job {job.job_id} for session {session_id}")
        return job

    def start_job(self, job_id: str) -> bool:
        """Mark job as running."""
        job = self.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return False

        job.status = JobStatus.RUNNING
        job.start_time = datetime.now()
        self._update_job(job)

        logger.info(f"Started job {job_id}")
        return True

    def finish_job(self, job_id: str, exit_code: int = 0) -> bool:
        """Mark job as finished."""
        job = self.get_job(job_id)
        if not job:
            return False

        job.status = JobStatus.FINISHED
        job.end_time = datetime.now()
        job.exit_code = exit_code
        self._update_job(job)

        logger.info(f"Finished job {job_id} with exit code {exit_code}")

        # Check if we should start next job in session
        self._try_start_next_job(job.session_id)
        return True

    def fail_job(self, job_id: str, error_message: str) -> bool:
        """Mark job as failed."""
        job = self.get_job(job_id)
        if not job:
            return False

        job.status = JobStatus.FAILED
        job.end_time = datetime.now()
        job.error_message = error_message
        self._update_job(job)

        logger.info(f"Failed job {job_id}: {error_message}")
        return True

    def get_job(self, job_id: str) -> Optional[DestoJob]:
        """Get job by ID."""
        job_key = f"desto:job:{job_id}"
        data = self.redis.redis.hgetall(job_key)
        return DestoJob.from_dict(data) if data else None

    def get_jobs_for_session(self, session_id: str) -> List[DestoJob]:
        """Get all jobs for a session."""
        jobs = []
        for key in self.redis.redis.scan_iter(match="desto:job:*"):
            data = self.redis.redis.hgetall(key)
            if data:
                job = DestoJob.from_dict(data)
                if job.session_id == session_id:
                    jobs.append(job)

        # Sort by creation time (job_id contains timestamp info from UUID)
        jobs.sort(key=lambda j: j.job_id)
        return jobs

    def get_current_job_for_session(self, session_id: str) -> Optional[DestoJob]:
        """Get the currently running job for a session."""
        jobs = self.get_jobs_for_session(session_id)
        for job in jobs:
            if job.status == JobStatus.RUNNING:
                return job
        return None

    def queue_job(self, session_id: str, command: str, script_path: str) -> DestoJob:
        """Queue a job for execution in a session."""
        job = self.create_job(session_id, command, script_path)

        # Check if this should start immediately
        current_job = self.get_current_job_for_session(session_id)
        if not current_job:
            # No job running, start this one
            self.start_job(job.job_id)

        return job

    def get_job_status(self, job_id: str) -> str:
        """Get job status as string."""
        job = self.get_job(job_id)
        return job.status.value if job else "unknown"

    def get_session_job_status(self, session_id: str) -> str:
        """Get the overall job status for a session."""
        jobs = self.get_jobs_for_session(session_id)
        if not jobs:
            return "no_jobs"

        # Check for running job
        for job in jobs:
            if job.status == JobStatus.RUNNING:
                return "running"

        # Check for failed jobs
        for job in jobs:
            if job.status == JobStatus.FAILED:
                return "failed"

        # Check if all jobs are finished
        if all(job.status == JobStatus.FINISHED for job in jobs):
            return "finished"

        # Must have queued jobs
        return "queued"

    def _update_job(self, job: DestoJob):
        """Update job in Redis."""
        job_key = f"desto:job:{job.job_id}"
        self.redis.redis.hset(job_key, mapping=job.to_dict())

        # Publish update
        self._publish_update(job)

    def _publish_update(self, job: DestoJob):
        """Publish job update for real-time dashboard."""
        import json

        update_data = {
            "job_id": job.job_id,
            "session_id": job.session_id,
            "status": job.status.value,
            "timestamp": datetime.now().isoformat(),
        }
        self.redis.redis.publish("desto:job_updates", json.dumps(update_data))

    def _try_start_next_job(self, session_id: str):
        """Try to start the next queued job in the session."""
        jobs = self.get_jobs_for_session(session_id)

        # Find next queued job
        for job in jobs:
            if job.status == JobStatus.QUEUED:
                logger.info(f"Starting next queued job {job.job_id} in session {session_id}")
                self.start_job(job.job_id)
                break

    def get_job_duration(self, job_id: str) -> str:
        """Return the duration of a job as a human-readable string, or 'N/A' if not available."""
        job = self.get_job(job_id)
        if not job or not job.start_time or not job.end_time:
            return "N/A"
        start = job.start_time
        end = job.end_time
        from datetime import datetime

        # If start or end are strings, try to parse them
        if isinstance(start, str):
            try:
                start = datetime.fromisoformat(start)
            except Exception:
                return "N/A"
        if isinstance(end, str):
            try:
                end = datetime.fromisoformat(end)
            except Exception:
                return "N/A"
        elapsed = end - start
        total_seconds = int(elapsed.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
