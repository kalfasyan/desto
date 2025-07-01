"""Tests for CLI sessions commands."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Import only if typer is available, otherwise skip tests
try:
    from typer.testing import CliRunner

    from desto.cli.sessions import sessions_app

    TYPER_AVAILABLE = True
except ImportError:
    TYPER_AVAILABLE = False
    pytestmark = pytest.mark.skip("typer not available")


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        log_dir = temp_path / "logs"
        scripts_dir = temp_path / "scripts"
        log_dir.mkdir()
        scripts_dir.mkdir()
        yield {
            "log_dir": log_dir,
            "scripts_dir": scripts_dir,
            "temp_path": temp_path,
        }


@pytest.fixture
def mock_session_manager():
    """Create a mock session manager."""
    with patch("desto.cli.sessions.CLISessionManager") as mock_manager_class:
        mock_manager = Mock()
        mock_manager_class.return_value = mock_manager
        yield mock_manager


@pytest.mark.skipif(not TYPER_AVAILABLE, reason="typer not available")
class TestListCommand:
    """Test the sessions list command."""

    def test_list_no_sessions(self, runner, mock_session_manager):
        """Test listing when no sessions exist."""
        mock_session_manager.list_sessions.return_value = {}

        result = runner.invoke(sessions_app, ["list"])

        assert result.exit_code == 0
        assert "No active tmux sessions found" in result.stdout

    def test_list_with_sessions(self, runner, mock_session_manager):
        """Test listing with active sessions."""
        mock_sessions = {
            "session1": {
                "finished": False,
                "runtime": 3661,  # 1h 1m 1s
                "created": 1719835200.0,  # Mock timestamp
            },
            "session2": {
                "finished": True,
                "runtime": 120,  # 2m
                "created": 1719838800.0,  # Mock timestamp
            },
        }
        mock_session_manager.list_sessions.return_value = mock_sessions

        result = runner.invoke(sessions_app, ["list"])

        assert result.exit_code == 0
        assert "session1" in result.stdout
        assert "session2" in result.stdout
        assert "Running" in result.stdout
        assert "Finished" in result.stdout

    def test_list_verbose(self, runner, mock_session_manager):
        """Test listing with verbose flag."""
        mock_sessions = {
            "session1": {
                "finished": False,
                "runtime": 60,
                "created": 1719835200.0,
                "id": "1",
                "windows": 2,
                "attached": True,
            }
        }
        mock_session_manager.list_sessions.return_value = mock_sessions

        result = runner.invoke(sessions_app, ["list", "--verbose"])

        assert result.exit_code == 0
        assert "session1" in result.stdout


@pytest.mark.skipif(not TYPER_AVAILABLE, reason="typer not available")
class TestStartCommand:
    """Test the sessions start command."""

    def test_start_session_success(self, runner, mock_session_manager):
        """Test starting a session successfully."""
        mock_session_manager.session_exists.return_value = False
        mock_session_manager.start_session.return_value = True

        result = runner.invoke(sessions_app, ["start", "test_session", "echo hello"])

        assert result.exit_code == 0
        assert "started successfully" in result.stdout
        mock_session_manager.start_session.assert_called_with(
            "test_session", "echo hello", False
        )

    def test_start_session_with_keep_alive(self, runner, mock_session_manager):
        """Test starting a session with keep-alive flag."""
        mock_session_manager.session_exists.return_value = False
        mock_session_manager.start_session.return_value = True

        result = runner.invoke(
            sessions_app, ["start", "test_session", "echo hello", "--keep-alive"]
        )

        assert result.exit_code == 0
        mock_session_manager.start_session.assert_called_with(
            "test_session", "echo hello", True
        )

    def test_start_session_already_exists(self, runner, mock_session_manager):
        """Test starting a session that already exists."""
        mock_session_manager.session_exists.return_value = True

        result = runner.invoke(
            sessions_app, ["start", "existing_session", "echo hello"]
        )

        assert result.exit_code == 1
        assert "already exists" in result.stdout

    def test_start_session_failure(self, runner, mock_session_manager):
        """Test starting a session that fails."""
        mock_session_manager.session_exists.return_value = False
        mock_session_manager.start_session.return_value = False

        result = runner.invoke(sessions_app, ["start", "test_session", "echo hello"])

        assert result.exit_code == 1
        assert "Failed to start" in result.stdout

    def test_start_session_with_custom_dirs(
        self, runner, mock_session_manager, temp_dirs
    ):
        """Test starting a session with custom directories."""
        mock_session_manager.session_exists.return_value = False
        mock_session_manager.start_session.return_value = True

        result = runner.invoke(
            sessions_app,
            [
                "start",
                "test_session",
                "echo hello",
                "--logs-dir",
                str(temp_dirs["log_dir"]),
                "--scripts-dir",
                str(temp_dirs["scripts_dir"]),
            ],
        )

        assert result.exit_code == 0

    def test_start_session_exception(self, runner, mock_session_manager):
        """Test starting a session with exception."""
        mock_session_manager.session_exists.side_effect = Exception("Test error")

        result = runner.invoke(sessions_app, ["start", "test_session", "echo hello"])

        assert result.exit_code == 1
        assert "Error:" in result.stdout


@pytest.mark.skipif(not TYPER_AVAILABLE, reason="typer not available")
class TestKillCommand:
    """Test the sessions kill command."""

    def test_kill_specific_session(self, runner, mock_session_manager):
        """Test killing a specific session."""
        mock_session_manager.session_exists.return_value = True
        mock_session_manager.kill_session.return_value = True

        result = runner.invoke(sessions_app, ["kill", "test_session", "--force"])

        assert result.exit_code == 0
        assert "killed successfully" in result.stdout
        mock_session_manager.kill_session.assert_called_with("test_session")

    def test_kill_nonexistent_session(self, runner, mock_session_manager):
        """Test killing a session that doesn't exist."""
        mock_session_manager.session_exists.return_value = False

        result = runner.invoke(sessions_app, ["kill", "nonexistent", "--force"])

        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_kill_session_failure(self, runner, mock_session_manager):
        """Test killing a session that fails."""
        mock_session_manager.session_exists.return_value = True
        mock_session_manager.kill_session.return_value = False

        result = runner.invoke(sessions_app, ["kill", "test_session", "--force"])

        assert result.exit_code == 1
        assert "Failed to kill" in result.stdout

    def test_kill_no_arguments(self, runner, mock_session_manager):
        """Test kill command with no arguments."""
        result = runner.invoke(sessions_app, ["kill"])

        assert result.exit_code == 1
        assert "Must specify either a session name or --all flag" in result.stdout

    @patch("desto.cli.sessions.typer.confirm")
    def test_kill_with_confirmation(self, mock_confirm, runner, mock_session_manager):
        """Test kill command with confirmation prompt."""
        mock_confirm.return_value = True
        mock_session_manager.session_exists.return_value = True
        mock_session_manager.kill_session.return_value = True

        result = runner.invoke(sessions_app, ["kill", "test_session"])

        assert result.exit_code == 0
        mock_confirm.assert_called()

    @patch("desto.cli.sessions.typer.confirm")
    def test_kill_confirmation_denied(self, mock_confirm, runner, mock_session_manager):
        """Test kill command when confirmation is denied."""
        mock_confirm.return_value = False
        mock_session_manager.session_exists.return_value = True

        result = runner.invoke(sessions_app, ["kill", "test_session"])

        assert result.exit_code == 0
        assert "Operation cancelled" in result.stdout


