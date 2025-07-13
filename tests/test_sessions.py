from unittest.mock import MagicMock, Mock, patch

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

    # Should initialize successfully but in limited mode when Redis is not available
    tmux_manager = TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)
    
    # Verify that it operates in limited mode
    assert tmux_manager.use_redis is False
    assert tmux_manager.desto_manager is None
    assert tmux_manager.pubsub is None
