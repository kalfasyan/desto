"""Recurring schedules built on self-re-arming ``at`` jobs.

A schedule lives in Redis at ``desto:recurring:<id>``. Only its next run is queued with
``at``, as ``python -m desto.hooks.run_recurring <id> <occurrence>``. When that job fires,
it queues the following run and then launches the session, so schedules keep running
while the dashboard is closed, just like one-off scheduled jobs.
"""

import shlex
import sys
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from loguru import logger

from .at_job_manager import AtJobManager
from .client import DestoRedisClient

RECURRING_PREFIX = "desto:recurring:"
CLAIM_PREFIX = "desto:recurring_claim:"
CLAIM_TTL_SECONDS = 7 * 24 * 3600
OCCURRENCE_FORMAT = "%Y-%m-%dT%H:%M"

# Minutes per repeat unit offered in the dashboard
REPEAT_UNITS = {"minutes": 1, "hours": 60, "days": 24 * 60, "weeks": 7 * 24 * 60}


def describe_interval(interval_minutes: int) -> str:
    """Human-readable form of an interval, e.g. 'every day' or 'every 15 minutes'."""
    for unit in ("weeks", "days", "hours", "minutes"):
        size = REPEAT_UNITS[unit]
        if interval_minutes % size == 0:
            count = interval_minutes // size
            return f"every {unit[:-1]}" if count == 1 else f"every {count} {unit}"
    return f"every {interval_minutes} minutes"


def next_occurrence(anchor: datetime, interval_minutes: int, after: datetime) -> datetime:
    """First run strictly after ``after``, aligned to ``anchor``. Runs missed while the machine was off are skipped."""
    if anchor > after:
        return anchor
    step = timedelta(minutes=interval_minutes)
    return anchor + ((after - anchor) // step + 1) * step


def occurrence_session_name(base_name: str, occurrence: datetime) -> str:
    """Each run gets its own tmux session so runs keep separate logs and history."""
    return f"{base_name}-{occurrence:%Y%m%d-%H%M}"


class RecurringScheduleManager:
    """Create, arm, claim and cancel recurring schedules."""

    def __init__(self, redis_client: DestoRedisClient, at_job_manager: Optional[AtJobManager] = None):
        self.client = redis_client
        self.redis = redis_client.redis
        self.at_job_manager = at_job_manager or AtJobManager(redis_client)

    def create(
        self,
        session_name: str,
        command: str,
        interval_minutes: int,
        first_run: datetime,
        log_dir: str,
        script_paths: Optional[List[str]] = None,
        arguments: str = "",
    ) -> Optional[str]:
        """Store a schedule and queue its first run. Returns the schedule id, or None if it could not be queued."""
        if interval_minutes < 1:
            raise ValueError("Repeat interval must be at least 1 minute")

        schedule_id = uuid.uuid4().hex[:12]
        schedule = {
            "id": schedule_id,
            "session_name": session_name,
            "command": command,
            "interval_minutes": str(interval_minutes),
            "anchor": first_run.replace(second=0, microsecond=0).strftime(OCCURRENCE_FORMAT),
            "log_dir": str(log_dir),
            "script_path": shlex.join(script_paths or []),
            "arguments": arguments,
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "run_count": "0",
            "next_run": "",
            "pending_at_job_id": "",
            "last_run_at": "",
            "last_session_name": "",
            "last_result": "",
        }
        self.redis.hset(self._key(schedule_id), mapping=schedule)

        if not self.arm(schedule, datetime.strptime(schedule["anchor"], OCCURRENCE_FORMAT)):
            self.redis.delete(self._key(schedule_id))
            return None
        logger.info(f"Created recurring schedule {schedule_id} for '{session_name}' ({describe_interval(interval_minutes)})")
        return schedule_id

    def get(self, schedule_id: str) -> Optional[Dict[str, str]]:
        schedule = self.redis.hgetall(self._key(schedule_id))
        return schedule or None

    def list(self, active_only: bool = False) -> List[Dict[str, str]]:
        schedules = []
        for key in self.redis.scan_iter(match=f"{RECURRING_PREFIX}*"):
            schedule = self.redis.hgetall(key)
            if schedule and (not active_only or schedule.get("status") == "active"):
                schedules.append(schedule)
        return schedules

    def arm(self, schedule: Dict[str, str], occurrence: datetime) -> Optional[str]:
        """Queue one run with ``at``. Returns the at job id, or None on failure."""
        schedule_id = schedule["id"]
        occurrence_str = occurrence.strftime(OCCURRENCE_FORMAT)
        command = f"{shlex.quote(sys.executable)} -m desto.hooks.run_recurring {shlex.quote(schedule_id)} {occurrence_str}"
        at_job_id = self.at_job_manager.schedule(
            command=command,
            time_spec=occurrence.strftime("%H:%M %Y-%m-%d"),
            session_name=occurrence_session_name(schedule["session_name"], occurrence),
            script_path=shlex.split(schedule.get("script_path", "")),
            arguments=schedule.get("arguments", ""),
            extra_metadata={"recurring_id": schedule_id, "recurrence": describe_interval(int(schedule["interval_minutes"]))},
        )
        if at_job_id:
            self.redis.hset(self._key(schedule_id), mapping={"next_run": occurrence_str, "pending_at_job_id": at_job_id})
        else:
            logger.error(f"Failed to queue next run of recurring schedule {schedule_id} at {occurrence_str}")
        return at_job_id

    def claim(self, schedule_id: str, occurrence: datetime) -> bool:
        """Return True only for the first caller per run, so a run fires once even if both atd and the dashboard's overdue check trigger it."""
        key = f"{CLAIM_PREFIX}{schedule_id}:{occurrence.strftime(OCCURRENCE_FORMAT)}"
        return bool(self.redis.set(key, "1", nx=True, ex=CLAIM_TTL_SECONDS))

    def record_run(self, schedule_id: str, result: str, session_name: str = "") -> None:
        fields = {"last_run_at": datetime.now().isoformat(), "last_result": result}
        if session_name:
            fields["last_session_name"] = session_name
        self.redis.hset(self._key(schedule_id), mapping=fields)
        if result == "started":
            self.redis.hincrby(self._key(schedule_id), "run_count", 1)

    def cancel(self, schedule_id: str, remove_pending_job: bool = True) -> bool:
        """Stop all future runs. Runs already in progress are left alone."""
        schedule = self.get(schedule_id)
        if not schedule:
            return False
        # Mark cancelled before removing the at job, so a run firing in between does not queue another
        self.redis.hset(self._key(schedule_id), mapping={"status": "cancelled", "next_run": ""})
        pending = schedule.get("pending_at_job_id")
        if remove_pending_job and pending:
            self.at_job_manager.cancel(pending)
        logger.info(f"Cancelled recurring schedule {schedule_id} ('{schedule.get('session_name')}')")
        return True

    def cancel_all(self, remove_pending_jobs: bool = True) -> int:
        schedules = self.list(active_only=True)
        for schedule in schedules:
            self.cancel(schedule["id"], remove_pending_job=remove_pending_jobs)
        return len(schedules)

    @staticmethod
    def _key(schedule_id: str) -> str:
        return f"{RECURRING_PREFIX}{schedule_id}"
