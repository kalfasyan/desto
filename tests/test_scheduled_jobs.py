import subprocess
from unittest.mock import MagicMock, call, patch

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


class TestScheduledJobs:
    """Test scheduled jobs functionality"""

    @patch("desto.app.sessions.subprocess.run")
    def test_get_scheduled_jobs_empty(self, mock_run, tmux_manager):
        """Test getting scheduled jobs when none exist"""
        # Mock empty atq output
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        jobs = tmux_manager.get_scheduled_jobs()

        assert jobs == []
        mock_run.assert_called_once_with(["atq"], capture_output=True, text=True)

    @patch("desto.app.sessions.subprocess.run")
    def test_get_scheduled_jobs_with_jobs(self, mock_run, tmux_manager):
        """Test getting scheduled jobs when they exist"""
        # Mock atq output with sample jobs
        mock_output = """39	Mon Jun 30 15:30:00 2025 a	kalfasy
40	Tue Jul  1 10:00:00 2025 a	kalfasy
41	Wed Jul  2 14:45:00 2025 a	kalfasy"""

        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)

        jobs = tmux_manager.get_scheduled_jobs()

        assert len(jobs) == 3
        assert jobs[0]["id"] == "39"
        assert jobs[0]["user"] == "kalfasy"
        # The parsing takes parts[1:5], so it would be "Mon Jun 30 15:30:00"
        assert "Mon Jun 30 15:30:00" in jobs[0]["datetime"]

        assert jobs[1]["id"] == "40"
        assert jobs[2]["id"] == "41"

        mock_run.assert_called_once_with(["atq"], capture_output=True, text=True)

    @patch("desto.app.sessions.subprocess.run")
    def test_get_scheduled_jobs_command_fails(self, mock_run, tmux_manager):
        """Test getting scheduled jobs when atq command fails"""
        # Mock failed atq command
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="atq: command not found"
        )

        jobs = tmux_manager.get_scheduled_jobs()

        assert jobs == []
        mock_run.assert_called_once_with(["atq"], capture_output=True, text=True)

    @patch("desto.app.sessions.subprocess.run")
    def test_get_scheduled_jobs_exception(self, mock_run, tmux_manager):
        """Test getting scheduled jobs when an exception occurs"""
        # Mock exception
        mock_run.side_effect = Exception("Connection error")

        jobs = tmux_manager.get_scheduled_jobs()

        assert jobs == []
        tmux_manager.logger.warning.assert_called_once()

    @patch("desto.app.sessions.subprocess.run")
    def test_kill_scheduled_jobs_empty(self, mock_run, tmux_manager):
        """Test killing scheduled jobs when none exist"""
        # Mock empty atq output
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        success, total, errors = tmux_manager.kill_scheduled_jobs()

        assert success == 0
        assert total == 0
        assert errors == []
        mock_run.assert_called_once_with(["atq"], capture_output=True, text=True)

    @patch("desto.app.sessions.subprocess.run")
    def test_kill_scheduled_jobs_success(self, mock_run, tmux_manager):
        """Test successfully killing scheduled jobs"""
        # Mock atq output first, then atrm success
        mock_output = """39	Mon Jun 30 15:30:00 2025 a	kalfasy
40	Tue Jul  1 10:00:00 2025 a	kalfasy"""

        # First call to atq returns jobs, subsequent calls to atrm succeed
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=mock_output),  # atq call
            MagicMock(returncode=0),  # atrm for job 39
            MagicMock(returncode=0),  # atrm for job 40
        ]

        success, total, errors = tmux_manager.kill_scheduled_jobs()

        assert success == 2
        assert total == 2
        assert errors == []

        # Verify calls
        expected_calls = [
            call(["atq"], capture_output=True, text=True),
            call(["atrm", "39"], check=True),
            call(["atrm", "40"], check=True),
        ]
        mock_run.assert_has_calls(expected_calls)

    @patch("desto.app.sessions.subprocess.run")
    def test_kill_scheduled_jobs_partial_failure(self, mock_run, tmux_manager):
        """Test killing scheduled jobs with some failures"""
        # Mock atq output
        mock_output = """39	Mon Jun 30 15:30:00 2025 a	kalfasy
40	Tue Jul  1 10:00:00 2025 a	kalfasy"""

        # First job succeeds, second fails
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=mock_output),  # atq call
            MagicMock(returncode=0),  # atrm for job 39 succeeds
            subprocess.CalledProcessError(
                1, ["atrm", "40"], stderr="Job not found"
            ),  # atrm for job 40 fails
        ]

        success, total, errors = tmux_manager.kill_scheduled_jobs()

        assert success == 1
        assert total == 2
        assert len(errors) == 1
        assert "Failed to remove job '40'" in errors[0]

    @patch("desto.app.sessions.subprocess.run")
    def test_kill_scheduled_jobs_unexpected_error(self, mock_run, tmux_manager):
        """Test killing scheduled jobs with unexpected errors"""
        # Mock atq output
        mock_output = """39	Mon Jun 30 15:30:00 2025 a	kalfasy"""

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=mock_output),  # atq call
            Exception("Unexpected error"),  # atrm throws unexpected error
        ]

        success, total, errors = tmux_manager.kill_scheduled_jobs()

        assert success == 0
        assert total == 1
        assert len(errors) == 1
        assert "Unexpected error removing job '39'" in errors[0]


