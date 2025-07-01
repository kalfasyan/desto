"""Integration tests for the CLI module."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestCLIIntegration:
    """Integration tests for CLI components working together."""

    @pytest.fixture
    def temp_dirs(self):
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

    def test_session_lifecycle_integration(self, temp_dirs):
        """Test complete session lifecycle through CLI components."""
        from desto.cli.session_manager import CLISessionManager

        manager = CLISessionManager(
            log_dir=temp_dirs["log_dir"], scripts_dir=temp_dirs["scripts_dir"]
        )

        # Mock subprocess for tmux operations
        with patch("desto.cli.session_manager.subprocess.run") as mock_run:
            # Mock successful session start
            mock_run.return_value = Mock(returncode=0)

            # Start a session
            result = manager.start_session("integration_test", "echo 'hello world'")
            assert result is True

            # Mock session listing
            mock_run.return_value = Mock(
                stdout="integration_test: 1 windows (created Tue Jul  1 10:00:00 2025)",
                returncode=0,
            )

            # List sessions
            sessions = manager.list_sessions()
            assert "integration_test" in sessions

            # Mock successful session kill
            mock_run.return_value = Mock(returncode=0)

            # Kill the session
            result = manager.kill_session("integration_test")
            assert result is True

    def test_log_management_integration(self, temp_dirs):
        """Test log management integration."""
        from desto.cli.session_manager import CLISessionManager

        manager = CLISessionManager(
            log_dir=temp_dirs["log_dir"], scripts_dir=temp_dirs["scripts_dir"]
        )

        # Create a log file
        log_file = temp_dirs["log_dir"] / "test_session.log"
        log_content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
        log_file.write_text(log_content)

        # Test getting full log content
        content = manager.get_log_content("test_session")
        assert content == log_content

        # Test getting limited lines with subprocess mock
        with patch("desto.cli.session_manager.subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="Line 4\nLine 5\n", returncode=0)
            content = manager.get_log_content("test_session", lines=2)
            mock_run.assert_called_with(
                ["tail", "-n", "2", str(log_file)],
                capture_output=True,
                text=True,
                check=True,
            )

    def test_utility_functions_integration(self):
        """Test utility functions working together."""
        from datetime import datetime

        from desto.cli.utils import (
            format_duration,
            format_timestamp,
            validate_session_name,
        )

        # Test duration formatting for realistic values
        assert format_duration(0) == "0s"
        assert format_duration(3661) == "1h 1m"
        assert format_duration(90061) == "1d 1h"

        # Test timestamp formatting
        now = datetime.now()
        timestamp = now.timestamp()
        formatted = format_timestamp(timestamp)
        assert ":" in formatted  # Should contain time

        # Test session name validation
        assert validate_session_name("valid-session_name.123") is True
        assert validate_session_name("invalid'session") is False

    def test_error_handling_integration(self, temp_dirs):
        """Test error handling across CLI components."""
        from desto.cli.session_manager import CLISessionManager

        manager = CLISessionManager(
            log_dir=temp_dirs["log_dir"], scripts_dir=temp_dirs["scripts_dir"]
        )

        # Test handling non-existent session
        assert manager.session_exists("nonexistent") is False
        content = manager.get_log_content("nonexistent")
        assert content is None

        # Test handling subprocess errors
        with patch("desto.cli.session_manager.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("tmux not found")

            sessions = manager.list_sessions()
            assert sessions == {}

            result = manager.start_session("test", "echo hello")
            assert result is False

    @pytest.mark.skipif(True, reason="requires typer")
    def test_cli_commands_integration(self, temp_dirs):
        """Test CLI commands integration (requires typer)."""
        try:
            from typer.testing import CliRunner

            from desto.cli.main import app

            runner = CliRunner()

            # Test version command
            result = runner.invoke(app, ["version"])
            assert result.exit_code == 0
            assert "desto-cli" in result.stdout

            # Test doctor command
            with patch("desto.cli.main.shutil.which", return_value=None):
                with patch("desto.cli.main.CLISessionManager") as mock_manager_class:
                    mock_manager = Mock()
                    mock_manager.scripts_dir.exists.return_value = True
                    mock_manager.log_dir.exists.return_value = True
                    mock_manager.list_sessions.return_value = {}
                    mock_manager_class.return_value = mock_manager

                    result = runner.invoke(app, ["doctor"])
                    assert result.exit_code == 0
                    assert "System Check" in result.stdout

        except ImportError:
            pytest.skip("typer not available for CLI integration tests")

    def test_environment_variables_integration(self, temp_dirs):
        """Test environment variable handling."""
        from desto.cli.session_manager import CLISessionManager

        env_scripts = str(temp_dirs["temp_path"] / "env_scripts")
        env_logs = str(temp_dirs["temp_path"] / "env_logs")

        with patch.dict(
            "os.environ", {"DESTO_SCRIPTS_DIR": env_scripts, "DESTO_LOGS_DIR": env_logs}
        ):
            with patch("pathlib.Path.mkdir"):
                manager = CLISessionManager()
                assert str(manager.scripts_dir) == env_scripts
                assert str(manager.log_dir) == env_logs

    def test_cross_module_functionality(self, temp_dirs):
        """Test functionality that spans multiple modules."""
        from desto.cli.session_manager import CLISessionManager
        from desto.cli.utils import format_duration

        manager = CLISessionManager(
            log_dir=temp_dirs["log_dir"], scripts_dir=temp_dirs["scripts_dir"]
        )

        # Mock a session with runtime
        with patch.object(manager, "list_sessions") as mock_list:
            mock_list.return_value = {
                "test_session": {
                    "finished": False,
                    "runtime": 3661,  # 1h 1m 1s
                    "created": 1719835200.0,
                }
            }

            sessions = manager.list_sessions()
            session_info = sessions["test_session"]

            # Format the runtime using utility function
            formatted_runtime = format_duration(session_info["runtime"])
            assert formatted_runtime == "1h 1m"

            # Check session exists
            assert manager.session_exists("test_session") is True

    def test_file_operations_integration(self, temp_dirs):
        """Test file operations across CLI components."""
        from desto.cli.session_manager import CLISessionManager

        manager = CLISessionManager(
            log_dir=temp_dirs["log_dir"], scripts_dir=temp_dirs["scripts_dir"]
        )

        # Test script file path generation
        script_file = manager.get_script_file("test_script.sh")
        assert script_file == temp_dirs["scripts_dir"] / "test_script.sh"

        # Test log file path generation
        log_file = manager.get_log_file("test_session")
        assert log_file == temp_dirs["log_dir"] / "test_session.log"

        # Create and test actual file operations
        test_content = "#!/bin/bash\necho 'test script'\n"
        script_file.write_text(test_content)
        assert script_file.exists()
        assert script_file.read_text() == test_content

        log_content = "Session started\nCommand executed\nSession finished\n"
        log_file.write_text(log_content)

        retrieved_content = manager.get_log_content("test_session")
        assert retrieved_content == log_content

    def test_concurrent_operations_safety(self, temp_dirs):
        """Test that CLI operations are safe for concurrent use."""
        from desto.cli.session_manager import CLISessionManager

        # Create multiple managers (simulating concurrent access)
        manager1 = CLISessionManager(
            log_dir=temp_dirs["log_dir"], scripts_dir=temp_dirs["scripts_dir"]
        )
        manager2 = CLISessionManager(
            log_dir=temp_dirs["log_dir"], scripts_dir=temp_dirs["scripts_dir"]
        )

        # Both should use the same directories
        assert manager1.log_dir == manager2.log_dir
        assert manager1.scripts_dir == manager2.scripts_dir

        # Both should be able to check for sessions independently
        with patch("desto.cli.session_manager.subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="", returncode=0)

            sessions1 = manager1.list_sessions()
            sessions2 = manager2.list_sessions()

            assert sessions1 == sessions2 == {}

    def test_backwards_compatibility(self, temp_dirs):
        """Test backwards compatibility of CLI components."""
        from desto.cli.session_manager import CLISessionManager

        # Test that the manager works with minimal initialization
        manager = CLISessionManager()

        # Should not raise errors for basic operations
        assert manager.log_dir.name in ["desto_logs", "logs"]
        assert manager.scripts_dir.name in ["desto_scripts", "scripts"]

        # Should handle missing directories gracefully
        assert callable(manager.session_exists)
        assert callable(manager.get_log_content)
        assert callable(manager.get_script_file)
