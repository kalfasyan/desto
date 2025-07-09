#!/usr/bin/env python3
"""
Comprehensive test for verifying the chain logging fixes in the desto app.
This test verifies that when scripts are chained, all scripts log to the same log file correctly.
"""

import os
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest

from desto.app.sessions import TmuxManager
from desto.app.ui import UserInterfaceManager


class TestChainLoggingFixed:
    """Test suite for the fixed chain logging functionality."""

    @pytest.fixture
    def temp_env(self, tmp_path):
        """Create temporary environment for testing."""
        scripts_dir = tmp_path / "scripts"
        logs_dir = tmp_path / "logs"
        scripts_dir.mkdir()
        logs_dir.mkdir()

        # Create test scripts
        script1 = scripts_dir / "script1.sh"
        script1.write_text("""#!/bin/bash
echo "Script 1 starting"
echo "Script 1 output line 1"
echo "Script 1 output line 2"
echo "Script 1 finished"
""")
        script1.chmod(0o755)

        script2 = scripts_dir / "script2.py"
        script2.write_text("""#!/usr/bin/env python3
print("Script 2 starting")
print("Script 2 output line 1")
print("Script 2 output line 2")
print("Script 2 finished")
""")
        script2.chmod(0o755)

        script3 = scripts_dir / "script3.sh"
        script3.write_text("""#!/bin/bash
echo "Script 3 starting"
echo "Script 3 output line 1"
echo "Script 3 output line 2"
echo "Script 3 finished"
""")
        script3.chmod(0o755)

        return {
            "scripts_dir": scripts_dir,
            "logs_dir": logs_dir,
            "script1": script1,
            "script2": script2,
            "script3": script3,
        }

    def test_fixed_chain_logging_structure(self, temp_env):
        """Test that the fixed logging structure properly captures all chain output."""
        mock_ui = MagicMock()
        mock_logger = MagicMock()

        tmux_manager = TmuxManager(mock_ui, mock_logger, log_dir=temp_env["logs_dir"], scripts_dir=temp_env["scripts_dir"])

        session_name = "test_fixed_chain"

        # Create a chain command like the app does
        chain_cmd = (
            f"echo '---- Running script1.sh ----' && "
            f"bash {temp_env['script1']} && "
            f"echo '---- Running script2.py ----' && "
            f"python3 {temp_env['script2']} && "
            f"echo '---- Running script3.sh ----' && "
            f"bash {temp_env['script3']}"
        )

        # Mock subprocess to capture the tmux command
        with patch("desto.app.sessions.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0

            with patch("desto.app.sessions.ui.notification"):
                tmux_manager.start_tmux_session(session_name, chain_cmd, mock_logger, False)

        # Verify subprocess was called
        assert mock_run.called
        call_args = mock_run.call_args

        # Extract the full tmux command
        tmux_args = call_args[0][0]
        full_command = tmux_args[7]  # The bash command (after bash -c)

        # Verify the command uses parentheses for proper grouping
        assert f"({chain_cmd})" in full_command

        # Verify it uses printf instead of echo -e
        assert "printf" in full_command
        assert "echo -e" not in full_command

        # Verify proper logging structure
        assert "=== SCRIPT STARTING at" in full_command
        assert "=== SCRIPT FINISHED at" in full_command

    def test_chain_logging_manual_execution(self, temp_env):
        """Test chain logging with manual command execution to verify it works."""
        session_name = "manual_chain_test"
        log_file = temp_env["logs_dir"] / f"{session_name}.log"

        # Build the chain command
        chain_cmd = (
            f"echo '---- Running script1.sh ----' && "
            f"bash {temp_env['script1']} && "
            f"echo '---- Running script2.py ----' && "
            f"python3 {temp_env['script2']}"
        )

        # Use the fixed logging structure
        full_cmd = (
            f'printf "\\n=== SCRIPT STARTING at %s ===\\n" "$(date)" > \'{log_file}\' && '
            f"({chain_cmd}) >> '{log_file}' 2>&1 && "
            f'printf "\\n=== SCRIPT FINISHED at %s ===\\n" "$(date)" >> \'{log_file}\' && '
            f"touch '{temp_env['logs_dir']}/{session_name}.finished'"
        )

        # Execute the command
        result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)

        assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"
        assert log_file.exists(), "Log file should exist"

        content = log_file.read_text()

        # Verify ALL script outputs are captured in the SAME log file
        assert "=== SCRIPT STARTING at" in content
        assert "=== SCRIPT FINISHED at" in content

        # Verify script 1 output
        assert "---- Running script1.sh ----" in content
        assert "Script 1 starting" in content
        assert "Script 1 output line 1" in content
        assert "Script 1 output line 2" in content
        assert "Script 1 finished" in content

        # Verify script 2 output
        assert "---- Running script2.py ----" in content
        assert "Script 2 starting" in content
        assert "Script 2 output line 1" in content
        assert "Script 2 output line 2" in content
        assert "Script 2 finished" in content

        # Verify finished marker exists
        finished_file = temp_env["logs_dir"] / f"{session_name}.finished"
        assert finished_file.exists(), "Finished marker should exist"

    @pytest.mark.skipif(not os.system("tmux -V > /dev/null 2>&1") == 0, reason="tmux not available")
    def test_tmux_integration_fixed_chain_logging(self, temp_env):
        """Integration test with real tmux to verify chain logging works end-to-end."""
        mock_ui = MagicMock()
        mock_logger = MagicMock()

        tmux_manager = TmuxManager(mock_ui, mock_logger, log_dir=temp_env["logs_dir"], scripts_dir=temp_env["scripts_dir"])

        session_name = "tmux_integration_chain"

        # Create a realistic chain command
        chain_cmd = (
            f"echo '---- Running script1.sh ----' && bash {temp_env['script1']} && echo '---- Running script3.sh ----' && bash {temp_env['script3']}"
        )

        # Start the session with patched notifications
        with patch("desto.app.sessions.ui.notification"):
            tmux_manager.start_tmux_session(session_name, chain_cmd, mock_logger, False)

        # Wait for completion
        time.sleep(3)

        # Verify results
        log_file = temp_env["logs_dir"] / f"{session_name}.log"
        finished_file = temp_env["logs_dir"] / f"{session_name}.finished"

        assert log_file.exists(), f"Log file {log_file} should exist"
        assert finished_file.exists(), f"Finished marker {finished_file} should exist"

        content = log_file.read_text()

        # The key test: verify that ALL scripts logged to the SAME file
        assert "Script 1 starting" in content, "Script 1 output should be in log"
        assert "Script 1 finished" in content, "Script 1 completion should be in log"
        assert "Script 3 starting" in content, "Script 3 output should be in log"
        assert "Script 3 finished" in content, "Script 3 completion should be in log"
        assert "---- Running script1.sh ----" in content, "Script separators should be in log"
        assert "---- Running script3.sh ----" in content, "Script separators should be in log"

        # Verify proper logging timestamps
        assert "=== SCRIPT STARTING at" in content
        assert "=== SCRIPT FINISHED at" in content

        # Clean up
        try:
            subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True, check=False)
        except Exception:
            pass

    def test_ui_manager_build_logging_command_fixed(self, temp_env):
        """Test that the UI manager's build_logging_command method produces correct output."""
        mock_ui = MagicMock()
        mock_settings = {"script_settings": {"supported_extensions": [".sh", ".py"]}}
        mock_tmux = MagicMock()
        mock_tmux.LOG_DIR = temp_env["logs_dir"]

        ui_manager = UserInterfaceManager(mock_ui, mock_settings, mock_tmux)

        log_file_path = temp_env["logs_dir"] / "test.log"
        info_block = "# Test session\\n# User: test"
        exec_cmd = "echo 'test1' && echo 'test2' && echo 'test3'"
        finished_marker_cmd = "touch /tmp/test.finished"

        # Build the logging command using the fixed method
        logging_cmd = ui_manager.build_logging_command(log_file_path, info_block, exec_cmd, finished_marker_cmd, keep_alive=False)

        # Verify the command uses parentheses for grouping
        assert f"({exec_cmd})" in logging_cmd, "Execution command should be grouped in parentheses"

        # Verify it uses printf instead of echo -e
        assert "printf" in logging_cmd, "Should use printf for shell compatibility"
        assert "echo -e" not in logging_cmd, "Should not use echo -e"

        # Test manual execution to verify it works
        result = subprocess.run(logging_cmd, shell=True, capture_output=True, text=True)
        assert result.returncode == 0, f"Logging command failed: {result.stderr}"

        if log_file_path.exists():
            content = log_file_path.read_text()
            # Verify all commands in the chain are logged
            assert "test1" in content
            assert "test2" in content
            assert "test3" in content
            assert "=== SCRIPT STARTING at" in content
            assert "=== SCRIPT FINISHED at" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
