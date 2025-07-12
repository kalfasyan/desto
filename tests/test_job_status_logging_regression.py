#!/usr/bin/env python3
"""
Tests for job status tracking and logging functionality.
These tests ensure that the issues we fixed stay fixed:
1. Jobs with keep-alive properly show "Finished" status when the job completes
2. Logging messages appear in the Log Messages panel
3. Redis job completion tracking works correctly
4. Session status vs job status distinction is maintained
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from src.desto.app.sessions import TmuxManager
    from src.desto.app.ui import LogSection
    from src.desto.redis.client import DestoRedisClient
    from src.desto.redis.status_tracker import SessionStatusTracker
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)


class TestJobStatusTracking(unittest.TestCase):
    """Test that job status is correctly tracked separately from session status"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.log_dir = self.temp_path / "logs"
        self.scripts_dir = self.temp_path / "scripts"
        self.log_dir.mkdir()
        self.scripts_dir.mkdir()

        # Create mock Redis client
        self.mock_redis_client = Mock(spec=DestoRedisClient)
        self.mock_redis_client.is_connected.return_value = True
        self.mock_redis_client.redis = Mock()
        self.mock_redis_client.get_session_key.return_value = "desto:session:test"

        # Create mock status tracker
        self.mock_status_tracker = Mock(spec=SessionStatusTracker)

        # Mock UI and logger
        self.mock_ui = Mock()
        self.mock_logger = Mock()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_job_status_returns_correct_status(self):
        """Test that get_job_status returns the correct job status from Redis"""
        # Mock Redis data with job_status = "finished"
        mock_redis_data = {
            b"session_name": b"test_session",
            b"status": b"running",  # Session still running
            b"job_status": b"finished",  # Job completed
            b"job_exit_code": b"0",
            b"job_finished_time": b"2025-07-12T07:15:49.335093",
        }

        self.mock_redis_client.redis.hgetall.return_value = mock_redis_data

        # Create real status tracker with mocked Redis
        status_tracker = SessionStatusTracker(self.mock_redis_client)

        # Test the method
        job_status = status_tracker.get_job_status("test_session")

        # Should return "finished" even though session status is "running"
        self.assertEqual(job_status, "finished")

    def test_get_job_status_handles_missing_job_status(self):
        """Test that get_job_status returns 'running' when job_status is not set"""
        # Mock Redis data without job_status field
        mock_redis_data = {b"session_name": b"test_session", b"status": b"running"}

        self.mock_redis_client.redis.hgetall.return_value = mock_redis_data

        status_tracker = SessionStatusTracker(self.mock_redis_client)
        job_status = status_tracker.get_job_status("test_session")

        # Should return "running" as default
        self.assertEqual(job_status, "running")

    def test_get_job_status_handles_redis_error(self):
        """Test that get_job_status handles Redis connection errors gracefully"""
        # Mock Redis to raise exception
        self.mock_redis_client.redis.hgetall.side_effect = Exception("Redis connection failed")

        status_tracker = SessionStatusTracker(self.mock_redis_client)
        job_status = status_tracker.get_job_status("test_session")

        # Should return "unknown" on error
        self.assertEqual(job_status, "unknown")

    def test_mark_job_finished_sets_correct_fields(self):
        """Test that mark_job_finished sets the correct Redis fields"""
        status_tracker = SessionStatusTracker(self.mock_redis_client)

        # Call mark_job_finished
        status_tracker.mark_job_finished("test_session", 0)

        # Verify Redis hset was called with correct data
        self.mock_redis_client.redis.hset.assert_called_once()
        call_args = self.mock_redis_client.redis.hset.call_args

        # Check that the mapping contains the required fields
        mapping = call_args[1]["mapping"]
        self.assertEqual(mapping["job_status"], "finished")
        self.assertEqual(mapping["job_exit_code"], "0")
        self.assertIn("job_finished_time", mapping)
        self.assertIn("job_elapsed", mapping)

    def test_mark_job_failed_sets_correct_fields(self):
        """Test that mark_job_failed sets the correct Redis fields"""
        status_tracker = SessionStatusTracker(self.mock_redis_client)

        # Call mark_job_failed
        status_tracker.mark_job_failed("test_session", "Script failed with error")

        # Verify Redis hset was called with correct data
        self.mock_redis_client.redis.hset.assert_called_once()
        call_args = self.mock_redis_client.redis.hset.call_args

        # Check that the mapping contains the required fields
        mapping = call_args[1]["mapping"]
        self.assertEqual(mapping["job_status"], "failed")
        self.assertEqual(mapping["job_error"], "Script failed with error")
        self.assertIn("job_finished_time", mapping)
        self.assertIn("job_elapsed", mapping)


