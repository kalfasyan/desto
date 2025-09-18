#!/usr/bin/env python3
"""Unit tests for duplicate session validation."""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.desto.app.sessions import TmuxManager

pytestmark = pytest.mark.skipif(os.getenv("CI") == "true", reason="Redis is not available on GitHub Actions")


class TestDuplicateSessionValidation:
    """Test duplicate session validation functionality."""

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

    @pytest.fixture
    def tmux_manager(self, temp_dirs):
        """Create a TmuxManager instance for testing."""
        mock_ui = Mock()
        mock_logger = Mock()

        # Patch Redis to be available since it's now required
        with patch("src.desto.app.sessions.DestoRedisClient") as mock_redis_class:
            mock_redis_instance = Mock()
            mock_redis_instance.is_connected.return_value = True
            mock_redis_class.return_value = mock_redis_instance

            # Also need to mock the DestoManager
            with patch("src.desto.app.sessions.DestoManager") as mock_desto_manager_class:
                mock_desto_manager = Mock()
                # Configure the mock to return the expected tuple format
                mock_session = Mock()
                mock_job = Mock()
                mock_desto_manager.start_session_with_job.return_value = (mock_session, mock_job)
                mock_desto_manager_class.return_value = mock_desto_manager

                # Mock PubSub
                with patch("src.desto.app.sessions.SessionPubSub") as mock_pubsub_class:
                    mock_pubsub = Mock()
                    mock_pubsub_class.return_value = mock_pubsub

                    tmux_manager = TmuxManager(mock_ui, mock_logger, log_dir=temp_dirs["log_dir"], scripts_dir=temp_dirs["scripts_dir"])

                    return tmux_manager

    @pytest.mark.skipif(not subprocess.run(["tmux", "-V"], capture_output=True).returncode == 0, reason="tmux not available")
    def test_duplicate_session_validation(self, tmux_manager, temp_dirs):
        """Test that duplicate session validation prevents creating sessions with same name."""
        session_name = "test_duplicate_session"

        # Mock ui.notification to avoid import issues
        with patch("src.desto.app.sessions.ui.notification") as mock_notification:
            # Patch list_all_sessions to return a list
            with patch.object(tmux_manager.desto_manager.session_manager, "list_all_sessions", return_value=[]):
                # Start first session
                tmux_manager.start_tmux_session(session_name, "sleep 3", Mock())

                # Wait for session to start
                time.sleep(1)

                # Verify the session exists
                sessions = tmux_manager.check_sessions()
                assert session_name in sessions, "First session should be created successfully"

                # Attempt to start duplicate session
                tmux_manager.start_tmux_session(session_name, "sleep 3", Mock())

                # Check that error was logged
                # Note: We can't easily check mock_logger.error since it's created in the fixture
                # But we can check that negative notification was called
                negative_calls = [call for call in mock_notification.call_args_list if call[1].get("type") == "negative"]
                assert len(negative_calls) > 0, "Negative notification should be called for duplicate session"

                # Check the error message
                notification_message = negative_calls[0][0][0]
                assert "already exists" in notification_message, f"Error message should mention 'already exists': {notification_message}"
                assert session_name in notification_message, f"Error message should mention session name: {notification_message}"

                # Clean up
                try:
                    subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True, check=False)
                except Exception:
                    pass

    @pytest.mark.skipif(not subprocess.run(["tmux", "-V"], capture_output=True).returncode == 0, reason="tmux not available")
    def test_duplicate_session_validation_with_chain(self, tmux_manager, temp_dirs):
        """Test that duplicate session validation works with chained scripts."""
        session_name = "test_chain_duplicate"

        # Create a test script that runs longer
        test_script = temp_dirs["scripts_dir"] / "test_script.sh"
        test_script.write_text("#!/bin/bash\necho 'Test script started'\nsleep 5\necho 'Test script finished'\n")
        test_script.chmod(0o755)

        # Mock ui.notification to avoid import issues
        with patch("src.desto.app.sessions.ui.notification") as mock_notification:
            # Patch list_all_sessions to return a list
            with patch.object(tmux_manager.desto_manager.session_manager, "list_all_sessions", return_value=[]):
                # Start first session (simulating a chain)
                chain_command = f"echo '---- Running test_script.sh ----' && bash '{test_script}'"
                tmux_manager.start_tmux_session(session_name, chain_command, Mock())

                # Wait for session to start
                time.sleep(2)

                # Verify the session exists
                sessions = tmux_manager.check_sessions()
                assert session_name in sessions, "First chain session should be created successfully"

                # Attempt to start another chain with the same session name
                chain_command2 = f"echo '---- Running test_script.sh ----' && bash '{test_script}'"
                tmux_manager.start_tmux_session(session_name, chain_command2, Mock())

                # Check that duplicate session validation triggered
                negative_calls = [call for call in mock_notification.call_args_list if call[1].get("type") == "negative"]
                assert len(negative_calls) > 0, "Negative notification should be called for duplicate chain session"

                # Check the error message
                notification_message = negative_calls[0][0][0]
                assert "already exists" in notification_message, f"Error message should mention 'already exists': {notification_message}"
                assert session_name in notification_message, f"Error message should mention session name: {notification_message}"

                # Clean up
                try:
                    subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True, check=False)
                except Exception:
                    pass

    def test_non_duplicate_session_allowed(self, tmux_manager):
        """Test that non-duplicate sessions are allowed."""
        session_name1 = "test_session_1"
        session_name2 = "test_session_2"

        # Mock ui.notification and check_sessions
        with patch("src.desto.app.sessions.ui.notification") as mock_notification:
            with patch.object(tmux_manager, "check_sessions") as mock_check_sessions:
                # Mock that no sessions exist initially
                mock_check_sessions.return_value = {}
                # Patch list_all_sessions to return a list
                with patch.object(tmux_manager.desto_manager.session_manager, "list_all_sessions", return_value=[]):
                    # Mock subprocess.run to simulate successful tmux session creation
                    with patch("src.desto.app.sessions.subprocess.run") as mock_subprocess:
                        mock_subprocess.return_value.returncode = 0

                        # Start first session
                        tmux_manager.start_tmux_session(session_name1, "echo 'test1'", Mock())

                        # Check that positive notification was called
                        positive_calls = [call for call in mock_notification.call_args_list if call[1].get("type") == "positive"]
                        assert len(positive_calls) > 0, "Positive notification should be called for successful session start"

                        # Reset mock
                        mock_notification.reset_mock()

                        # Start second session (different name)
                        tmux_manager.start_tmux_session(session_name2, "echo 'test2'", Mock())

                        # Check that positive notification was called again
                        positive_calls = [call for call in mock_notification.call_args_list if call[1].get("type") == "positive"]
                        assert len(positive_calls) > 0, "Positive notification should be called for second successful session start"

                        # Check that no negative notifications were called
                        negative_calls = [call for call in mock_notification.call_args_list if call[1].get("type") == "negative"]
                        assert len(negative_calls) == 0, "No negative notifications should be called for non-duplicate sessions"
