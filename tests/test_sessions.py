import os
from unittest.mock import MagicMock, Mock, patch

import pytest

from desto.app.sessions import TmuxManager

pytestmark = pytest.mark.skipif(os.getenv("CI") == "true", reason="Redis is not available on GitHub Actions")


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
@patch("desto.app.sessions.DestoRedisClient")
def test_start_tmux_session_creates_tmux_session(mock_redis_class, mock_subprocess, mock_ui, mock_logger, tmp_path):
    # Mock Redis to be available
    mock_redis_instance = Mock()
    mock_redis_instance.is_connected.return_value = True

    # Mock the redis.redis object and its methods
    mock_redis_redis = Mock()
    mock_redis_redis.scan_iter.return_value = []  # No existing keys
    mock_redis_redis.hset.return_value = True
    mock_redis_redis.expire.return_value = True
    mock_redis_redis.hgetall.return_value = {}
    mock_redis_redis.publish.return_value = True

    mock_redis_instance.redis = mock_redis_redis
    mock_redis_class.return_value = mock_redis_instance

    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.CalledProcessError = Exception  # Mock the exception

    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    tmux.start_tmux_session("test", "echo hello", mock_logger)

    # Should call tmux new-session with bash -c and a complex command
    mock_subprocess.run.assert_called()
    call_args = mock_subprocess.run.call_args[0][0]
    assert call_args[:4] == ["tmux", "new-session", "-d", "-s"]
    assert call_args[4] == "test"


@patch("desto.app.sessions.subprocess")
@patch("desto.app.sessions.DestoRedisClient")
def test_kill_session_calls_tmux_kill(mock_redis_class, mock_subprocess, mock_ui, mock_logger, tmp_path):
    # Mock Redis to be available
    mock_redis_instance = Mock()
    mock_redis_instance.is_connected.return_value = True

    # Mock the redis.redis object and its methods
    mock_redis_redis = Mock()
    mock_redis_redis.scan_iter.return_value = []
    mock_redis_redis.hset.return_value = True
    mock_redis_redis.expire.return_value = True
    mock_redis_redis.hgetall.return_value = {}
    mock_redis_redis.publish.return_value = True

    mock_redis_instance.redis = mock_redis_redis
    mock_redis_class.return_value = mock_redis_instance

    mock_subprocess.run.return_value.returncode = 0
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    tmux.kill_session("test")
    mock_subprocess.run.assert_called_with(
        ["tmux", "kill-session", "-t", "test"],
        stdout=mock_subprocess.PIPE,
        stderr=mock_subprocess.PIPE,
        text=True,
    )


@patch("desto.app.sessions.subprocess")
@patch("desto.app.sessions.DestoRedisClient")
def test_check_sessions_returns_dict(mock_redis_class, mock_subprocess, mock_ui, mock_logger, tmp_path):
    # Mock Redis to be available
    mock_redis_instance = Mock()
    mock_redis_instance.is_connected.return_value = True

    # Mock the redis.redis object and its methods
    mock_redis_redis = Mock()
    mock_redis_redis.scan_iter.return_value = []
    mock_redis_redis.hset.return_value = True
    mock_redis_redis.expire.return_value = True
    mock_redis_redis.hgetall.return_value = {}
    mock_redis_redis.publish.return_value = True

    mock_redis_instance.redis = mock_redis_redis
    mock_redis_class.return_value = mock_redis_instance

    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = "1:test:1234567890:1:1::\n"
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    sessions = tmux.check_sessions()
    assert "test" in sessions
    assert sessions["test"]["id"] == "1"


@patch("desto.app.sessions.DestoRedisClient")
def test_redis_required_for_initialization(mock_redis_class, mock_ui, mock_logger, tmp_path):
    # Mock Redis to be unavailable
    mock_redis_instance = Mock()
    mock_redis_instance.is_connected.return_value = False

    # Mock the redis.redis object
    mock_redis_redis = Mock()
    mock_redis_instance.redis = mock_redis_redis
    mock_redis_class.return_value = mock_redis_instance

    # Should raise RuntimeError when Redis is not available
    with pytest.raises(RuntimeError):
        TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)