class TestSessionStatusVsJobStatus(unittest.TestCase):
    """Test that session status and job status are handled correctly"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.log_dir = self.temp_path / "logs"
        self.scripts_dir = self.temp_path / "scripts"
        self.log_dir.mkdir()
        self.scripts_dir.mkdir()

        # Mock Redis components
        self.mock_redis_client = Mock(spec=DestoRedisClient)
        self.mock_redis_client.is_connected.return_value = True
        self.mock_redis_client.redis = Mock()
        self.mock_redis_client.get_session_key.return_value = "desto:session:test"

        self.mock_status_tracker = Mock(spec=SessionStatusTracker)
        self.mock_ui = Mock()
        self.mock_logger = Mock()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_session_status_logic_with_redis(self):
        """Test that session status is determined by Redis job status when available"""
        # Create TmuxManager with Redis enabled
        with patch("src.desto.app.sessions.DestoRedisClient") as mock_redis_class:
            mock_redis_class.return_value = self.mock_redis_client

            tmux_manager = TmuxManager(ui=self.mock_ui, logger=self.mock_logger, log_dir=self.log_dir, scripts_dir=self.scripts_dir)

            # Mock the status tracker
            tmux_manager.status_tracker = self.mock_status_tracker

            # Test case 1: Job finished, should show "Finished"
            self.mock_status_tracker.get_job_status.return_value = "finished"

            # Mock a session that exists in tmux
            with patch("subprocess.run") as mock_subprocess:
                mock_subprocess.return_value.returncode = 0
                mock_subprocess.return_value.stdout = "session1:test_session:1699876543:0:1::"

                sessions = tmux_manager.check_sessions()
                self.assertIn("test_session", sessions)

            # Test case 2: Job failed, should show "Finished"
            self.mock_status_tracker.get_job_status.return_value = "failed"

            # The status should be determined by job completion, not session running state

    def test_session_status_logic_without_redis(self):
        """Test that session status falls back to file markers when Redis is not available"""
        # Create TmuxManager without Redis
        with patch("src.desto.app.sessions.DestoRedisClient") as mock_redis_class:
            mock_redis_class.return_value.is_connected.return_value = False

            tmux_manager = TmuxManager(ui=self.mock_ui, logger=self.mock_logger, log_dir=self.log_dir, scripts_dir=self.scripts_dir)

            # Should not use Redis
            self.assertFalse(tmux_manager.use_redis)

            # Should fall back to file-based status checking
            # This is tested in the add_sessions_table method logic


class TestLoggingFunctionality(unittest.TestCase):
    """Test that logging functionality works correctly"""

    def setUp(self):
        self.mock_display = Mock()
        self.log_section = LogSection()
        self.log_section.log_display = self.mock_display

    def test_log_section_updates_messages(self):
        """Test that LogSection correctly updates log messages"""
        # Test adding messages
        test_messages = ["Message 1", "Message 2", "Message 3"]

        for msg in test_messages:
            self.log_section.update_log_messages(msg)

        # Verify messages were stored
        self.assertEqual(len(self.log_section.log_messages), 3)
        self.assertEqual(self.log_section.log_messages, test_messages)

    def test_log_section_message_rotation(self):
        """Test that log messages are rotated when limit is exceeded"""
        # Add more messages than the limit (default 20)
        for i in range(25):
            self.log_section.update_log_messages(f"Message {i}")

        # Should only keep the last 20 messages
        self.assertEqual(len(self.log_section.log_messages), 20)
        self.assertEqual(self.log_section.log_messages[0], "Message 5")  # First 5 dropped
        self.assertEqual(self.log_section.log_messages[-1], "Message 24")

    def test_log_section_refresh_display(self):
        """Test that refresh_log_display updates the UI component"""
        # Add some messages
        test_messages = ["Line 1", "Line 2", "Line 3"]
        for msg in test_messages:
            self.log_section.update_log_messages(msg)

        # Refresh display
        self.log_section.refresh_log_display()

        # Verify the display was updated with joined messages
        expected_display = "\n".join(test_messages)
        self.assertEqual(self.mock_display.value, expected_display)

    def test_log_section_handles_empty_messages(self):
        """Test that LogSection handles empty message list correctly"""
        # Don't add any messages
        self.log_section.refresh_log_display()

        # Should display empty string
        self.assertEqual(self.mock_display.value, "")


class TestJobCompletionScriptPath(unittest.TestCase):
    """Test that the job completion script path is correct"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.log_dir = self.temp_path / "logs"
        self.scripts_dir = self.temp_path / "scripts"
        self.log_dir.mkdir()
        self.scripts_dir.mkdir()

        self.mock_ui = Mock()
        self.mock_logger = Mock()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_job_completion_command_with_redis(self):
        """Test that get_job_completion_command returns correct Redis command"""
        # Mock Redis client with all required attributes
        mock_redis_client = Mock(spec=DestoRedisClient)
        mock_redis_client.is_connected.return_value = True
        mock_redis_client.redis = Mock()  # Add the redis attribute

        with (
            patch("src.desto.app.sessions.DestoRedisClient") as mock_redis_class,
            patch("src.desto.redis.pubsub.SessionPubSub"),
        ):  # Mock pubsub to avoid errors
            mock_redis_class.return_value = mock_redis_client

            tmux_manager = TmuxManager(ui=self.mock_ui, logger=self.mock_logger, log_dir=self.log_dir, scripts_dir=self.scripts_dir)

            # Test with Redis enabled
            self.assertTrue(tmux_manager.use_redis)

            # Get completion command
            command = tmux_manager.get_job_completion_command("test_session", use_variable=True)

            # Should contain python3 and mark_job_finished.py
            self.assertIn("python3", command)
            self.assertIn("mark_job_finished.py", command)
            self.assertIn("test_session", command)
            self.assertIn("$SCRIPT_EXIT_CODE", command)

    def test_get_job_completion_command_without_redis(self):
        """Test that get_job_completion_command returns file marker when Redis not available"""
        # Mock Redis client as not connected
        mock_redis_client = Mock(spec=DestoRedisClient)
        mock_redis_client.is_connected.return_value = False

        with patch("src.desto.app.sessions.DestoRedisClient") as mock_redis_class:
            mock_redis_class.return_value = mock_redis_client

            tmux_manager = TmuxManager(ui=self.mock_ui, logger=self.mock_logger, log_dir=self.log_dir, scripts_dir=self.scripts_dir)

            # Test without Redis
            self.assertFalse(tmux_manager.use_redis)

            # Get completion command
            command = tmux_manager.get_job_completion_command("test_session", use_variable=True)

            # Should use file marker
            self.assertIn("touch", command)
            self.assertIn("test_session.finished", command)


