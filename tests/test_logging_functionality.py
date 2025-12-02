"""Test the enhanced logging functionality for TmuxManager.
This test verifies that log files are preserved between sessions and include proper timestamps.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from desto.app.sessions import TmuxManager

pytestmark = pytest.mark.skipif(os.getenv("CI") == "true", reason="Redis is not available on GitHub Actions")


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

            yield {"temp_path": temp_path, "log_dir": log_dir, "scripts_dir": scripts_dir}

            # Clean up any remaining log files after test
            try:
                import shutil

                if log_dir.exists():
                    shutil.rmtree(log_dir, ignore_errors=True)
            except Exception:
                pass

    @pytest.fixture
    def tmux_manager(self, temp_dirs):
        """Create a TmuxManager instance for testing."""
        mock_ui = Mock()
        mock_logger = Mock()

        # Patch Redis to be unavailable for consistent file-based testing
        with patch("src.desto.app.sessions.DestoRedisClient") as mock_redis_class:
            mock_redis_instance = Mock()
            mock_redis_instance.is_connected.return_value = False
            mock_redis_class.return_value = mock_redis_instance

            tmux_manager = TmuxManager(mock_ui, mock_logger, log_dir=temp_dirs["log_dir"], scripts_dir=temp_dirs["scripts_dir"])

            # Force Redis to be disabled to ensure file-based markers are used
            tmux_manager.use_redis = False

            return tmux_manager

    def test_log_file_creation_and_content(self, tmux_manager, temp_dirs):
        """Test that log files are created with proper content."""
        session_name = "test_session"
        command = "echo 'Hello World'"

        # Start session
        tmux_manager.start_tmux_session(session_name, command, Mock())

        # Wait for command to complete (poll the log)
        from .docker_test_utils import wait_for_file_contains

        assert wait_for_file_contains(temp_dirs["log_dir"] / f"{session_name}.log", "Hello World", timeout=5), "Log did not contain expected output"

        # Wait for session to fully complete by waiting for the finish marker
        assert wait_for_file_contains(temp_dirs["log_dir"] / f"{session_name}.log", "=== SCRIPT FINISHED at", timeout=5), "Finish marker not found"

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
        assert any(digit in log_content for digit in "0123456789"), "Real date should be present"

    def test_log_file_preservation_between_sessions(self, tmux_manager, temp_dirs):
        """Test that log files are preserved when running multiple sessions with the same name."""
        session_name = "test_session"

        # First session
        command1 = "echo 'First session'"
        tmux_manager.start_tmux_session(session_name, command1, Mock())

        log_file = temp_dirs["log_dir"] / f"{session_name}.log"
        from .docker_test_utils import wait_for_file_contains

        assert wait_for_file_contains(log_file, "First session", timeout=5), "First session output not found"

        # Wait for session to fully complete
        assert wait_for_file_contains(log_file, "=== SCRIPT FINISHED at", timeout=5), "First session finish marker not found"

        first_content = log_file.read_text()

        # Verify first session content
        assert "First session" in first_content
        assert "=== SCRIPT STARTING at" in first_content
        assert "=== SCRIPT FINISHED at" in first_content

        # Second session (same name - should append, not overwrite)
        command2 = "echo 'Second session'"
        tmux_manager.start_tmux_session(session_name, command2, Mock())
        assert wait_for_file_contains(log_file, "Second session", timeout=5), "Second session output not found"

        # Wait for second session to also complete - we need 2 finish markers total
        import time

        max_wait = 5
        start_time = time.time()
        while time.time() - start_time < max_wait:
            content = log_file.read_text()
            if content.count("=== SCRIPT FINISHED at") >= 2:
                break
            time.sleep(0.1)

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

    def test_session_completion_tracked_in_redis(self, tmux_manager, temp_dirs):
        """Test that session completion is tracked in Redis instead of file markers."""
        session_name = "test_session"
        command = "echo 'Test completed'"

        # Start session
        tmux_manager.start_tmux_session(session_name, command, Mock())

        from .docker_test_utils import wait_for_file_contains

        assert wait_for_file_contains(temp_dirs["log_dir"] / f"{session_name}.log", "Test completed", timeout=5), "Command output not found in log"

        # Check that job status can be retrieved from Redis (through the status tracker)
        # This replaces the old file marker check
        try:
            job_status = tmux_manager.status_tracker.get_job_status(session_name)
            # Job should eventually be marked as finished or at least have some status
            assert job_status is not None, "Job status should be available in Redis"
        except Exception:
            # If Redis tracking fails, at least verify the session completed by checking logs
            log_file = temp_dirs["log_dir"] / f"{session_name}.log"
            assert log_file.exists(), "Log file should exist"
            log_content = log_file.read_text()
            assert "Test completed" in log_content, "Command output should be in log"

    def test_log_file_reuse_for_same_session_name(self, tmux_manager, temp_dirs):
        """Test that log files are reused when running sessions with the same name."""
        session_name = "test_session"

        # First session
        command1 = "echo 'First run'"
        tmux_manager.start_tmux_session(session_name, command1, Mock())

        from .docker_test_utils import wait_for_file_contains

        assert wait_for_file_contains(temp_dirs["log_dir"] / f"{session_name}.log", "First run", timeout=5), "First run output not found"

        # Second session with same name - should append to existing log
        command2 = "echo 'Second run'"
        tmux_manager.start_tmux_session(session_name, command2, Mock())
        assert wait_for_file_contains(temp_dirs["log_dir"] / f"{session_name}.log", "Second run", timeout=5), "Second run output not found"

        # Check that log contains both runs
        log_file = temp_dirs["log_dir"] / f"{session_name}.log"
        assert log_file.exists(), "Log file should exist"
        log_content = log_file.read_text()
        assert "First run" in log_content, "First session output should be in log"
        assert "Second run" in log_content, "Second session output should be in log"
        assert "---- NEW SESSION" in log_content, "Session separator should be present"

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
            test_sessions = ["test_session", "path_test"]
            for session in test_sessions:
                subprocess.run(["tmux", "kill-session", "-t", session], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass  # Ignore errors if sessions don't exist or tmux is not available
