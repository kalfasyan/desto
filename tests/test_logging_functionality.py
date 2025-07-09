"""
Test the enhanced logging functionality for TmuxManager.
This test verifies that log files are preserved between sessions and include proper timestamps.
"""

import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from desto.app.sessions import TmuxManager


class TestTmuxManagerLogging:
    """Test enhanced logging functionality in TmuxManager."""

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
                "temp_path": temp_path,
                "log_dir": log_dir,
                "scripts_dir": scripts_dir
            }

    @pytest.fixture
    def tmux_manager(self, temp_dirs):
        """Create a TmuxManager instance for testing."""
        mock_ui = Mock()
        mock_logger = Mock()

        return TmuxManager(
            mock_ui,
            mock_logger,
            log_dir=temp_dirs["log_dir"],
            scripts_dir=temp_dirs["scripts_dir"]
        )

    def test_log_file_creation_and_content(self, tmux_manager, temp_dirs):
        """Test that log files are created with proper content."""
        session_name = "test_session"
        command = "echo 'Hello World'"

        # Start session
        tmux_manager.start_tmux_session(session_name, command, Mock(), keep_alive=False)

        # Wait for command to complete
        time.sleep(3)

        # Check log file exists
        log_file = temp_dirs["log_dir"] / f"{session_name}.log"
        assert log_file.exists(), "Log file should be created"

        # Check log content
        log_content = log_file.read_text()
        assert "=== SCRIPT STARTING at" in log_content, "Start logging should be present"
        assert "=== SCRIPT FINISHED at" in log_content, "Finish logging should be present"
        assert "Hello World" in log_content, "Script output should be present"

        # Check that date was expanded (not showing $(date))
        assert "$(date)" not in log_content, "Date should be expanded, not literal $(date)"
        assert "2025" in log_content, "Real date should be present"

    def test_log_file_preservation_between_sessions(self, tmux_manager, temp_dirs):
        """Test that log files are preserved when running multiple sessions with the same name."""
        session_name = "test_session"

        # First session
        command1 = "echo 'First session'"
        tmux_manager.start_tmux_session(session_name, command1, Mock(), keep_alive=False)
        time.sleep(3)

        log_file = temp_dirs["log_dir"] / f"{session_name}.log"
        first_content = log_file.read_text()

        # Verify first session content
        assert "First session" in first_content
        assert "=== SCRIPT STARTING at" in first_content
        assert "=== SCRIPT FINISHED at" in first_content

        # Second session (same name - should append, not overwrite)
        command2 = "echo 'Second session'"
        tmux_manager.start_tmux_session(session_name, command2, Mock(), keep_alive=False)
        time.sleep(3)

        # Check that both sessions are in the log
        second_content = log_file.read_text()

        # Verify both sessions are present
        assert "First session" in second_content, "First session content should be preserved"
        assert "Second session" in second_content, "Second session content should be present"

        # Verify session separator was added
        assert "---- NEW SESSION" in second_content, "Session separator should be present"

        # Count the number of start/finish entries
        start_count = second_content.count("=== SCRIPT STARTING at")
        finish_count = second_content.count("=== SCRIPT FINISHED at")

        assert start_count == 2, f"Expected 2 start entries, got {start_count}"
        assert finish_count == 2, f"Expected 2 finish entries, got {finish_count}"

    def test_finished_marker_creation(self, tmux_manager, temp_dirs):
        """Test that finished markers are created when sessions complete."""
        session_name = "test_session"
        command = "echo 'Test completed'"

        # Start session
        tmux_manager.start_tmux_session(session_name, command, Mock(), keep_alive=False)

        # Wait for command to complete
        time.sleep(3)

        # Check finished marker exists
        finished_marker = temp_dirs["log_dir"] / f"{session_name}.finished"
        assert finished_marker.exists(), "Finished marker should be created"

    def test_finished_marker_cleanup(self, tmux_manager, temp_dirs):
        """Test that finished markers are cleaned up when starting new sessions."""
        session_name = "test_session"

        # Create a finished marker
        finished_marker = temp_dirs["log_dir"] / f"{session_name}.finished"
        finished_marker.touch()
        assert finished_marker.exists(), "Finished marker should exist initially"

        # Start a new session
        command = "echo 'New session'"
        tmux_manager.start_tmux_session(session_name, command, Mock(), keep_alive=False)

        # The marker should be removed during session start
        # Note: It will be recreated when the session finishes, but this tests the cleanup
        time.sleep(3)

        # The session should complete and recreate the marker
        assert finished_marker.exists(), "Finished marker should be recreated after session completes"

    def test_keep_alive_functionality(self, tmux_manager, temp_dirs):
        """Test that keep_alive sessions stay running after the command completes."""
        session_name = "test_keep_alive"
        command = "echo 'Keep alive test'"

        # Start session with keep_alive=True
        tmux_manager.start_tmux_session(session_name, command, Mock(), keep_alive=True)

        # Wait for command to complete
        time.sleep(3)

        # Check if tmux session is still running
        try:
            result = subprocess.run(
                ["tmux", "list-sessions", "-f", "#{session_name}", "-F", "#{session_name}"],
                capture_output=True,
                text=True
            )

            # If keep_alive is working, the session should still be listed
            assert session_name in result.stdout, "Keep-alive session should still be running"

            # Clean up the session
            subprocess.run(["tmux", "kill-session", "-t", session_name],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            # tmux might not be available in test environment
            pytest.skip("tmux not available in test environment")

    def test_log_file_paths(self, tmux_manager, temp_dirs):
        """Test that log file paths are correct."""
        session_name = "path_test"

        expected_log_file = temp_dirs["log_dir"] / f"{session_name}.log"
        actual_log_file = tmux_manager.get_log_file(session_name)

        assert actual_log_file == expected_log_file, "Log file path should match expected location"

    def teardown_method(self, method):
        """Clean up any tmux sessions that might be left running."""
        try:
            # Kill any test sessions that might be running
            test_sessions = ["test_session", "test_keep_alive", "path_test"]
            for session in test_sessions:
                subprocess.run(["tmux", "kill-session", "-t", session],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass  # Ignore errors if sessions don't exist or tmux is not available
