import shutil
import subprocess
import time
from unittest.mock import MagicMock

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


@pytest.fixture
def tmux_manager(mock_ui, mock_logger, tmp_path):
    return TmuxManager(mock_ui, mock_logger, log_dir=tmp_path, scripts_dir=tmp_path)


@pytest.mark.skipif(not shutil.which("at"), reason="'at' command not available")
class TestScheduledJobsIntegration:
    """Integration tests for scheduled jobs functionality (requires 'at' command)"""

    def cleanup_test_jobs(self):
        """Clean up any test jobs that might exist"""
        try:
            result = subprocess.run(["atq"], capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.strip() and "test_job_" in line:
                        job_id = line.strip().split()[0]
                        subprocess.run(["atrm", job_id], capture_output=True)
        except Exception:
            pass  # Ignore cleanup errors

    def test_real_scheduled_job_creation_and_removal(self, tmux_manager):
        """Test creating and removing a real scheduled job"""
        self.cleanup_test_jobs()

        try:
            # Create a test job
            test_command = "echo 'test_job_12345_unique' > /tmp/test_output.txt"
            result = subprocess.run(
                f"echo '{test_command}' | at now + 2 minutes",
                shell=True,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                pytest.skip(f"Failed to create test job: {result.stderr}")

            # Wait a moment for job to be registered
            time.sleep(1)

            # Get jobs and verify our test job exists
            jobs = tmux_manager.get_scheduled_jobs()

            # Note: We can't easily check job content, so we'll check if any jobs exist
            # and trust that our job was created (since we just created it)
            initial_job_count = len(jobs)

            if initial_job_count == 0:
                pytest.skip(
                    "No jobs found after creation - 'at' might not be working properly"
                )

            # Kill all scheduled jobs
            success_count, total_count, errors = tmux_manager.kill_scheduled_jobs()

            # Verify jobs were removed
            time.sleep(1)
            remaining_jobs = tmux_manager.get_scheduled_jobs()

            assert len(remaining_jobs) < initial_job_count, (
                "Some jobs should have been removed"
            )
            assert success_count <= total_count, (
                "Success count should not exceed total count"
            )

            if errors:
                print(f"Errors during job removal: {errors}")
                # Don't fail the test due to permission errors, etc.

        finally:
            # Always clean up
            self.cleanup_test_jobs()

    def test_get_scheduled_jobs_real_format(self, tmux_manager):
        """Test that get_scheduled_jobs correctly parses real atq output"""
        # This test just verifies that the parsing doesn't crash on real output
        jobs = tmux_manager.get_scheduled_jobs()

        # Should return a list (even if empty)
        assert isinstance(jobs, list)

        # If jobs exist, they should have the expected structure
        for job in jobs:
            assert isinstance(job, dict)
            assert "id" in job
            assert "datetime" in job
            assert "user" in job
            assert isinstance(job["id"], str)
            assert isinstance(job["datetime"], str)
            assert isinstance(job["user"], str)

    def test_kill_scheduled_jobs_no_permission_errors(self, tmux_manager):
        """Test that kill_scheduled_jobs handles permission errors gracefully"""
        # This test ensures the method doesn't crash even if we can't remove jobs
        # (e.g., due to permissions or jobs belonging to other users)

        success_count, total_count, errors = tmux_manager.kill_scheduled_jobs()

        # Should return valid counts
        assert isinstance(success_count, int)
        assert isinstance(total_count, int)
        assert isinstance(errors, list)
        assert success_count >= 0
        assert total_count >= 0
        assert success_count <= total_count


@pytest.mark.skipif(not shutil.which("tmux"), reason="'tmux' command not available")
class TestCombinedFunctionalityIntegration:
    """Integration tests for combined tmux sessions and scheduled jobs functionality"""

    def cleanup_test_sessions(self):
        """Clean up any test tmux sessions"""
        try:
            result = subprocess.run(
                ["tmux", "list-sessions", "-F", "#{session_name}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                for session_name in result.stdout.splitlines():
                    if session_name.startswith("test_session_"):
                        subprocess.run(
                            ["tmux", "kill-session", "-t", session_name],
                            capture_output=True,
                        )
        except Exception:
            pass

    def cleanup_test_jobs(self):
        """Clean up any test jobs"""
        try:
            result = subprocess.run(["atq"], capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.strip() and "test_job_" in line:
                        job_id = line.strip().split()[0]
                        subprocess.run(["atrm", job_id], capture_output=True)
        except Exception:
            pass

    @pytest.mark.skipif(not shutil.which("at"), reason="'at' command not available")
    def test_kill_all_sessions_and_jobs_integration(self, tmux_manager):
        """Test the combined kill functionality with real sessions and jobs"""
        self.cleanup_test_sessions()
        self.cleanup_test_jobs()

        try:
            # Create a test tmux session
            subprocess.run(
                [
                    "tmux",
                    "new-session",
                    "-d",
                    "-s",
                    "test_session_integration",
                    "sleep 30",
                ],
                check=True,
            )

            # Create a test scheduled job (if 'at' is available)
            if shutil.which("at"):
                subprocess.run(
                    "echo 'echo test_job_integration' | at now + 3 minutes",
                    shell=True,
                    capture_output=True,
                    text=True,
                )

            # Wait for items to be registered
            time.sleep(1)

            # Get initial counts
            initial_sessions = tmux_manager.check_sessions()

            test_session_count = len(
                [s for s in initial_sessions.keys() if s.startswith("test_session_")]
            )

            # Kill all sessions and jobs
            session_success, session_total, job_success, job_total, all_errors = (
                tmux_manager.kill_all_sessions_and_jobs()
            )

            # Verify results
            assert isinstance(session_success, int)
            assert isinstance(session_total, int)
            assert isinstance(job_success, int)
            assert isinstance(job_total, int)
            assert isinstance(all_errors, list)

            # Should have killed at least our test session
            assert session_success >= min(test_session_count, 1), (
                "Should have killed at least one session"
            )

            # Wait and verify sessions are gone
            time.sleep(1)
            remaining_sessions = tmux_manager.check_sessions()
            remaining_test_sessions = [
                s for s in remaining_sessions.keys() if s.startswith("test_session_")
            ]

            assert len(remaining_test_sessions) == 0, "Test sessions should be removed"

        finally:
            # Always clean up
            self.cleanup_test_sessions()
            self.cleanup_test_jobs()

    def test_confirm_kill_all_sessions_dialog_structure(self, tmux_manager):
        """Test that the confirmation dialog is properly structured"""
        # Mock the pause/resume functions
        tmux_manager.pause_updates = MagicMock()
        tmux_manager.resume_updates = MagicMock()

        # This should not crash and should create proper UI elements
        tmux_manager.confirm_kill_all_sessions()

        # Should have called pause updates
        tmux_manager.pause_updates.assert_called_once()

        # Should have created UI elements (we can't easily test the full dialog,
        # but we can ensure it doesn't crash and basic UI calls are made)
        assert tmux_manager.ui.dialog.called or tmux_manager.ui.notification.called
