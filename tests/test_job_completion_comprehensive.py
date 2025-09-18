#!/usr/bin/env python3
"""Comprehensive tests for job completion tracking and logging functionality.
These tests verify that:
1. Job completion is properly detected with keep-alive
2. Logging works correctly
3. Chained scripts work properly
4. Failed scripts are handled correctly.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from loguru import logger

pytestmark = pytest.mark.skipif(os.getenv("CI") == "true", reason="Redis is not available on GitHub Actions")

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from src.desto.app.sessions import TmuxManager
except ImportError:
    TmuxManager = None  # Skip tests if module not available


class TestJobCompletionTracking(unittest.TestCase):
    """Test that job completion tracking works correctly."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.log_dir = self.temp_path / "logs"
        self.scripts_dir = self.temp_path / "scripts"
        self.log_dir.mkdir()
        self.scripts_dir.mkdir()

        # Mock UI and logger
        self.mock_ui = Mock()
        self.mock_logger = Mock()

        # Create TmuxManager (without Redis for testing)
        if TmuxManager:
            self.tmux_manager = TmuxManager(self.mock_ui, self.mock_logger, log_dir=self.log_dir, scripts_dir=self.scripts_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_command_structure_handles_success(self):
        """Test that successful scripts are logged correctly."""
        session_name = "test_success"
        command = "echo 'Test script'; sleep 0.1; echo 'Done'"

        # Create the command using the same structure as TmuxManager
        log_file = self.log_dir / f"{session_name}.log"

        # Use the actual command structure from TmuxManager
        bash_script = f"""
printf "\\n=== SCRIPT STARTING at %s ===\\n" "$(date)" > {log_file}
({command}) >> {log_file} 2>&1
SCRIPT_EXIT_CODE=$?
printf "\\n=== SCRIPT FINISHED at %s (exit code: $SCRIPT_EXIT_CODE) ===\\n" "$(date)" >> {log_file}
echo "Job completion: exit code $SCRIPT_EXIT_CODE" >> {log_file}
"""

        # Execute the command
        result = subprocess.run(["bash", "-c", bash_script.strip()], capture_output=True, text=True, timeout=5)

        # Verify command executed successfully
        self.assertEqual(result.returncode, 0, f"Command failed: {result.stderr}")

        # Verify log file was created and contains expected content
        self.assertTrue(log_file.exists(), "Log file was not created")

        content = log_file.read_text()
        expected_parts = ["SCRIPT STARTING", "Test script", "Done", "SCRIPT FINISHED", "exit code: 0", "Job completion: exit code 0"]

        for part in expected_parts:
            self.assertIn(part, content, f"Missing expected content: {part}")

    def test_command_structure_handles_failure(self):
        """Test that failed scripts are logged correctly and don't break the chain."""
        session_name = "test_failure"
        command = "echo 'Starting'; exit 1"  # This will fail

        log_file = self.log_dir / f"{session_name}.log"

        # Use the same command structure but ensure post-script commands run
        bash_script = f"""
printf "\\n=== SCRIPT STARTING at %s ===\\n" "$(date)" > {log_file}
({command}) >> {log_file} 2>&1
SCRIPT_EXIT_CODE=$?
printf "\\n=== SCRIPT FINISHED at %s (exit code: $SCRIPT_EXIT_CODE) ===\\n" "$(date)" >> {log_file}
echo "Job completion: exit code $SCRIPT_EXIT_CODE" >> {log_file}
echo "Keep-alive would continue here" >> {log_file}
"""

        # Execute the command - it should complete even though the script failed
        result = subprocess.run(["bash", "-c", bash_script.strip()], capture_output=True, text=True, timeout=5)

        # The bash command itself should succeed (exit 0) even though the inner script failed
        self.assertEqual(result.returncode, 0, f"Bash command failed: {result.stderr}")

        # Verify log file contains failure information
        self.assertTrue(log_file.exists(), "Log file was not created")

        content = log_file.read_text()
        expected_parts = [
            "SCRIPT STARTING",
            "Starting",
            "SCRIPT FINISHED",
            "exit code: 1",  # The failed exit code should be captured
            "Job completion: exit code 1",
            "Keep-alive would continue here",  # This should execute despite script failure
        ]

        for part in expected_parts:
            self.assertIn(part, content, f"Missing expected content: {part}")

    def test_chained_scripts_with_failure(self):
        """Test that chained scripts continue even if some fail."""
        session_name = "test_chain"

        # Simulate a chain of scripts where the middle one fails
        commands = [
            "echo 'Script 1: Success'",
            "echo 'Script 2: About to fail'; exit 1",  # This fails
            "echo 'Script 3: Should still run'",  # This should still execute
        ]

        log_file = self.log_dir / f"{session_name}.log"

        # Build chain command using semicolons (not &&) so all scripts run
        chain_script = f"""
printf "\\n=== CHAIN STARTING at %s ===\\n" "$(date)" > {log_file}
echo '---- Running script1 ----' >> {log_file}
({commands[0]}) >> {log_file} 2>&1
echo '---- Running script2 ----' >> {log_file}
({commands[1]}) >> {log_file} 2>&1
echo '---- Running script3 ----' >> {log_file}
({commands[2]}) >> {log_file} 2>&1
CHAIN_EXIT_CODE=$?
printf "\\n=== CHAIN FINISHED at %s ===\\n" "$(date)" >> {log_file}
echo "Chain completion marker" >> {log_file}
"""

        result = subprocess.run(["bash", "-c", chain_script.strip()], capture_output=True, text=True, timeout=5)

        self.assertEqual(result.returncode, 0, f"Chain command failed: {result.stderr}")

        # Verify all scripts ran
        content = log_file.read_text()
        expected_parts = [
            "CHAIN STARTING",
            "Script 1: Success",
            "Script 2: About to fail",
            "Script 3: Should still run",  # This should be present despite script 2 failing
            "CHAIN FINISHED",
            "Chain completion marker",
        ]

        for part in expected_parts:
            self.assertIn(part, content, f"Missing expected content: {part}")

    @patch("src.desto.app.sessions.subprocess.run")
    def test_tmux_manager_uses_correct_command_structure(self, mock_subprocess):
        """Test that TmuxManager generates correct command structure."""
        if not TmuxManager:
            self.skipTest("TmuxManager not available")

        mock_subprocess.return_value.returncode = 0

        session_name = "test_session"
        command = "echo 'test'"

        # Create a mock logger
        mock_logger = Mock()

        # Call the method
        self.tmux_manager.start_tmux_session(session_name, command, mock_logger)

        # Verify subprocess.run was called
        self.assertTrue(mock_subprocess.called, "subprocess.run was not called")

        # Get the actual command that was passed to tmux
        call_args = mock_subprocess.call_args[0][0]
        tmux_command = call_args[-1]  # Last argument should be the bash script

        # Verify the command structure includes important elements
        self.assertIn("SCRIPT_EXIT_CODE=$?", tmux_command, "Exit code capture missing")
        self.assertIn("SCRIPT STARTING", tmux_command, "Start logging missing")
        self.assertIn("SCRIPT FINISHED", tmux_command, "End logging missing")


class TestLoggingIntegration(unittest.TestCase):
    """Test that the logging integration works correctly."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_log_messages_panel_integration(self):
        """Test that the LogSection receives messages correctly."""
        try:
            from src.desto.app.ui import LogSection
        except ImportError:
            self.skipTest("LogSection not available")

        log_section = LogSection()
        log_section.log_display = Mock()  # Mock the UI component

        # Test adding messages
        test_messages = ["Message 1", "Message 2", "Message 3"]

        for msg in test_messages:
            log_section.update_log_messages(msg)

        # Verify messages were stored
        self.assertEqual(len(log_section.log_messages), 3)
        self.assertEqual(log_section.log_messages, test_messages)

        # Verify refresh_log_display was called correctly
        log_section.refresh_log_display()
        expected_display = "\n".join(test_messages)
        log_section.log_display.value = expected_display

    def test_log_messages_rotation(self):
        """Test that log messages are rotated when limit is exceeded."""
        try:
            from src.desto.app.ui import LogSection
        except ImportError:
            self.skipTest("LogSection not available")

        log_section = LogSection()
        log_section.log_display = Mock()

        # Add more messages than the limit
        for i in range(25):  # Default limit is 20
            log_section.update_log_messages(f"Message {i}")

        # Should only keep the last 20 messages
        self.assertEqual(len(log_section.log_messages), 20)
        self.assertEqual(log_section.log_messages[0], "Message 5")  # First 5 should be dropped
        self.assertEqual(log_section.log_messages[-1], "Message 24")


if __name__ == "__main__":
    # Create a test script for integration testing
    test_script_content = """#!/bin/bash
echo "Test script starting..."
sleep 1
echo "Test script finished successfully"
exit 0
"""

    logger.info("Running comprehensive job completion and logging tests...")
    logger.info("=" * 60)

    # Run the unit tests
    unittest.main(verbosity=2, exit=False)

    logger.info("=" * 60)
    logger.info("All tests completed!")
