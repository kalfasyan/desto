"""Tests for DestoService.schedule_launch: one-off 'at' jobs and recurring schedules."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from desto.core.scheduled_jobs import ScheduleError
from desto.core.service import DestoService

FIRST_RUN = (datetime.now() + timedelta(days=1)).replace(second=0, microsecond=0)


@pytest.fixture
def service(tmp_path):
    with (
        patch("desto.core.service.DestoRedisClient"),
        patch("desto.core.service.DestoManager"),
        patch("desto.core.service.SessionPubSub"),
    ):
        svc = DestoService(log_dir=tmp_path / "logs", scripts_dir=tmp_path, notifier=MagicMock())
    return svc


@pytest.fixture
def backends():
    with (
        patch("desto.core.scheduled_jobs.RecurringScheduleManager") as recurring,
        patch("desto.core.scheduled_jobs.AtJobManager") as at_manager,
        patch("desto.core.scheduled_jobs.shutil.which", return_value="/usr/bin/at"),
    ):
        recurring.return_value.create.return_value = "abc123"
        at_manager.return_value.schedule.return_value = "42"
        yield SimpleNamespace(recurring=recurring.return_value, at=at_manager.return_value)


def test_recurring_creates_schedule_without_precreating_session(service, backends, tmp_path):
    result = service.schedule_launch("backup", "bash backup.sh", [tmp_path / "backup.sh"], "", FIRST_RUN, 2 * 24 * 60)

    assert result == "abc123"
    kwargs = backends.recurring.create.call_args.kwargs
    assert kwargs["session_name"] == "backup"
    assert kwargs["interval_minutes"] == 2 * 24 * 60
    assert kwargs["first_run"] == FIRST_RUN
    assert kwargs["log_dir"] == str(tmp_path / "logs")
    assert kwargs["script_paths"] == [str(tmp_path / "backup.sh")]
    # Runs get their own sessions when they fire, so nothing is pre-created or queued directly
    service.desto_manager.start_session_with_job.assert_not_called()
    backends.at.schedule.assert_not_called()


def test_one_off_queues_at_job_and_records_scheduled_session(service, backends, tmp_path):
    result = service.schedule_launch("backup", "bash backup.sh", [tmp_path / "backup.sh"], "", FIRST_RUN)

    assert result == "42"
    backends.recurring.create.assert_not_called()
    assert service.desto_manager.start_session_with_job.call_args.kwargs["status"].value == "scheduled"
    kwargs = backends.at.schedule.call_args.kwargs
    assert "desto.hooks.start_scheduled_session" in kwargs["command"]
    assert kwargs["time_spec"] == FIRST_RUN.strftime("%H:%M %Y-%m-%d")
    service.notifier.assert_called_once()


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"session_name": ""}, "session name"),
        ({"when": datetime.now() - timedelta(minutes=5)}, "in the past"),
        ({"interval_minutes": 0}, "at least 1"),
    ],
)
def test_invalid_input_raises(service, backends, kwargs, message):
    args = {"session_name": "backup", "command": "true", "script_paths": ["x.sh"], "arguments": "", "when": FIRST_RUN, **kwargs}
    with pytest.raises(ScheduleError, match=message):
        service.schedule_launch(**args)
    backends.at.schedule.assert_not_called()


def test_missing_at_command_raises(service, backends):
    with patch("desto.core.scheduled_jobs.shutil.which", return_value=None):
        with pytest.raises(ScheduleError, match="'at' command is not available"):
            service.schedule_launch("backup", "true", ["x.sh"], "", FIRST_RUN)


def test_failed_first_recurring_run_raises(service, backends):
    backends.recurring.create.return_value = None
    with pytest.raises(ScheduleError, match="Failed to schedule the first run"):
        service.schedule_launch("backup", "true", ["x.sh"], "", FIRST_RUN, 30)
