"""Tests for the repeat option in the dashboard's schedule dialog."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from desto.app.ui import UserInterfaceManager


@pytest.fixture
def ui_manager(tmp_path):
    (tmp_path / "backup.sh").write_text("echo hi\n")
    mock_tmux = MagicMock()
    mock_tmux.SCRIPTS_DIR = tmp_path
    mock_tmux.LOG_DIR = tmp_path / "logs"
    manager = UserInterfaceManager(MagicMock(), {}, mock_tmux)
    manager.session_name_input = SimpleNamespace(value="backup")
    manager.arguments_input = SimpleNamespace(value="")
    manager.script_path_select = SimpleNamespace(value="backup.sh")
    manager.chain_queue_display = MagicMock()
    return manager


@pytest.fixture
def backends():
    with (
        patch("desto.app.ui.RecurringScheduleManager") as recurring,
        patch("desto.app.ui.AtJobManager") as at_manager,
        patch("desto.redis.client.DestoRedisClient") as redis_client,
        patch("desto.redis.desto_manager.DestoManager") as desto_manager,
        patch("desto.app.ui.ui"),
        patch("shutil.which", return_value="/usr/bin/at"),
    ):
        redis_client.return_value.is_connected.return_value = True
        recurring.return_value.create.return_value = "abc123"
        at_manager.return_value.schedule.return_value = "42"
        yield SimpleNamespace(recurring=recurring.return_value, at=at_manager.return_value, desto=desto_manager.return_value)


FIRST_RUN = (datetime.now() + timedelta(days=1)).replace(second=0, microsecond=0)


def schedule(ui_manager, unit, count=1):
    error_label, dialog = SimpleNamespace(text=""), MagicMock()
    ui_manager.confirm_schedule(
        SimpleNamespace(value=FIRST_RUN.strftime("%Y-%m-%d")),
        SimpleNamespace(value=FIRST_RUN.strftime("%H:%M")),
        error_label,
        dialog,
        SimpleNamespace(value=unit),
        SimpleNamespace(value=count),
    )
    return error_label, dialog


def test_repeat_creates_recurring_schedule(ui_manager, backends, tmp_path):
    error_label, dialog = schedule(ui_manager, "days", 2)

    assert error_label.text == ""
    kwargs = backends.recurring.create.call_args.kwargs
    assert kwargs["session_name"] == "backup"
    assert kwargs["interval_minutes"] == 2 * 24 * 60
    assert kwargs["first_run"] == FIRST_RUN
    assert kwargs["log_dir"] == str(tmp_path / "logs")
    assert str(tmp_path / "backup.sh") in kwargs["command"]
    # Runs get their own sessions when they fire, so nothing is pre-created or queued directly
    backends.desto.start_session_with_job.assert_not_called()
    backends.at.schedule.assert_not_called()
    dialog.close.assert_called_once()


def test_no_repeat_keeps_one_off_scheduling(ui_manager, backends):
    error_label, dialog = schedule(ui_manager, "never")

    assert error_label.text == ""
    backends.recurring.create.assert_not_called()
    backends.desto.start_session_with_job.assert_called_once()
    assert "desto.hooks.start_scheduled_session" in backends.at.schedule.call_args.kwargs["command"]
    dialog.close.assert_called_once()


def test_repeat_count_must_be_positive(ui_manager, backends):
    error_label, dialog = schedule(ui_manager, "hours", 0)

    assert "at least 1" in error_label.text
    backends.recurring.create.assert_not_called()
    dialog.close.assert_not_called()


def test_recurring_chain_runs_all_scripts_and_clears_queue(ui_manager, backends, tmp_path):
    (tmp_path / "report.py").write_text("print('hi')\n")
    ui_manager.chain_queue = [(tmp_path / "backup.sh", ""), (tmp_path / "report.py", "")]

    schedule(ui_manager, "weeks")

    kwargs = backends.recurring.create.call_args.kwargs
    assert kwargs["interval_minutes"] == 7 * 24 * 60
    assert " && " in kwargs["command"]
    assert kwargs["script_paths"] == [str(tmp_path / "backup.sh"), str(tmp_path / "report.py")]
    assert ui_manager.chain_queue == []


def test_failed_first_run_reports_error(ui_manager, backends):
    backends.recurring.create.return_value = None

    error_label, dialog = schedule(ui_manager, "minutes", 30)

    assert error_label.text == "Failed to schedule the first run with 'at'."
    dialog.close.assert_not_called()
