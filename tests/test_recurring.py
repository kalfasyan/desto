"""Tests for recurring schedules (desto.redis.recurring and desto.hooks.run_recurring)."""

import subprocess
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from desto.hooks import run_recurring
from desto.redis.client import DestoRedisClient
from desto.redis.recurring import CLAIM_PREFIX, RECURRING_PREFIX, RecurringScheduleManager, describe_interval, next_occurrence, occurrence_session_name


@pytest.mark.parametrize(
    "minutes, expected",
    [(1, "every minute"), (15, "every 15 minutes"), (60, "every hour"), (180, "every 3 hours"), (1440, "every day"), (2880, "every 2 days"), (10080, "every week"), (90, "every 90 minutes")],
)
def test_describe_interval(minutes, expected):
    assert describe_interval(minutes) == expected


class TestNextOccurrence:
    anchor = datetime(2026, 1, 1, 9, 0)

    def test_future_anchor_is_first_run(self):
        assert next_occurrence(self.anchor, 60, after=datetime(2025, 12, 31)) == self.anchor

    def test_stays_aligned_to_anchor(self):
        assert next_occurrence(self.anchor, 60, after=datetime(2026, 1, 1, 11, 20)) == datetime(2026, 1, 1, 12, 0)

    def test_is_strictly_after(self):
        assert next_occurrence(self.anchor, 60, after=datetime(2026, 1, 1, 10, 0)) == datetime(2026, 1, 1, 11, 0)

    def test_skips_missed_runs(self):
        assert next_occurrence(self.anchor, 1440, after=datetime(2026, 1, 10, 8, 0)) == datetime(2026, 1, 10, 9, 0)


def test_occurrence_session_name():
    assert occurrence_session_name("backup", datetime(2026, 3, 4, 5, 6)) == "backup-20260304-0506"


class FakeAtJobManager:
    def __init__(self, job_id="900"):
        self.job_id = job_id
        self.scheduled = []
        self.cancelled = []

    def schedule(self, **kwargs):
        self.scheduled.append(kwargs)
        return self.job_id

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        return True


@pytest.fixture
def redis_client(monkeypatch):
    # A separate DB keeps tests away from real schedules; the hook reads REDIS_DB too
    monkeypatch.setenv("REDIS_DB", "15")
    client = DestoRedisClient()
    if not client.is_connected():
        pytest.skip("Redis not available")
    yield client
    for pattern in (f"{RECURRING_PREFIX}*", f"{CLAIM_PREFIX}*"):
        for key in client.redis.scan_iter(match=pattern):
            client.redis.delete(key)


@pytest.fixture
def at_jobs():
    return FakeAtJobManager()


@pytest.fixture
def manager(redis_client, at_jobs):
    return RecurringScheduleManager(redis_client, at_job_manager=at_jobs)


FIRST_RUN = datetime(2030, 5, 1, 6, 30)


def create(manager, **overrides):
    kwargs = dict(session_name=f"rec-{uuid.uuid4().hex[:6]}", command="bash /s/backup.sh", interval_minutes=1440, first_run=FIRST_RUN, log_dir="/logs", script_paths=["/s/backup.sh"])
    kwargs.update(overrides)
    return manager.create(**kwargs)


