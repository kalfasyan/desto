from unittest.mock import MagicMock, patch

import pytest

from desto.app.sessions import TmuxManager


@pytest.fixture
def mock_ui():
    return MagicMock()


@pytest.fixture
def mock_logger():
    logger = MagicMock()
    logger.error = MagicMock()
    logger.info = MagicMock()
    logger.success = MagicMock()
    logger.warning = MagicMock()
    return logger


@patch("desto.app.sessions.subprocess")
def test_start_session_creates_tmux_session(
    mock_subprocess, mock_ui, mock_logger, tmp_path
):
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    tmux.start_session("test", "echo hello")
    mock_subprocess.run.assert_called_with(
        ["tmux", "new-session", "-d", "-s", "test", "echo hello"]
    )
    assert "test" in tmux.sessions


@patch("desto.app.sessions.subprocess")
def test_kill_session_removes_from_sessions(
    mock_subprocess, mock_ui, mock_logger, tmp_path
):
    mock_subprocess.run.return_value.returncode = 0
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    tmux.sessions["test"] = "echo hello"
    tmux.kill_session("test")
    assert "test" not in tmux.sessions


@patch("desto.app.sessions.subprocess")
def test_check_sessions_returns_dict(mock_subprocess, mock_ui, mock_logger, tmp_path):
    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = "1:test:1234567890:1:1::\n"
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    sessions = tmux.check_sessions()
    assert "test" in sessions
    assert sessions["test"]["id"] == "1"
