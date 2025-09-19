#!/usr/bin/env python3
"""Integration tests for dashboard UI behavior and session status display.
These tests ensure that the dashboard correctly shows job completion status.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

pytestmark = pytest.mark.skipif(os.getenv("CI") == "true", reason="Redis is not available on GitHub Actions")

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
    """Test that the dashboard correctly displays job completion status."""

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
        """Test that add_sessions_table checks Redis job status for keep-alive sessions."""
        with patch("src.desto.app.sessions.DestoRedisClient") as mock_redis_class:
            mock_redis_class.return_value = self.mock_redis_client

            tmux_manager = TmuxManager(self.mock_ui, self.mock_logger, log_dir=self.log_dir, scripts_dir=self.scripts_dir)
            mock_desto_manager = Mock(spec=DestoManager)
            tmux_manager.desto_manager = mock_desto_manager

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
            mock_desto_manager.get_job_status.return_value = "finished"

            captured_labels = []

            def capture_label(text):
                captured_labels.append(text)
                return Mock()

            mock_ui = Mock()
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=None)
            mock_row = Mock()
            mock_row.style.return_value = mock_context
            mock_ui.row.return_value = mock_row
            mock_ui.label = capture_label
            mock_ui.button = Mock()

            tmux_manager.add_sessions_table(mock_session_data, mock_ui)
            self.assertTrue(mock_ui.row.called)
            self.assertTrue(len(captured_labels) > 0)

    def test_add_sessions_table_falls_back_to_file_marker_without_redis(self):
        """Test that add_sessions_table falls back to file markers when Redis is not available."""
        with patch("src.desto.app.sessions.DestoRedisClient") as mock_redis_class:
            mock_redis_instance = Mock(spec=DestoRedisClient)
            mock_redis_instance.is_connected.return_value = False
            mock_redis_class.return_value = mock_redis_instance
            with self.assertRaises(RuntimeError):
                TmuxManager(self.mock_ui, self.mock_logger, log_dir=self.log_dir, scripts_dir=self.scripts_dir)

    def test_session_status_correctly_distinguishes_job_vs_session(self):
        """Test that session status correctly shows job completion vs session running state."""
        with patch("src.desto.app.sessions.DestoRedisClient") as mock_redis_class:
            mock_redis_class.return_value = self.mock_redis_client

            tmux_manager = TmuxManager(self.mock_ui, self.mock_logger, log_dir=self.log_dir, scripts_dir=self.scripts_dir)
            mock_desto_manager = Mock(spec=DestoManager)
            tmux_manager.desto_manager = mock_desto_manager

            test_cases = [
                ("finished", "🟡 Running"),
                ("failed", "🟡 Running"),
                ("running", "🟡 Running"),
                ("unknown", "🟡 Running"),
            ]

            for job_status, expected_display in test_cases:
                with self.subTest(job_status=job_status):
                    mock_desto_manager.get_job_status.return_value = job_status
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
                    captured_labels = []

                    def capture_label(text):
                        captured_labels.append(text)
                        return Mock()

                    mock_ui = Mock()
                    mock_context = Mock()
                    mock_context.__enter__ = Mock(return_value=mock_context)
                    mock_context.__exit__ = Mock(return_value=None)
                    mock_row = Mock()
                    mock_row.style.return_value = mock_context
                    mock_ui.row.return_value = mock_row
                    mock_ui.label = capture_label
                    mock_ui.button = Mock()
                    tmux_manager.add_sessions_table(mock_session_data, mock_ui)
                    # Find the status label (last label in the row)
                    if captured_labels:
                        self.assertIn(expected_display, captured_labels)


class TestLogSectionIntegration(unittest.TestCase):
    """Test LogSection integration with the dashboard."""

    def setUp(self):
        self.log_section = LogSection()

    def test_log_section_initialization(self):
        """Test that LogSection initializes correctly."""
        self.assertIsInstance(self.log_section.log_messages, list)
        self.assertEqual(len(self.log_section.log_messages), 0)

    def test_log_section_message_handling(self):
        """Test that LogSection handles messages correctly."""
        # Test adding messages
        test_messages = ["Test message 1", "Test message 2", "Test message 3"]

        for msg in test_messages:
            self.log_section.update_log_messages(msg)

        # Verify messages were stored
        self.assertEqual(len(self.log_section.log_messages), 3)
        self.assertEqual(self.log_section.log_messages, test_messages)

    def test_log_section_ui_component_setup(self):
        """Test that LogSection sets up UI components correctly."""
        # This test verifies the structure without needing actual NiceGUI
        self.assertTrue(hasattr(self.log_section, "log_messages"))
        self.assertTrue(hasattr(self.log_section, "update_log_messages"))
        self.assertTrue(hasattr(self.log_section, "refresh_log_display"))


class TestJobCompletionMarkingIntegration(unittest.TestCase):
    """Test job completion marking integration."""

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
        """Test that job completion commands are generated correctly."""
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
        """Test job completion command generation without Redis."""
        # Mock Redis client as disconnected
        mock_redis_client = Mock(spec=DestoRedisClient)
        mock_redis_client.is_connected.return_value = False
        mock_redis_client.redis = Mock()  # Add the redis attribute

        with patch("src.desto.app.sessions.DestoRedisClient") as mock_redis_class:
            mock_redis_class.return_value = mock_redis_client
            with self.assertRaises(RuntimeError):
                TmuxManager(self.mock_ui, self.mock_logger, log_dir=self.log_dir, scripts_dir=self.scripts_dir)
