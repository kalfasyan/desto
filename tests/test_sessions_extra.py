from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from desto.app.sessions import TmuxManager


@patch("desto.app.sessions.ui")
def test_init_log_dir_creation_error(mock_ui):
    mock_logger = MagicMock()
    with patch.object(Path, "mkdir", side_effect=OSError("fail")):
        with pytest.raises(OSError):
            TmuxManager(
                mock_ui, mock_logger, log_dir="/bad/dir", scripts_dir="/bad/dir"
            )


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