@patch("desto.app.sessions.subprocess")
@patch("desto.app.sessions.DestoRedisClient")
def test_is_tmux_session_active_true_false(mock_redis_class, mock_subprocess, mock_ui, mock_logger, tmp_path):
    # Mock Redis to be available
    mock_redis_instance = Mock()
    mock_redis_instance.is_connected.return_value = True
    mock_redis_instance.redis = Mock()
    mock_redis_class.return_value = mock_redis_instance

    # Simulate tmux session exists
    mock_subprocess.run.return_value.returncode = 0
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    assert tmux.is_tmux_session_active("test") is True

    # Simulate tmux session does not exist
    mock_subprocess.run.return_value.returncode = 1
    assert tmux.is_tmux_session_active("test") is False


@patch("desto.app.sessions.subprocess")
@patch("desto.app.sessions.DestoRedisClient")
def test_get_all_sessions_status_includes_tmux_and_redis(mock_redis_class, mock_subprocess, mock_ui, mock_logger, tmp_path):
    # Mock Redis to be available
    mock_redis_instance = Mock()
    mock_redis_instance.is_connected.return_value = True
    mock_redis_instance.redis = Mock()
    # Simulate Redis returns one session
    mock_redis_instance.redis.scan_iter.return_value = ["desto:session:1"]
    mock_redis_instance.redis.hgetall.return_value = {"session_name": "redis_session", "id": "1"}
    mock_redis_class.return_value = mock_redis_instance

    # Simulate tmux returns one session
    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = "2:tmux_session:1234567890:1:1::\n"
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    all_sessions = tmux.get_all_sessions_status()
    assert "redis_session" in all_sessions
    assert "tmux_session" in all_sessions


@patch("desto.app.sessions.DestoRedisClient")
def test_session_heartbeat_and_finish(mock_redis_class, mock_ui, mock_logger, tmp_path):
    from desto.redis.session_manager import DestoSession, SessionManager, SessionStatus

    # Mock Redis
    mock_redis_instance = Mock()
    mock_redis_instance.is_connected.return_value = True
    mock_redis_instance.redis = Mock()
    # Patch hgetall to return a real dict
    session_id = "test-id"
    session_dict = {
        "session_id": session_id,
        "session_name": "test",
        "tmux_session_name": "test",
        "status": SessionStatus.RUNNING.value,
        "start_time": "2025-07-21T14:00:00",
        "last_heartbeat": "2025-07-21T14:00:00",
    }
    mock_redis_instance.redis.hgetall.return_value = session_dict
    mock_redis_class.return_value = mock_redis_instance
    manager = SessionManager(mock_redis_instance)
    # Create session
    session = DestoSession(session_name="test", tmux_session_name="test", status=SessionStatus.RUNNING)
    session.session_id = session_id
    manager._update_session(session)
    # Update heartbeat
    assert manager.update_heartbeat(session.session_id) is True
    # Finish session
    assert manager.finish_session(session.session_id) is True
    # Fail session
    assert manager.fail_session(session.session_id, "error") is True


@patch("desto.app.sessions.DestoRedisClient")
def test_clear_sessions_container_calls_ui_clear(mock_redis_class, mock_ui, mock_logger, tmp_path):
    mock_redis_instance = Mock()
    mock_redis_instance.is_connected.return_value = True
    mock_redis_instance.redis = Mock()
    mock_redis_class.return_value = mock_redis_instance
    # Patch sessions_container directly
    tmux = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    tmux.sessions_container = Mock()
    tmux.sessions_container.clear = Mock()
    tmux.clear_sessions_container()
    tmux.sessions_container.clear.assert_called()