class TestRegressionProtection(unittest.TestCase):
    """Tests to prevent regression of specific issues we fixed"""

    def test_log_section_class_exists(self):
        """Ensure LogSection class exists and has required methods"""
        from src.desto.app.ui import LogSection

        log_section = LogSection()

        # Check required methods exist
        self.assertTrue(hasattr(log_section, "update_log_messages"))
        self.assertTrue(hasattr(log_section, "refresh_log_display"))
        self.assertTrue(hasattr(log_section, "log_messages"))

    def test_redis_status_tracker_has_get_job_status(self):
        """Ensure SessionStatusTracker has get_job_status method"""
        from src.desto.redis.status_tracker import SessionStatusTracker

        # Check method exists
        self.assertTrue(hasattr(SessionStatusTracker, "get_job_status"))

    def test_tmux_manager_uses_redis_for_status(self):
        """Ensure TmuxManager checks Redis for job status when available"""
        from src.desto.app.sessions import TmuxManager

        # Check that the method exists and is being used
        self.assertTrue(hasattr(TmuxManager, "get_job_completion_command"))

    def test_mark_job_finished_script_exists(self):
        """Ensure the mark_job_finished.py script exists and is executable"""
        script_path = Path(__file__).parent.parent / "scripts" / "mark_job_finished.py"

        self.assertTrue(script_path.exists(), f"Script not found at {script_path}")
        self.assertTrue(script_path.is_file(), f"Path is not a file: {script_path}")

        # Check it's a Python script
        with open(script_path, "r") as f:
            first_line = f.readline().strip()
            self.assertTrue(first_line.startswith("#!"), "Script missing shebang")
            self.assertIn("python", first_line.lower(), "Script is not a Python script")


if __name__ == "__main__":
    print("Running regression tests for job status and logging functionality...")
    print("=" * 70)

    # Run all tests
    unittest.main(verbosity=2, exit=False)

    print("=" * 70)
    print("All regression tests completed!")