class TestKillAllSessionsAndJobs:
    """Test the combined kill all functionality"""

    @patch.object(TmuxManager, "kill_scheduled_jobs")
    @patch.object(TmuxManager, "kill_all_sessions")
    def test_kill_all_sessions_and_jobs_success(
        self, mock_kill_sessions, mock_kill_jobs, tmux_manager
    ):
        """Test successfully killing all sessions and jobs"""
        # Mock successful operations
        mock_kill_sessions.return_value = (2, 2, [])  # 2/2 sessions killed
        mock_kill_jobs.return_value = (1, 1, [])  # 1/1 jobs killed

        session_success, session_total, job_success, job_total, all_errors = (
            tmux_manager.kill_all_sessions_and_jobs()
        )

        assert session_success == 2
        assert session_total == 2
        assert job_success == 1
        assert job_total == 1
        assert all_errors == []

        mock_kill_sessions.assert_called_once()
        mock_kill_jobs.assert_called_once()

    @patch.object(TmuxManager, "kill_scheduled_jobs")
    @patch.object(TmuxManager, "kill_all_sessions")
    def test_kill_all_sessions_and_jobs_with_errors(
        self, mock_kill_sessions, mock_kill_jobs, tmux_manager
    ):
        """Test killing all sessions and jobs with some errors"""
        # Mock operations with errors
        session_errors = ["Session error 1", "Session error 2"]
        job_errors = ["Job error 1"]

        mock_kill_sessions.return_value = (1, 2, session_errors)  # 1/2 sessions killed
        mock_kill_jobs.return_value = (0, 1, job_errors)  # 0/1 jobs killed

        session_success, session_total, job_success, job_total, all_errors = (
            tmux_manager.kill_all_sessions_and_jobs()
        )

        assert session_success == 1
        assert session_total == 2
        assert job_success == 0
        assert job_total == 1
        assert len(all_errors) == 3
        assert "Session error 1" in all_errors
        assert "Session error 2" in all_errors
        assert "Job error 1" in all_errors

    @patch.object(TmuxManager, "kill_scheduled_jobs")
    @patch.object(TmuxManager, "kill_all_sessions")
    def test_kill_all_sessions_and_jobs_empty(
        self, mock_kill_sessions, mock_kill_jobs, tmux_manager
    ):
        """Test killing all when no sessions or jobs exist"""
        # Mock empty operations
        mock_kill_sessions.return_value = (0, 0, [])
        mock_kill_jobs.return_value = (0, 0, [])

        session_success, session_total, job_success, job_total, all_errors = (
            tmux_manager.kill_all_sessions_and_jobs()
        )

        assert session_success == 0
        assert session_total == 0
        assert job_success == 0
        assert job_total == 0
        assert all_errors == []


