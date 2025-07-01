"""Tests for the main CLI application."""

from unittest.mock import Mock, patch

import pytest

# Import only if typer is available, otherwise skip tests
try:
    from typer.testing import CliRunner

    from desto.cli.main import app

    TYPER_AVAILABLE = True
except ImportError:
    TYPER_AVAILABLE = False
    pytestmark = pytest.mark.skip("typer not available")


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.mark.skipif(not TYPER_AVAILABLE, reason="typer not available")
class TestMainApp:
    """Test the main CLI application."""

    def test_version_command(self, runner):
        """Test the version command."""
        result = runner.invoke(app, ["version"])

        assert result.exit_code == 0
        assert "desto-cli" in result.stdout
        assert "version" in result.stdout

    def test_help_command(self, runner):
        """Test the help command."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "desto-cli" in result.stdout
        assert "Manage tmux sessions" in result.stdout

    def test_verbose_flag(self, runner):
        """Test the verbose flag."""
        result = runner.invoke(app, ["--verbose", "version"])

        assert result.exit_code == 0

    def test_log_file_option(self, runner):
        """Test the log file option."""
        with patch("desto.cli.main.setup_logging") as mock_setup:
            result = runner.invoke(app, ["--log-file", "/tmp/test.log", "version"])

            assert result.exit_code == 0
            mock_setup.assert_called_with(level="INFO", log_file="/tmp/test.log")


@pytest.mark.skipif(not TYPER_AVAILABLE, reason="typer not available")
class TestDoctorCommand:
    """Test the doctor command for system checks."""

    @patch("desto.cli.main.shutil.which")
    @patch("desto.cli.main.subprocess.run")
    def test_doctor_tmux_available(self, mock_subprocess, mock_which, runner):
        """Test doctor command when tmux is available."""
        mock_which.return_value = "/usr/bin/tmux"
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "tmux 3.2a"
        mock_subprocess.return_value = mock_result

        with patch("desto.cli.main.CLISessionManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.scripts_dir.exists.return_value = True
            mock_manager.log_dir.exists.return_value = True
            mock_manager.scripts_dir.glob.return_value = ["script1.sh", "script2.py"]
            mock_manager.log_dir.glob.return_value = ["session1.log"]
            mock_manager.list_sessions.return_value = {}
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "tmux: tmux 3.2a" in result.stdout

    @patch("desto.cli.main.shutil.which")
    def test_doctor_tmux_not_available(self, mock_which, runner):
        """Test doctor command when tmux is not available."""
        mock_which.return_value = None

        with patch("desto.cli.main.CLISessionManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.scripts_dir.exists.return_value = False
            mock_manager.log_dir.exists.return_value = False
            mock_manager.list_sessions.return_value = {}
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "tmux: not found" in result.stdout

    @patch("desto.cli.main.shutil.which")
    @patch("desto.cli.main.subprocess.run")
    def test_doctor_tmux_version_check_fails(self, mock_subprocess, mock_which, runner):
        """Test doctor command when tmux version check fails."""
        mock_which.return_value = "/usr/bin/tmux"
        mock_subprocess.side_effect = Exception("Command failed")

        with patch("desto.cli.main.CLISessionManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.scripts_dir.exists.return_value = True
            mock_manager.log_dir.exists.return_value = True
            mock_manager.scripts_dir.glob.return_value = []
            mock_manager.log_dir.glob.return_value = []
            mock_manager.list_sessions.return_value = {}
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "version check failed" in result.stdout

    def test_doctor_with_active_sessions(self, runner):
        """Test doctor command with active sessions."""
        with patch("desto.cli.main.shutil.which", return_value="/usr/bin/tmux"):
            with patch("desto.cli.main.subprocess.run") as mock_subprocess:
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = "tmux 3.2a"
                mock_subprocess.return_value = mock_result

                with patch("desto.cli.main.CLISessionManager") as mock_manager_class:
                    mock_manager = Mock()
                    mock_manager.scripts_dir.exists.return_value = True
                    mock_manager.log_dir.exists.return_value = True
                    mock_manager.scripts_dir.glob.return_value = ["script1.sh"]
                    mock_manager.log_dir.glob.return_value = ["session1.log"]
                    mock_manager.list_sessions.return_value = {
                        "session1": {"finished": False},
                        "session2": {"finished": True},
                    }
                    mock_manager_class.return_value = mock_manager

                    result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "Found 2 active tmux session" in result.stdout
        assert "session1 (running)" in result.stdout
        assert "session2 (finished)" in result.stdout

    def test_doctor_python_version(self, runner):
        """Test doctor command shows Python version."""
        with patch("desto.cli.main.shutil.which", return_value=None):
            with patch("desto.cli.main.CLISessionManager") as mock_manager_class:
                mock_manager = Mock()
                mock_manager.scripts_dir.exists.return_value = True
                mock_manager.log_dir.exists.return_value = True
                mock_manager.scripts_dir.glob.return_value = []
                mock_manager.log_dir.glob.return_value = []
                mock_manager.list_sessions.return_value = {}
                mock_manager_class.return_value = mock_manager

                result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "Python:" in result.stdout

    def test_doctor_directory_status(self, runner):
        """Test doctor command shows directory status."""
        with patch("desto.cli.main.shutil.which", return_value=None):
            with patch("desto.cli.main.CLISessionManager") as mock_manager_class:
                mock_manager = Mock()
                mock_manager.scripts_dir.exists.return_value = False
                mock_manager.log_dir.exists.return_value = False
                mock_manager.list_sessions.return_value = {}
                mock_manager_class.return_value = mock_manager

                result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "Scripts directory does not exist" in result.stdout
        assert "Logs directory does not exist" in result.stdout


@pytest.mark.skipif(not TYPER_AVAILABLE, reason="typer not available")
class TestMainCallback:
    """Test the main callback function."""

    def test_main_callback_default(self, runner):
        """Test main callback with default options."""
        with patch("desto.cli.main.setup_logging") as mock_setup:
            result = runner.invoke(app, ["version"])

            assert result.exit_code == 0
            mock_setup.assert_called_with(level="INFO", log_file=None)

    def test_main_callback_verbose(self, runner):
        """Test main callback with verbose option."""
        with patch("desto.cli.main.setup_logging") as mock_setup:
            result = runner.invoke(app, ["--verbose", "version"])

            assert result.exit_code == 0
            mock_setup.assert_called_with(level="DEBUG", log_file=None)

    def test_main_callback_with_log_file(self, runner):
        """Test main callback with log file option."""
        with patch("desto.cli.main.setup_logging") as mock_setup:
            result = runner.invoke(app, ["--log-file", "/tmp/test.log", "version"])

            assert result.exit_code == 0
            mock_setup.assert_called_with(level="INFO", log_file="/tmp/test.log")


@pytest.mark.skipif(not TYPER_AVAILABLE, reason="typer not available")
class TestCommandIntegration:
    """Test integration between commands."""

    def test_sessions_command_group_available(self, runner):
        """Test that sessions command group is available."""
        result = runner.invoke(app, ["sessions", "--help"])

        assert result.exit_code == 0
        assert "Manage tmux sessions" in result.stdout

    def test_sessions_list_integration(self, runner):
        """Test integration with sessions list command."""
        with patch("desto.cli.sessions.CLISessionManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.list_sessions.return_value = {}
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(app, ["sessions", "list"])

        assert result.exit_code == 0
        assert "No active tmux sessions found" in result.stdout
