"""Tests for the dashboard's schedule dialog: it turns the form into one schedule_launch call."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from desto.app.ui import UserInterfaceManager
from desto.core.scheduled_jobs import ScheduleError


@pytest.fixture
def ui_manager(tmp_path):
    (tmp_path / "backup.sh").write_text("echo hi\n")
    mock_tmux = MagicMock()
    mock_tmux.SCRIPTS_DIR = tmp_path
    manager = UserInterfaceManager(MagicMock(), {}, mock_tmux)
    manager.session_name_input = SimpleNamespace(value="backup")
    manager.arguments_input = SimpleNamespace(value="")
    manager.script_path_select = SimpleNamespace(value="backup.sh")
    manager.chain_queue_display = MagicMock()
    return manager


FIRST_RUN = (datetime.now() + timedelta(days=1)).replace(second=0, microsecond=0)


def schedule(ui_manager, unit, count=1):
    error_label, dialog = SimpleNamespace(text=""), MagicMock()
    ui_manager.schedule_dialog.confirm(
        SimpleNamespace(value=FIRST_RUN.strftime("%Y-%m-%d")),
        SimpleNamespace(value=FIRST_RUN.strftime("%H:%M")),
        error_label,
        dialog,
        SimpleNamespace(value=unit),
        SimpleNamespace(value=count),
    )
    return error_label, dialog


def test_repeat_passes_interval_to_service(ui_manager, tmp_path):
    error_label, dialog = schedule(ui_manager, "days", 2)

    assert error_label.text == ""
    name, command, script_paths, arguments, when, interval = ui_manager.tmux_manager.schedule_launch.call_args.args
    assert (name, when, interval) == ("backup", FIRST_RUN, 2 * 24 * 60)
    assert str(tmp_path / "backup.sh") in command
    assert script_paths == [tmp_path / "backup.sh"]
    dialog.close.assert_called_once()


def test_no_repeat_schedules_once(ui_manager):
    schedule(ui_manager, "never")

    assert ui_manager.tmux_manager.schedule_launch.call_args.args[5] is None


def test_service_errors_are_shown_and_keep_dialog_open(ui_manager):
    ui_manager.tmux_manager.schedule_launch.side_effect = ScheduleError("Repeat interval must be at least 1.")

    error_label, dialog = schedule(ui_manager, "hours", 0)

    assert error_label.text == "Repeat interval must be at least 1."
    dialog.close.assert_not_called()


def test_chain_schedules_all_scripts_and_clears_queue(ui_manager, tmp_path):
    (tmp_path / "report.py").write_text("print('hi')\n")
    ui_manager.chain_queue = [(str(tmp_path / "backup.sh"), ""), (str(tmp_path / "report.py"), "")]

    schedule(ui_manager, "weeks")

    _, command, script_paths, _, _, interval = ui_manager.tmux_manager.schedule_launch.call_args.args
    assert interval == 7 * 24 * 60
    assert " && " in command
    assert script_paths == [str(tmp_path / "backup.sh"), str(tmp_path / "report.py")]
    assert ui_manager.chain_queue == []