class TestConfirmKillAllSessions:
    """Test the UI confirmation dialog functionality"""

    @patch.object(TmuxManager, "get_scheduled_jobs")
    @patch.object(TmuxManager, "check_sessions")
    def test_confirm_kill_all_sessions_no_jobs_or_sessions(
        self, mock_check_sessions, mock_get_jobs, tmux_manager
    ):
        """Test confirmation dialog when no sessions or jobs exist"""
        # Mock empty sessions and jobs
        mock_check_sessions.return_value = {}
        mock_get_jobs.return_value = []

        # Mock pause/resume functions
        tmux_manager.pause_updates = MagicMock()
        tmux_manager.resume_updates = MagicMock()

        tmux_manager.confirm_kill_all_sessions()

        # Should pause updates, show notification, and resume updates
        tmux_manager.pause_updates.assert_called_once()
        tmux_manager.resume_updates.assert_called_once()
        tmux_manager.ui.notification.assert_called_once()

        # Check notification message
        notification_call = tmux_manager.ui.notification.call_args
        assert "No active sessions or scheduled jobs" in notification_call[0][0]

    @patch.object(TmuxManager, "get_scheduled_jobs")
    @patch.object(TmuxManager, "check_sessions")
    def test_confirm_kill_all_sessions_with_jobs_and_sessions(
        self, mock_check_sessions, mock_get_jobs, tmux_manager, tmp_path
    ):
        """Test confirmation dialog when both sessions and jobs exist"""
        # Mock sessions and jobs
        mock_check_sessions.return_value = {
            "session1": {"created": 1640995200},  # Mock session
            "session2": {"created": 1640995300},
        }
        mock_get_jobs.return_value = [
            {"id": "39", "datetime": "Mon Jun 30 15:30:00 2025", "user": "testuser"}
        ]

        # Create finished marker for session2 to test finished vs running logic
        finished_marker = tmp_path / "session2.finished"
        finished_marker.touch()

        # Mock pause function
        tmux_manager.pause_updates = MagicMock()

        tmux_manager.confirm_kill_all_sessions()

        # Should pause updates and open dialog
        tmux_manager.pause_updates.assert_called_once()
        tmux_manager.ui.dialog.assert_called_once()

    @patch.object(TmuxManager, "get_scheduled_jobs")
    @patch.object(TmuxManager, "check_sessions")
    def test_confirm_kill_all_sessions_only_jobs(
        self, mock_check_sessions, mock_get_jobs, tmux_manager
    ):
        """Test confirmation dialog when only scheduled jobs exist"""
        # Mock no sessions, but some jobs
        mock_check_sessions.return_value = {}
        mock_get_jobs.return_value = [
            {"id": "39", "datetime": "Mon Jun 30 15:30:00 2025", "user": "testuser"},
            {"id": "40", "datetime": "Tue Jul  1 10:00:00 2025", "user": "testuser"},
        ]

        # Mock pause function
        tmux_manager.pause_updates = MagicMock()

        tmux_manager.confirm_kill_all_sessions()

        # Should pause updates and open dialog
        tmux_manager.pause_updates.assert_called_once()
        tmux_manager.ui.dialog.assert_called_once()

    @patch.object(TmuxManager, "get_scheduled_jobs")
    @patch.object(TmuxManager, "check_sessions")
    def test_confirm_kill_all_sessions_only_sessions(
        self, mock_check_sessions, mock_get_jobs, tmux_manager
    ):
        """Test confirmation dialog when only sessions exist"""
        # Mock some sessions, but no jobs
        mock_check_sessions.return_value = {"session1": {"created": 1640995200}}
        mock_get_jobs.return_value = []

        # Mock pause function
        tmux_manager.pause_updates = MagicMock()

        tmux_manager.confirm_kill_all_sessions()

        # Should pause updates and open dialog
        tmux_manager.pause_updates.assert_called_once()
        tmux_manager.ui.dialog.assert_called_once()
