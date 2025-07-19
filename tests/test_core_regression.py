#!/usr/bin/env python3
"""
Simple regression tests focusing on core functionality that must not break.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from src.desto.app.ui import LogSection
    from src.desto.redis.client import DestoRedisClient
    from src.desto.redis.status_tracker import SessionStatusTracker
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)


class TestCoreRegression(unittest.TestCase):
    """Core regression tests to prevent breakage of fixed functionality"""

    def test_log_section_exists_and_works(self):
        """Test that LogSection class exists and basic functionality works"""
        log_section = LogSection()

        # Test that required attributes exist
        self.assertTrue(hasattr(log_section, "log_messages"))
        self.assertTrue(hasattr(log_section, "update_log_messages"))
        self.assertTrue(hasattr(log_section, "refresh_log_display"))

        # Test basic functionality
        self.assertIsInstance(log_section.log_messages, list)
        self.assertEqual(len(log_section.log_messages), 0)

        # Test adding messages
        log_section.update_log_messages("Test message")
        self.assertEqual(len(log_section.log_messages), 1)
        self.assertEqual(log_section.log_messages[0], "Test message")

    def test_redis_status_tracker_has_job_status_method(self):
        """Test that SessionStatusTracker has get_job_status method"""
        self.assertTrue(hasattr(SessionStatusTracker, "get_job_status"))

        # Test with mock Redis client
        mock_redis_client = Mock(spec=DestoRedisClient)
        mock_redis_client.redis = Mock()
        mock_redis_client.get_session_key.return_value = "desto:session:test"

        # Test with finished job status
        mock_redis_client.redis.hgetall.return_value = {b"job_status": b"finished", b"job_exit_code": b"0"}

        status_tracker = SessionStatusTracker(mock_redis_client)
        job_status = status_tracker.get_job_status("test_session")
        self.assertEqual(job_status, "finished")

    def test_mark_job_finished_script_exists(self):
        """Test that mark_job_finished.py script exists"""
        script_path = Path(__file__).parent.parent / "scripts" / "mark_job_finished.py"
        self.assertTrue(script_path.exists(), f"Script not found at {script_path}")
        self.assertTrue(script_path.is_file(), f"Path is not a file: {script_path}")

    def test_job_status_vs_session_status_distinction(self):
        """Test that job status and session status are properly distinguished"""
        mock_redis_client = Mock(spec=DestoRedisClient)
        mock_redis_client.redis = Mock()
        mock_redis_client.get_session_key.return_value = "desto:session:test"

        # Test case: Session running but job finished (keep-alive scenario)
        mock_redis_client.redis.hgetall.return_value = {
            b"session_name": b"test_session",
            b"status": b"running",  # Session still running (keep-alive)
            b"job_status": b"finished",  # Job completed
            b"job_exit_code": b"0",
        }

        status_tracker = SessionStatusTracker(mock_redis_client)
        job_status = status_tracker.get_job_status("test_session")

        # Should return job status, not session status
        self.assertEqual(job_status, "finished")

    def test_log_section_message_rotation(self):
        """Test that log messages are properly rotated"""
        log_section = LogSection()

        # Add more than 20 messages (default limit)
        for i in range(25):
            log_section.update_log_messages(f"Message {i}")

        # Should keep only last 20
        self.assertEqual(len(log_section.log_messages), 20)
        self.assertEqual(log_section.log_messages[0], "Message 5")  # First 5 dropped
        self.assertEqual(log_section.log_messages[-1], "Message 24")  # Last one kept

    def test_redis_error_handling(self):
        """Test that Redis errors are handled gracefully"""
        mock_redis_client = Mock(spec=DestoRedisClient)
        mock_redis_client.redis = Mock()
        mock_redis_client.get_session_key.return_value = "desto:session:test"

        # Simulate Redis connection error
        mock_redis_client.redis.hgetall.side_effect = Exception("Redis connection failed")

        status_tracker = SessionStatusTracker(mock_redis_client)
        job_status = status_tracker.get_job_status("test_session")

        # Should return "unknown" instead of crashing
        self.assertEqual(job_status, "unknown")


if __name__ == "__main__":
    print("Running core regression tests...")
    print("=" * 50)

    unittest.main(verbosity=2, exit=False)

    print("=" * 50)
    print("Core regression tests completed!")
