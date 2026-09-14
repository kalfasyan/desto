import os
from pathlib import Path
from unittest.mock import MagicMock, call, mock_open, patch

import pytest

from desto.app.sessions import TmuxManager

pytestmark = pytest.mark.skipif(os.getenv("CI") == "true", reason="Redis is not available on GitHub Actions")


@patch("desto.app.sessions.ui")
def test_init_log_dir_creation_error(mock_ui):
    mock_logger = MagicMock()
    with patch.object(Path, "mkdir", side_effect=OSError("fail")):
        with pytest.raises(OSError):
            TmuxManager(mock_ui, mock_logger, log_dir="/bad/dir", scripts_dir="/bad/dir")


@patch("desto.app.sessions.subprocess")
def test_start_tmux_session_logfile_append(mock_subprocess, tmp_path):
    mock_logger = MagicMock()
    mock_ui = MagicMock()
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    log_file = tmux.get_log_file("mysess")
    log_file.write_text("existing log")
    with patch("builtins.open", mock_open()):
        tmux.start_tmux_session("mysess", "echo hi", mock_logger)
    assert log_file.exists()


@patch("desto.app.sessions.subprocess")
def test_view_log_missing_file(mock_subprocess, tmp_path):
    mock_logger = MagicMock()
    mock_ui = MagicMock()
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    # Should not raise
    tmux.view_log("notfound", mock_ui)
    mock_ui.log.assert_called_once()
    mock_ui.timer.assert_called_once()
    mock_ui.dialog.assert_called_once()


@patch("desto.app.sessions.subprocess")
def test_view_log_existing_file_builds_dialog(mock_subprocess, tmp_path):
    mock_logger = MagicMock()
    mock_ui = MagicMock()
    mock_subprocess.run.return_value.returncode = 0
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    log_file = tmux.get_log_file("mysess")
    log_file.write_text("hello\nworld\n")

    # Should not raise and should build the live viewer controls
    tmux.view_log("mysess", mock_ui)

    mock_ui.log.assert_called_once()
    mock_ui.timer.assert_called_once()
    mock_ui.badge.assert_called_once()
    mock_ui.switch.assert_called_once()
    mock_ui.dialog.assert_called_once()


@patch("desto.app.sessions.subprocess")
def test_view_log_follows_and_stops_when_session_ends(mock_subprocess, tmp_path):
    mock_logger = MagicMock()
    mock_ui = MagicMock()
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    tmux.resume_updates = MagicMock()
    mock_subprocess.run.return_value.returncode = 0  # Session is active

    log_file = tmux.get_log_file("mysess")
    log_file.write_text("initial\n")
    tmux.view_log("mysess", mock_ui)

    tick = mock_ui.timer.call_args.args[1]
    timer = mock_ui.timer.return_value
    log_element = mock_ui.log.return_value.style.return_value.classes.return_value
    badge = mock_ui.badge.return_value
    auto_refresh = mock_ui.switch.return_value

    assert log_element.push.call_args_list == [call("initial")]

    with log_file.open("a") as f:
        f.write("live line\n")
    tick()
    assert log_element.push.call_args_list[-1] == call("live line")
    assert not timer.cancel.called

    # Auto-refresh off: the timer stops pushing lines
    auto_refresh.value = False
    with log_file.open("a") as f:
        f.write("ignored line\n")
    tick()
    assert log_element.push.call_args_list[-1] == call("live line")
    auto_refresh.value = True

    # Session ends: final read, badge flips, timer cancelled
    mock_subprocess.run.return_value.returncode = 1
    with log_file.open("a") as f:
        f.write("last line\n")
    tick()
    assert log_element.push.call_args_list[-1] == call("last line")
    assert timer.cancel.called
    assert badge.props.call_args_list[-1] == call("color=grey")

    # Closing resumes global updates exactly once and closes the dialog
    dialog = mock_ui.dialog.return_value.__enter__.return_value
    value_change = dialog.on_value_change.call_args.args[0]
    value_change(MagicMock(value=True))  # Opening the dialog must not resume updates
    tmux.resume_updates.assert_not_called()
    close = next(call.kwargs["on_click"] for call in mock_ui.button.call_args_list if call.args == ("Close",))
    close()
    tmux.resume_updates.assert_called_once()
    dialog.close.assert_called_once()
    hide = dialog.on.call_args.args[1]
    hide()
    value_change(MagicMock(value=False))
    tmux.resume_updates.assert_called_once()
    dialog.close.assert_called_once()


@patch("desto.app.sessions.subprocess")
def test_view_log_poll_error_cancels_timer(mock_subprocess, tmp_path):
    mock_logger = MagicMock()
    mock_ui = MagicMock()
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    mock_subprocess.run.return_value.returncode = 0

    log_file = tmux.get_log_file("mysess")
    log_file.write_text("initial\n")
    tmux.view_log("mysess", mock_ui)

    tick = mock_ui.timer.call_args.args[1]
    timer = mock_ui.timer.return_value
    log_element = mock_ui.log.return_value.style.return_value.classes.return_value
    pushes = {"count": 0}

    def flaky_push(line):
        pushes["count"] += 1
        if pushes["count"] == 1:  # The initial push happened before the failure was armed
            raise RuntimeError("boom")

    log_element.push.side_effect = flaky_push

    with log_file.open("a") as f:
        f.write("live line\n")
    tick()  # Must not raise

    assert timer.cancel.called
    assert str(log_element.push.call_args_list[-1].args[0]).startswith("[desto] log follow error: boom")


@patch("desto.app.sessions.subprocess")
def test_view_log_download_guard(mock_subprocess, tmp_path):
    mock_logger = MagicMock()
    mock_ui = MagicMock()
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    mock_subprocess.run.return_value.returncode = 0

    log_file = tmux.get_log_file("mysess")
    log_file.write_text("content\n")
    tmux.view_log("mysess", mock_ui)

    download = next(call.kwargs["on_click"] for call in mock_ui.button.call_args_list if call.args == ("Download log",))
    download()
    mock_ui.download.file.assert_called_once_with(log_file, filename="mysess.log", media_type="text/plain")

    mock_ui.download.file.reset_mock()
    log_file.unlink()
    download()
    assert not mock_ui.download.file.called
    assert mock_ui.notification.called


def test_get_log_and_script_file(tmp_path):
    mock_logger = MagicMock()
    mock_ui = MagicMock()
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    assert tmux.get_log_file("abc").name == "abc.log"
    assert tmux.get_script_file("myscript.sh").name == "myscript.sh"


@patch("desto.app.sessions.subprocess")
def test_kill_session_failure(mock_subprocess, tmp_path):
    mock_logger = MagicMock()
    mock_ui = MagicMock()
    result = MagicMock()
    result.returncode = 1
    result.stderr = "fail"
    mock_subprocess.run.return_value = result
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    tmux.sessions["test"] = "echo hello"
    tmux.kill_session("test")
    msg = "Failed to kill session 'test': fail"
    mock_logger.warning.assert_called_with(msg)
    mock_ui.notification.assert_called_with(msg, type="negative")
    # The session should still be present since kill failed
    assert "test" in tmux.sessions
