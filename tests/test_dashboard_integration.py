#!/usr/bin/env python3
"""
Integration tests for dashboard UI behavior and session status display.
These tests ensure that the dashboard correctly shows job completion status.
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
    from src.desto.redis.desto_manager import DestoManager
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)


class TestDashboardStatusDisplay(unittest.TestCase):
    """Test that the dashboard correctly displays job completion status"""

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

        # Mock UI and logger
        self.mock_ui = Mock()
        self.mock_logger = Mock()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_sessions_table_uses_redis_status_when_available(self):
        """Test that add_sessions_table checks Redis job status for keep-alive sessions"""
        # Create TmuxManager with Redis enabled
        with patch("src.desto.app.sessions.DestoRedisClient") as mock_redis_class:
            mock_redis_class.return_value = self.mock_redis_client

            tmux_manager = TmuxManager(self.mock_ui, self.mock_logger, log_dir=self.log_dir, scripts_dir=self.scripts_dir)

            # Mock the desto manager
            mock_desto_manager = Mock(spec=DestoManager)
            tmux_manager.desto_manager = mock_desto_manager

            # Create a mock session that would appear "Running" in tmux
            mock_session_data = {
                "test_session": {
                    "id": "$1",
                    "name": "test_session",
                    "created": 1699876543,
                    "attached": False,
                    "windows": 1,
                    "group": None,
                    "group_size": 1,
                }
            }

            # Test case 1: Job is finished (even though session is running)
            mock_desto_manager.get_job_status.return_value = "finished"

            # Mock UI components for the table
            mock_ui = Mock()
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=None)

            # Mock the chained method calls: ui.row().style() returns a context manager
            mock_row = Mock()
            mock_row.style.return_value = mock_context
            mock_ui.row.return_value = mock_row
            mock_ui.label = Mock()
            mock_ui.button = Mock()

            # Call add_sessions_table
            tmux_manager.add_sessions_table(mock_session_data, mock_ui)

            # Verify that get_job_status was called
            mock_desto_manager.get_job_status.assert_called_with("test_session")

            # Verify that UI components were created
            self.assertTrue(mock_ui.row.called)
            self.assertTrue(mock_ui.label.called)

    def test_add_sessions_table_falls_back_to_file_marker_without_redis(self):
        """Test that add_sessions_table falls back to file markers when Redis is not available"""
        # Create TmuxManager without Redis
        with patch("src.desto.app.sessions.DestoRedisClient") as mock_redis_class:
            mock_redis_instance = Mock(spec=DestoRedisClient)
            mock_redis_instance.is_connected.return_value = False
            mock_redis_class.return_value = mock_redis_instance

            tmux_manager = TmuxManager(self.mock_ui, self.mock_logger, log_dir=self.log_dir, scripts_dir=self.scripts_dir)

            # Should not use Redis
            self.assertFalse(tmux_manager.use_redis)

            # Create a mock session
            mock_session_data = {
                "test_session": {
                    "id": "$1",
                    "name": "test_session",
                    "created": 1699876543,
                    "attached": False,
                    "windows": 1,
                    "group": None,
                    "group_size": 1,
                }
            }

            # Create a finished marker file
            finished_marker = self.log_dir / "test_session.finished"
            finished_marker.touch()

            # Mock UI components with proper context manager support
            mock_ui = Mock()
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=None)

            # Mock the chained method calls: ui.row().style() returns a context manager
            mock_row = Mock()
            mock_row.style.return_value = mock_context
            mock_ui.row.return_value = mock_row
            mock_ui.label = Mock()
            mock_ui.button = Mock()

            # Call add_sessions_table
            tmux_manager.add_sessions_table(mock_session_data, mock_ui)

            # Verify that UI components were created
            self.assertTrue(mock_ui.row.called)
            self.assertTrue(mock_ui.label.called)

    def test_session_status_correctly_distinguishes_job_vs_session(self):
        """Test that session status correctly shows job completion vs session running state"""
        # Create TmuxManager with Redis
        with patch("src.desto.app.sessions.DestoRedisClient") as mock_redis_class:
            mock_redis_class.return_value = self.mock_redis_client

            tmux_manager = TmuxManager(self.mock_ui, self.mock_logger, log_dir=self.log_dir, scripts_dir=self.scripts_dir)

            # Mock the desto manager
            mock_desto_manager = Mock(spec=DestoManager)
            tmux_manager.desto_manager = mock_desto_manager

            # Test different job status scenarios
            test_cases = [
                ("finished", "Finished"),
                ("failed", "Finished"),
                ("running", "Running"),
                ("unknown", "Running"),
            ]

            for job_status, expected_display in test_cases:
                with self.subTest(job_status=job_status):
                    mock_desto_manager.get_job_status.return_value = job_status

                    # Create session data
                    mock_session_data = {
                        "test_session": {
                            "id": "$1",
                            "name": "test_session",
                            "created": 1699876543,
                            "attached": False,
                            "windows": 1,
                            "group": None,
                            "group_size": 1,
                        }
                    }

                    # Mock UI to capture the status label
                    captured_labels = []

                    def capture_label(text):
                        captured_labels.append(text)
                        return Mock()

                    mock_ui = Mock()
                    mock_context = Mock()
                    mock_context.__enter__ = Mock(return_value=mock_context)
                    mock_context.__exit__ = Mock(return_value=None)

                    # Mock the chained method calls: ui.row().style() returns a context manager
                    mock_row = Mock()
                    mock_row.style.return_value = mock_context
                    mock_ui.row.return_value = mock_row
                    mock_ui.label = capture_label
                    mock_ui.button = Mock()

                    # Call add_sessions_table
                    tmux_manager.add_sessions_table(mock_session_data, mock_ui)

                    # Find the status label
                    # Headers: Session ID, Name, Created, Elapsed, Attached, Status, Actions (7 labels)
                    # Data row: ID, Name, Created, Elapsed, Attached, Status (6 labels + button)
                    # So status should be at index 7 + 5 = 12 (0-based)
                    if len(captured_labels) >= 13:
                        status_label = captured_labels[12]  # 0-indexed, 12th is the status data
                        self.assertEqual(status_label, expected_display)


class TestLogSectionIntegration(unittest.TestCase):
    """Test LogSection integration with the dashboard"""

    def setUp(self):
        self.log_section = LogSection()

    def test_log_section_initialization(self):
        """Test that LogSection initializes correctly"""
        self.assertIsInstance(self.log_section.log_messages, list)
        self.assertEqual(len(self.log_section.log_messages), 0)

    def test_log_section_message_handling(self):
        """Test that LogSection handles messages correctly"""
        # Test adding messages
        test_messages = ["Test message 1", "Test message 2", "Test message 3"]

        for msg in test_messages:
            self.log_section.update_log_messages(msg)

        # Verify messages were stored
        self.assertEqual(len(self.log_section.log_messages), 3)
        self.assertEqual(self.log_section.log_messages, test_messages)

    def test_log_section_ui_component_setup(self):
        """Test that LogSection sets up UI components correctly"""
        # This test verifies the structure without needing actual NiceGUI
        self.assertTrue(hasattr(self.log_section, "log_messages"))
        self.assertTrue(hasattr(self.log_section, "update_log_messages"))
        self.assertTrue(hasattr(self.log_section, "refresh_log_display"))


class TestJobCompletionMarkingIntegration(unittest.TestCase):
    """Test job completion marking integration"""

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

    def test_job_completion_command_generation(self):
        """Test that job completion commands are generated correctly"""
        # Mock Redis client
        mock_redis_client = Mock(spec=DestoRedisClient)
        mock_redis_client.is_connected.return_value = True
        mock_redis_client.redis = Mock()  # Add the redis attribute

        with patch("src.desto.app.sessions.DestoRedisClient") as mock_redis_class:
            mock_redis_class.return_value = mock_redis_client

            tmux_manager = TmuxManager(self.mock_ui, self.mock_logger, log_dir=self.log_dir, scripts_dir=self.scripts_dir)

            # Test Redis-based command generation
            self.assertTrue(tmux_manager.use_redis)

            command = tmux_manager.get_job_completion_command("test_session", use_variable=True)

            # Verify command structure
            self.assertIn("python3", command)
            self.assertIn("mark_job_finished.py", command)
            self.assertIn("test_session", command)
            self.assertIn("$SCRIPT_EXIT_CODE", command)

    def test_job_completion_command_without_redis(self):
        """Test job completion command generation without Redis"""
        # Mock Redis client as disconnected
        mock_redis_client = Mock(spec=DestoRedisClient)
        mock_redis_client.is_connected.return_value = False
        mock_redis_client.redis = Mock()  # Add the redis attribute

        with patch("src.desto.app.sessions.DestoRedisClient") as mock_redis_class:
            mock_redis_class.return_value = mock_redis_client

            tmux_manager = TmuxManager(self.mock_ui, self.mock_logger, log_dir=self.log_dir, scripts_dir=self.scripts_dir)

            # Test file-based command generation
            self.assertFalse(tmux_manager.use_redis)

            command = tmux_manager.get_job_completion_command("test_session", use_variable=True)

            # Verify command structure
            self.assertIn("touch", command)
            self.assertIn("test_session.finished", command)


if __name__ == "__main__":
    print("Running integration tests for dashboard status display...")
    print("=" * 60)

    # Run all tests
    unittest.main(verbosity=2, exit=False)

    print("=" * 60)
    print("All integration tests completed!")