@pytest.mark.skipif(not TYPER_AVAILABLE, reason="typer not available")
class TestAttachCommand:
    """Test the sessions attach command."""

    def test_attach_success(self, runner, mock_session_manager):
        """Test attaching to a session successfully."""
        mock_session_manager.session_exists.return_value = True
        mock_session_manager.attach_session.return_value = True

        result = runner.invoke(sessions_app, ["attach", "test_session"])

        assert result.exit_code == 0
        assert "Attaching to session" in result.stdout
        mock_session_manager.attach_session.assert_called_with("test_session")

    def test_attach_nonexistent_session(self, runner, mock_session_manager):
        """Test attaching to a non-existent session."""
        mock_session_manager.session_exists.return_value = False

        result = runner.invoke(sessions_app, ["attach", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_attach_failure(self, runner, mock_session_manager):
        """Test attaching to a session that fails."""
        mock_session_manager.session_exists.return_value = True
        mock_session_manager.attach_session.return_value = False

        result = runner.invoke(sessions_app, ["attach", "test_session"])

        assert result.exit_code == 1
        assert "Failed to attach" in result.stdout


@pytest.mark.skipif(not TYPER_AVAILABLE, reason="typer not available")
class TestLogsCommand:
    """Test the sessions logs command."""

    def test_view_logs_success(self, runner, mock_session_manager):
        """Test viewing logs successfully."""
        mock_session_manager.get_log_file.return_value = Path("/tmp/test.log")
        mock_session_manager.get_log_content.return_value = "Log content here"

        with patch("pathlib.Path.exists", return_value=True):
            result = runner.invoke(sessions_app, ["logs", "test_session"])

        assert result.exit_code == 0
        assert "Log content here" in result.stdout

    def test_view_logs_file_not_exists(self, runner, mock_session_manager):
        """Test viewing logs when file doesn't exist."""
        mock_log_file = Mock()
        mock_log_file.exists.return_value = False
        mock_session_manager.get_log_file.return_value = mock_log_file

        result = runner.invoke(sessions_app, ["logs", "test_session"])

        assert result.exit_code == 1
        assert "No log file found" in result.stdout

    def test_view_logs_with_lines(self, runner, mock_session_manager):
        """Test viewing logs with line limit."""
        mock_session_manager.get_log_file.return_value = Path("/tmp/test.log")
        mock_session_manager.get_log_content.return_value = "Last 5 lines"

        with patch("pathlib.Path.exists", return_value=True):
            result = runner.invoke(
                sessions_app, ["logs", "test_session", "--lines", "5"]
            )

        assert result.exit_code == 0
        mock_session_manager.get_log_content.assert_called_with("test_session", 5)

    def test_follow_logs(self, runner, mock_session_manager):
        """Test following logs."""
        mock_log_file = Mock()
        mock_log_file.exists.return_value = True
        mock_session_manager.get_log_file.return_value = mock_log_file
        mock_session_manager.follow_log.return_value = True

        result = runner.invoke(sessions_app, ["logs", "test_session", "--follow"])

        assert result.exit_code == 0
        mock_session_manager.follow_log.assert_called_with("test_session")

    def test_follow_logs_failure(self, runner, mock_session_manager):
        """Test following logs when it fails."""
        mock_log_file = Mock()
        mock_log_file.exists.return_value = True
        mock_session_manager.get_log_file.return_value = mock_log_file
        mock_session_manager.follow_log.return_value = False

        result = runner.invoke(sessions_app, ["logs", "test_session", "--follow"])

        assert result.exit_code == 1
        assert "Failed to follow logs" in result.stdout