class TestRecurringScheduleManager:
    def test_create_queues_first_run(self, manager, at_jobs):
        schedule_id = create(manager, session_name="backup")

        [queued] = at_jobs.scheduled
        assert queued["time_spec"] == "06:30 2030-05-01"
        assert queued["command"].endswith(f"-m desto.hooks.run_recurring {schedule_id} 2030-05-01T06:30")
        assert queued["session_name"] == "backup-20300501-0630"
        assert queued["script_path"] == ["/s/backup.sh"]
        assert queued["extra_metadata"] == {"recurring_id": schedule_id, "recurrence": "every day"}

        schedule = manager.get(schedule_id)
        assert schedule["status"] == "active"
        assert schedule["next_run"] == "2030-05-01T06:30"
        assert schedule["pending_at_job_id"] == "900"

    def test_create_rejects_zero_interval(self, manager):
        with pytest.raises(ValueError):
            create(manager, interval_minutes=0)

    def test_create_leaves_nothing_behind_when_at_fails(self, manager, at_jobs):
        at_jobs.job_id = None
        before = {s["id"] for s in manager.list()}

        assert create(manager) is None
        assert {s["id"] for s in manager.list()} == before

    def test_claim_succeeds_once_per_run(self, manager):
        schedule_id = create(manager)

        assert manager.claim(schedule_id, FIRST_RUN) is True
        assert manager.claim(schedule_id, FIRST_RUN) is False
        assert manager.claim(schedule_id, FIRST_RUN + timedelta(days=1)) is True

    def test_cancel_removes_pending_run(self, manager, at_jobs):
        schedule_id = create(manager)

        assert manager.cancel(schedule_id) is True
        assert manager.get(schedule_id)["status"] == "cancelled"
        assert at_jobs.cancelled == ["900"]
        assert schedule_id not in {s["id"] for s in manager.list(active_only=True)}

    def test_cancel_all_can_leave_at_jobs_to_caller(self, manager, at_jobs):
        ids = [create(manager), create(manager)]

        assert manager.cancel_all(remove_pending_jobs=False) == 2
        assert all(manager.get(i)["status"] == "cancelled" for i in ids)
        assert at_jobs.cancelled == []

    def test_record_run_counts_only_started_runs(self, manager):
        schedule_id = create(manager)

        manager.record_run(schedule_id, "started", "rec-1")
        manager.record_run(schedule_id, "skipped: previous run still active")

        schedule = manager.get(schedule_id)
        assert schedule["run_count"] == "1"
        assert schedule["last_session_name"] == "rec-1"
        assert schedule["last_result"] == "skipped: previous run still active"


class TestRunRecurringHook:
    """Run the hook in-process with ``at`` and tmux faked out."""

    @pytest.fixture
    def env(self, manager, at_jobs, monkeypatch):
        calls = SimpleNamespace(launched=[], active_sessions=set())

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["tmux", "has-session"]:
                return subprocess.CompletedProcess(cmd, 0 if cmd[3].lstrip("=") in calls.active_sessions else 1)
            calls.launched.append((cmd, kwargs.get("env", {})))
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(run_recurring.subprocess, "run", fake_run)
        monkeypatch.setattr("desto.redis.recurring.AtJobManager", lambda *a, **k: at_jobs)
        return calls

    def fire(self, schedule_id, occurrence=FIRST_RUN):
        return run_recurring.main([schedule_id, occurrence.strftime("%Y-%m-%dT%H:%M")])

    def test_launches_run_and_queues_next(self, manager, at_jobs, env):
        schedule_id = create(manager, session_name="backup")
        at_jobs.scheduled.clear()

        assert self.fire(schedule_id) == 0

        [(cmd, launch_env)] = env.launched
        assert cmd[-3:] == ["desto.hooks.start_scheduled_session", "backup-20300501-0630", "bash /s/backup.sh"]
        assert launch_env["DESTO_LOGS_DIR"] == "/logs"
        assert at_jobs.scheduled[0]["time_spec"] == "06:30 2030-05-02"
        schedule = manager.get(schedule_id)
        assert schedule["run_count"] == "1"
        assert schedule["last_session_name"] == "backup-20300501-0630"
        assert schedule["next_run"] == "2030-05-02T06:30"

    def test_fires_once_when_triggered_twice(self, manager, at_jobs, env):
        schedule_id = create(manager)
        at_jobs.scheduled.clear()

        self.fire(schedule_id)
        self.fire(schedule_id)

        assert len(env.launched) == 1
        assert len(at_jobs.scheduled) == 1

    def test_cancelled_schedule_does_nothing(self, manager, at_jobs, env):
        schedule_id = create(manager)
        manager.cancel(schedule_id)
        at_jobs.scheduled.clear()

        assert self.fire(schedule_id) == 0
        assert env.launched == []
        assert at_jobs.scheduled == []

    def test_skips_run_while_previous_is_active_but_keeps_series(self, manager, at_jobs, env):
        schedule_id = create(manager, session_name="backup")
        manager.record_run(schedule_id, "started", "backup-20300430-0630")
        env.active_sessions.add("backup-20300430-0630")
        at_jobs.scheduled.clear()

        assert self.fire(schedule_id) == 0
        assert env.launched == []
        assert len(at_jobs.scheduled) == 1
        assert manager.get(schedule_id)["last_result"] == "skipped: previous run still active"

    def test_rejects_bad_arguments(self):
        assert run_recurring.main([]) == 1
        assert run_recurring.main(["abc", "not-a-date"]) == 1
