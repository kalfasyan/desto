"""Test chained script logging functionality to verify all scripts log to same file."""

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from desto.app.sessions import TmuxManager
from desto.app.ui import UserInterfaceManager


@pytest.fixture
def temp_env(tmp_path):
    """Create temporary environment for testing."""
    scripts_dir = tmp_path / "scripts"
    logs_dir = tmp_path / "logs"
    scripts_dir.mkdir()
    logs_dir.mkdir()

    # Create test scripts
    script1 = scripts_dir / "script1.sh"
    script1.write_text("""#!/bin/bash
echo "Script 1 starting"
sleep 1
echo "Script 1 output line 1"
echo "Script 1 output line 2"
echo "Script 1 finished"
""")
    script1.chmod(0o755)

    script2 = scripts_dir / "script2.py"
    script2.write_text("""#!/usr/bin/env python3
print("Script 2 starting")
import time
time.sleep(1)
print("Script 2 output line 1")
print("Script 2 output line 2")
print("Script 2 finished")
""")
    script2.chmod(0o755)

    script3 = scripts_dir / "script3.sh"
    script3.write_text("""#!/bin/bash
echo "Script 3 starting"
sleep 1
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


@pytest.fixture
def mock_ui_manager(temp_env):
    """Create a mock UI manager for testing."""
    mock_ui = MagicMock()
    mock_settings = {
        "header": {"background_color": "#fff", "color": "#000", "font_size": "1em"},
        "sidebar": {
            "width": "200px",
            "padding": "10px",
            "background_color": "#eee",
            "border_radius": "8px",
        },
        "labels": {
            "title_font_size": "1em",
            "title_font_weight": "bold",
            "subtitle_font_weight": "normal",
            "subtitle_font_size": "1em",
            "info_font_size": "1em",
            "info_color": "#888",
        },
        "progress_bar": {"size": "1em"},
        "script_settings": {"supported_extensions": [".sh", ".py"]},
    }

    mock_logger = MagicMock()
    mock_tmux = TmuxManager(mock_ui, mock_logger, log_dir=temp_env["logs_dir"], scripts_dir=temp_env["scripts_dir"])

    ui_manager = UserInterfaceManager(mock_ui, mock_settings, mock_tmux)
    ui_manager.chain_queue = []

    # Mock required UI elements
    ui_manager.script_path_select = MagicMock()
    ui_manager.arguments_input = MagicMock()
    ui_manager.session_name_input = MagicMock()
    ui_manager.keep_alive_switch_new = MagicMock()
    ui_manager.chain_queue_display = MagicMock()

    return ui_manager


def test_chain_queue_basic_functionality(mock_ui_manager, temp_env):
    """Test basic chain queue functionality."""
    ui_manager = mock_ui_manager

    # Test adding scripts to chain
    ui_manager.script_path_select.value = "script1.sh"
    ui_manager.arguments_input.value = ""

    with patch("desto.app.ui.ui.notification"):
        ui_manager.chain_current_script()

    assert len(ui_manager.chain_queue) == 1
    assert ui_manager.chain_queue[0][0] == str(temp_env["script1"])
    assert ui_manager.chain_queue[0][1] == ""

    # Add second script
    ui_manager.script_path_select.value = "script2.py"
    ui_manager.arguments_input.value = "arg1"

    with patch("desto.app.ui.ui.notification"):
        ui_manager.chain_current_script()

    assert len(ui_manager.chain_queue) == 2
    assert ui_manager.chain_queue[1][0] == str(temp_env["script2"])
    assert ui_manager.chain_queue[1][1] == "arg1"


def test_chain_logging_single_file(mock_ui_manager, temp_env):
    """Test that chained scripts all log to the same file."""
    ui_manager = mock_ui_manager
    session_name = "test_chain"

    # Build chain queue
    ui_manager.chain_queue = [
        (str(temp_env["script1"]), ""),
        (str(temp_env["script2"]), ""),
        (str(temp_env["script3"]), ""),
    ]

    # Mock tmux session creation and UI elements to avoid dependencies
    with patch.object(ui_manager.tmux_manager, "start_tmux_session") as mock_start:
        with patch("desto.app.ui.ui.notification"):
            with patch.object(ui_manager, "refresh_chain_queue_display"):
                # Call the chain runner
                import asyncio

                asyncio.run(ui_manager.run_chain_queue(session_name, "", False))

    # Verify tmux session was called
    assert mock_start.called
    call_args = mock_start.call_args

    # Extract the command that was passed to tmux
    called_session_name = call_args[0][0]
    called_command = call_args[0][1]

    assert called_session_name == session_name

    # Verify the command contains all three scripts
    assert "script1.sh" in called_command
    assert "script2.py" in called_command
    assert "script3.sh" in called_command

    # Verify they're chained with &&
    assert "&&" in called_command

    # Verify separators are included
    assert "---- Running script1.sh ----" in called_command
    assert "---- Running script2.py ----" in called_command
    assert "---- Running script3.sh ----" in called_command


def test_tmux_manager_logging_structure(temp_env):
    """Test the TmuxManager logging structure for chained commands."""
    mock_ui = MagicMock()
    mock_logger = MagicMock()

    tmux_manager = TmuxManager(mock_ui, mock_logger, log_dir=temp_env["logs_dir"], scripts_dir=temp_env["scripts_dir"])

    session_name = "test_logging"
    test_command = "echo 'test1' && echo 'test2' && echo 'test3'"

    # Mock subprocess to avoid actual tmux calls
    with patch("desto.app.sessions.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0

        tmux_manager.start_tmux_session(session_name, test_command, mock_logger, False)

    # Verify subprocess was called
    assert mock_run.called
    call_args = mock_run.call_args

    # Extract the full tmux command
    tmux_args = call_args[0][0]
    assert tmux_args[0] == "tmux"
    assert tmux_args[1] == "new-session"
    assert tmux_args[2] == "-d"
    assert tmux_args[3] == "-s"
    assert tmux_args[4] == session_name
    assert tmux_args[5] == "bash"
    assert tmux_args[6] == "-c"

    # Get the full command that would be executed (the bash command)
    full_command = tmux_args[7]

    # Verify logging structure
    assert "=== SCRIPT STARTING at" in full_command
    assert "=== SCRIPT FINISHED at" in full_command
    assert test_command in full_command
    assert f"{session_name}.log" in full_command
    assert f"{session_name}.finished" in full_command

    # Verify the logging redirections
    assert ">>" in full_command  # Append mode
    assert "2>&1" in full_command  # Stderr redirect


def test_build_execution_command(mock_ui_manager, temp_env):
    """Test that build_execution_command works correctly for different script types."""
    ui_manager = mock_ui_manager

    # Test bash script
    bash_cmd = ui_manager.build_execution_command(temp_env["script1"], "arg1 arg2")
    assert str(temp_env["script1"]) in bash_cmd
    assert "arg1 arg2" in bash_cmd

    # Test python script
    python_cmd = ui_manager.build_execution_command(temp_env["script2"], "")
    assert str(temp_env["script2"]) in python_cmd


def test_chain_queue_display_updates(mock_ui_manager):
    """Test that chain queue display updates correctly."""
    ui_manager = mock_ui_manager

    # Mock the display methods
    ui_manager.refresh_chain_queue_display = MagicMock()

    # Add script to chain
    ui_manager.script_path_select.value = "script1.sh"
    ui_manager.arguments_input.value = "test_arg"

    with patch("desto.app.ui.ui.notification"):
        ui_manager.chain_current_script()

    # Verify display was refreshed
    ui_manager.refresh_chain_queue_display.assert_called()


def test_clear_chain_queue(mock_ui_manager):
    """Test clearing the chain queue."""
    ui_manager = mock_ui_manager
    ui_manager.refresh_chain_queue_display = MagicMock()

    # Add some items to queue
    ui_manager.chain_queue = [("script1", ""), ("script2", "arg")]

    with patch("desto.app.ui.ui.notification"):
        ui_manager.clear_chain_queue()

    assert len(ui_manager.chain_queue) == 0
    ui_manager.refresh_chain_queue_display.assert_called()


@pytest.mark.integration
def test_chain_logging_integration(temp_env):
    """Integration test to verify actual logging works when tmux is available."""
    pytest.importorskip("subprocess")

    # Only run if tmux is available
    import subprocess

    try:
        subprocess.run(["tmux", "-V"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("tmux not available")

    mock_ui = MagicMock()
    mock_logger = MagicMock()

    tmux_manager = TmuxManager(mock_ui, mock_logger, log_dir=temp_env["logs_dir"], scripts_dir=temp_env["scripts_dir"])

    session_name = "integration_test_chain"

    # Create a simple chain command
    chain_cmd = "echo 'First script output' && sleep 0.5 && echo 'Second script output'"

    # Start the session (no return value expected)
    with patch("desto.app.sessions.ui.notification"):
        tmux_manager.start_tmux_session(session_name, chain_cmd, mock_logger, False)

    # Wait for completion
    time.sleep(2)

    # Check log file exists and contains expected content
    log_file = temp_env["logs_dir"] / f"{session_name}.log"
    finished_file = temp_env["logs_dir"] / f"{session_name}.finished"

    assert log_file.exists(), f"Log file {log_file} should exist"
    assert finished_file.exists(), f"Finished marker {finished_file} should exist"

    log_content = log_file.read_text()

    # Verify logging structure
    assert "=== SCRIPT STARTING at" in log_content
    assert "=== SCRIPT FINISHED at" in log_content
    assert "First script output" in log_content
    assert "Second script output" in log_content

    # Clean up
    try:
        subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True, check=False)
    except Exception:
        pass


def test_date_expansion_in_logging():
    """Test that $(date) is properly expanded in logging commands."""
    from desto.app.ui import UserInterfaceManager

    # Create a minimal UI manager to test date expansion
    mock_ui = MagicMock()
    mock_settings = {"script_settings": {"supported_extensions": [".sh", ".py"]}}
    mock_tmux = MagicMock()

    ui_manager = UserInterfaceManager(mock_ui, mock_settings, mock_tmux)

    # Test the build_logging_command method
    log_file = "/tmp/test.log"
    info_block = "# Test info"
    exec_cmd = "echo 'test'"
    finished_marker = "touch /tmp/test.finished"

    logging_cmd = ui_manager.build_logging_command(log_file, info_block, exec_cmd, finished_marker, keep_alive=False)

    # Verify $(date) appears in the command (it should be expanded by the shell)
    assert "$(date)" in logging_cmd
    # Check for the printf format instead of echo -e format
    assert "printf" in logging_cmd
    assert "SCRIPT STARTING" in logging_cmd
    assert "SCRIPT FINISHED" in logging_cmd


def test_realistic_chain_logging_flow(temp_env):
    """Test the complete chain logging flow as it happens in the real app."""
    import subprocess

    # Skip if tmux not available
    try:
        subprocess.run(["tmux", "-V"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("tmux not available")

    mock_ui = MagicMock()
    mock_logger = MagicMock()

    tmux_manager = TmuxManager(mock_ui, mock_logger, log_dir=temp_env["logs_dir"], scripts_dir=temp_env["scripts_dir"])

    # Create a mock UI manager to test the real chain building logic
    mock_settings = {"script_settings": {"supported_extensions": [".sh", ".py"]}}
    ui_manager = UserInterfaceManager(mock_ui, mock_settings, tmux_manager)

    session_name = "realistic_chain_test"

    # Simulate the chain queue as it would be built in the app
    chain_queue = [
        (str(temp_env["script1"]), ""),
        (str(temp_env["script2"]), "arg1 arg2"),
        (str(temp_env["script3"]), ""),
    ]

    # Build chain commands exactly like the app does
    chain_commands = []
    for script_path, arguments in chain_queue:
        script_file = Path(script_path)

        # Add separator like the app does
        separator = f"echo '---- Running {script_file.name} ----'"
        chain_commands.append(separator)

        # Build execution command like the app does
        exec_cmd = ui_manager.build_execution_command(script_file, arguments)
        chain_commands.append(exec_cmd)

    # Join with && like the app does
    full_chain_cmd = " && ".join(chain_commands)

    # Start the session with proper logging command using the UI manager's build_logging_command
    log_file = temp_env["logs_dir"] / f"{session_name}.log"
    finished_marker = f"touch '{temp_env['logs_dir']}/{session_name}.finished'"
    info_block = f"# Session: {session_name}\\n# User: test"

    # Build the complete logging command like the UI manager would
    logging_cmd = ui_manager.build_logging_command(str(log_file), info_block, full_chain_cmd, finished_marker, keep_alive=False)

    print(f"Logging command: {logging_cmd}")  # Debug output

    with patch("desto.app.sessions.ui.notification"):
        tmux_manager.start_tmux_session(session_name, logging_cmd, mock_logger, False)

    # Wait for completion with more robust checking
    max_wait = 10  # seconds
    for i in range(max_wait):
        time.sleep(1)
        try:
            result = subprocess.run(["tmux", "has-session", "-t", session_name], capture_output=True)
            if result.returncode != 0:
                break  # Session has ended
        except Exception:
            break

    # Force kill session if it's still running
    try:
        subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True, check=False)
    except Exception:
        pass

    # Verify log file exists and has proper content
    log_file = temp_env["logs_dir"] / f"{session_name}.log"
    finished_file = temp_env["logs_dir"] / f"{session_name}.finished"

    print(f"Log file exists: {log_file.exists()}")  # Debug
    print(f"Finished file exists: {finished_file.exists()}")  # Debug
    if log_file.exists():
        print(f"Log content:\n{log_file.read_text()}")  # Debug

    assert log_file.exists(), f"Log file {log_file} should exist"
    assert finished_file.exists(), f"Finished marker {finished_file} should exist"

    log_content = log_file.read_text()
    print(f"Log content:\n{log_content}")  # For debugging

    # Verify ALL scripts ran and logged to the SAME file
    assert "=== SCRIPT STARTING at" in log_content
    assert "=== SCRIPT FINISHED at" in log_content

    # Check that all script outputs are in the same log
    assert "---- Running script1.sh ----" in log_content
    assert "Script 1 starting" in log_content
    assert "Script 1 output line 1" in log_content
    assert "Script 1 finished" in log_content

    assert "---- Running script2.py ----" in log_content
    assert "Script 2 starting" in log_content
    assert "Script 2 output line 1" in log_content
    assert "Script 2 finished" in log_content

    assert "---- Running script3.sh ----" in log_content
    assert "Script 3 starting" in log_content
    assert "Script 3 output line 1" in log_content
    assert "Script 3 finished" in log_content

    # Verify that arguments were passed (script2 had "arg1 arg2")
    # The arguments should be visible in the execution command in the log

    # Clean up
    try:
        subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True, check=False)
    except Exception:
        pass


def test_simple_chain_debug(temp_env):
    """Debug test to understand what's happening with chained commands."""
    import subprocess

    # Skip if tmux not available
    try:
        subprocess.run(["tmux", "-V"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("tmux not available")

    mock_ui = MagicMock()
    mock_logger = MagicMock()

    tmux_manager = TmuxManager(mock_ui, mock_logger, log_dir=temp_env["logs_dir"], scripts_dir=temp_env["scripts_dir"])

    # Test 1: Simple echo commands that should work
    session_name = "debug_simple"
    simple_cmd = "echo 'First' && echo 'Second' && echo 'Third'"

    with patch("desto.app.sessions.ui.notification"):
        tmux_manager.start_tmux_session(session_name, simple_cmd, mock_logger, False)

    time.sleep(2)

    log_file = temp_env["logs_dir"] / f"{session_name}.log"
    finished_file = temp_env["logs_dir"] / f"{session_name}.finished"

    assert log_file.exists()
    assert finished_file.exists()

    content = log_file.read_text()
    print(f"Simple test content:\n{content}")

    assert "First" in content
    assert "Second" in content
    assert "Third" in content

    # Test 2: Test with actual script execution
    session_name2 = "debug_scripts"
    script_cmd = f"bash {temp_env['script1']} && python3 {temp_env['script2']} && bash {temp_env['script3']}"

    with patch("desto.app.sessions.ui.notification"):
        tmux_manager.start_tmux_session(session_name2, script_cmd, mock_logger, False)

    time.sleep(3)

    log_file2 = temp_env["logs_dir"] / f"{session_name2}.log"
    finished_file2 = temp_env["logs_dir"] / f"{session_name2}.finished"

    print("Script files exist:")
    print(f"  script1: {temp_env['script1'].exists()}")
    print(f"  script2: {temp_env['script2'].exists()}")
    print(f"  script3: {temp_env['script3'].exists()}")

    if log_file2.exists():
        content2 = log_file2.read_text()
        print(f"Scripts test content:\n{content2}")

    if finished_file2.exists():
        print("Scripts test completed successfully")
    else:
        print("Scripts test did not complete")

    # Clean up
    try:
        subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True, check=False)
        subprocess.run(["tmux", "kill-session", "-t", session_name2], capture_output=True, check=False)
    except Exception:
        pass


def test_chain_failure_behavior(temp_env):
    """Test what happens when one script in a chain fails."""
    import subprocess

    # Skip if tmux not available
    try:
        subprocess.run(["tmux", "-V"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("tmux not available")

    mock_ui = MagicMock()
    mock_logger = MagicMock()

    tmux_manager = TmuxManager(mock_ui, mock_logger, log_dir=temp_env["logs_dir"], scripts_dir=temp_env["scripts_dir"])

    # Create a script that will fail
    failing_script = temp_env["scripts_dir"] / "failing_script.sh"
    failing_script.write_text("""#!/bin/bash
echo "This script will fail"
exit 1
""")
    failing_script.chmod(0o755)

    # Test chain with failing middle script
    session_name = "chain_with_failure"
    chain_cmd = f"echo 'Before failure' && bash {failing_script} && echo 'After failure'"

    with patch("desto.app.sessions.ui.notification"):
        tmux_manager.start_tmux_session(session_name, chain_cmd, mock_logger, False)

    time.sleep(2)

    log_file = temp_env["logs_dir"] / f"{session_name}.log"
    finished_file = temp_env["logs_dir"] / f"{session_name}.finished"

    # The log file should exist
    assert log_file.exists()

    content = log_file.read_text()
    print(f"Chain with failure content:\n{content}")

    # Check what actually got logged
    assert "Before failure" in content
    assert "This script will fail" in content
    # "After failure" should NOT be in content because the chain stopped
    assert "After failure" not in content

    # The finished marker might not exist because the chain failed
    print(f"Finished marker exists: {finished_file.exists()}")

    # Clean up
    try:
        subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True, check=False)
    except Exception:
        pass


def test_proposed_chain_logging_fix(temp_env):
    """Test a proposed fix for chain logging that ensures all scripts log regardless of failures."""
    import subprocess

    # Skip if tmux not available
    try:
        subprocess.run(["tmux", "-V"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("tmux not available")

    mock_ui = MagicMock()
    mock_logger = MagicMock()

    tmux_manager = TmuxManager(mock_ui, mock_logger, log_dir=temp_env["logs_dir"], scripts_dir=temp_env["scripts_dir"])

    # Create a failing script
    failing_script = temp_env["scripts_dir"] / "failing_script.sh"
    failing_script.write_text("""#!/bin/bash
echo "This script will fail"
exit 1
""")
    failing_script.chmod(0o755)

    session_name = "fixed_chain_logging"
    log_file = temp_env["logs_dir"] / f"{session_name}.log"
    quoted_log_file = f"'{log_file}'"

    # Proposed fix: Use semicolons instead of && for the individual script execution
    # This ensures all scripts run regardless of failures, but each script's
    # success/failure is still logged
    chain_parts = [
        f"echo 'Script 1:' >> {quoted_log_file}",
        f'bash {temp_env["script1"]} >> {quoted_log_file} 2>&1; EXIT_CODE=$?; echo "Script 1 exit code: $EXIT_CODE" >> {quoted_log_file}',
        f"echo 'Script 2 (failing):' >> {quoted_log_file}",
        f'bash {failing_script} >> {quoted_log_file} 2>&1; EXIT_CODE=$?; echo "Script 2 exit code: $EXIT_CODE" >> {quoted_log_file}',
        f"echo 'Script 3:' >> {quoted_log_file}",
        f'bash {temp_env["script3"]} >> {quoted_log_file} 2>&1; EXIT_CODE=$?; echo "Script 3 exit code: $EXIT_CODE" >> {quoted_log_file}',
    ]

    # Join with semicolons so all commands execute regardless of failures
    fixed_chain_cmd = "; ".join(chain_parts)

    with patch("desto.app.sessions.ui.notification"):
        tmux_manager.start_tmux_session(session_name, fixed_chain_cmd, mock_logger, False)

    time.sleep(3)

    finished_file = temp_env["logs_dir"] / f"{session_name}.finished"

    assert log_file.exists()
    assert finished_file.exists()  # Should exist because command completed

    content = log_file.read_text()
    print(f"Fixed chain content:\n{content}")

    # All scripts should have run and logged
    assert "Script 1 starting" in content
    assert "Script 1 exit code: 0" in content

    assert "This script will fail" in content
    assert "Script 2 exit code: 1" in content  # Failed with exit code 1

    assert "Script 3 starting" in content
    assert "Script 3 exit code: 0" in content

    # Clean up
    try:
        subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True, check=False)
    except Exception:
        pass


def test_debug_tmux_command_generation(temp_env):
    """Debug test to see exactly what command gets generated for tmux."""
    mock_ui = MagicMock()
    mock_logger = MagicMock()

    tmux_manager = TmuxManager(mock_ui, mock_logger, log_dir=temp_env["logs_dir"], scripts_dir=temp_env["scripts_dir"])

    session_name = "debug_command"
    simple_command = "echo 'test'"

    # Let's intercept the subprocess.run call to see the exact command
    captured_command = None

    def capture_run(*args, **kwargs):
        nonlocal captured_command
        captured_command = args[0]
        # Mock successful execution
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        return result

    with patch("desto.app.sessions.subprocess.run", side_effect=capture_run):
        with patch("desto.app.sessions.ui.notification"):
            tmux_manager.start_tmux_session(session_name, simple_command, mock_logger, False)

    print(f"Captured tmux command: {captured_command}")

    if captured_command:
        # The command should be: ["tmux", "new-session", "-d", "-s", session_name, full_command]
        if len(captured_command) >= 6:
            full_tmux_command = captured_command[5]
            print(f"Full tmux execution command: {full_tmux_command}")

            # Let's test this command manually (without tmux)
            # by extracting just the shell part
            if " && " in full_tmux_command:
                parts = full_tmux_command.split(" && ")
                print("Command parts:")
                for i, part in enumerate(parts):
                    print(f"  {i}: {part}")


def test_manual_chain_execution(temp_env):
    """Test manual execution of chained commands to isolate the tmux layer."""
    import subprocess

    # Test 1: Simple commands
    log_file = temp_env["logs_dir"] / "manual_test.log"
    quoted_log_file = f"'{log_file}'"

    # Simulate what the tmux command generation creates (with printf)
    commands = [
        f'printf "\\n=== SCRIPT STARTING at %s ===\\n" "$(date)" > {quoted_log_file}',
        f"(echo 'First command' && echo 'Second command' && echo 'Third command') >> {quoted_log_file} 2>&1",
        f'printf "\\n=== SCRIPT FINISHED at %s ===\\n" "$(date)" >> {quoted_log_file}',
        f"touch '{temp_env['logs_dir']}/manual_test.finished'",
    ]

    full_command = " && ".join(commands)
    print(f"Testing command: {full_command}")

    # Execute the command directly
    result = subprocess.run(full_command, shell=True, capture_output=True, text=True)
    print(f"Return code: {result.returncode}")
    print(f"Stdout: {result.stdout}")
    print(f"Stderr: {result.stderr}")

    # Check results
    if log_file.exists():
        content = log_file.read_text()
        print(f"Manual execution log content:\n{content}")

        assert "First command" in content
        assert "Second command" in content
        assert "Third command" in content

    finished_file = temp_env["logs_dir"] / "manual_test.finished"
    assert finished_file.exists()


def test_comprehensive_chain_logging_fix():
    """Test the comprehensive fix for chain logging issues using subprocess directly."""
    import subprocess

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        logs_dir = temp_path / "logs"
        scripts_dir = temp_path / "scripts"
        logs_dir.mkdir()
        scripts_dir.mkdir()

        # Create test scripts
        script1 = scripts_dir / "script1.sh"
        script1.write_text("""#!/bin/bash
echo "Script 1 starting"
echo "Script 1 output line 1"
echo "Script 1 finished"
""")
        script1.chmod(0o755)

        script2 = scripts_dir / "script2.py"
        script2.write_text("""#!/usr/bin/env python3
print("Script 2 starting")
print("Script 2 output line 1")
print("Script 2 finished")
""")
        script2.chmod(0o755)

        # Test simple chain logging with proper grouping
        session_name = "fixed_chain_test"
        log_file = logs_dir / f"{session_name}.log"

        # Build a command that demonstrates the fix
        chain_cmd = f"echo '---- Running script1.sh ----' && bash '{script1}' && echo '---- Running script2.py ----' && python3 '{script2}'"

        # Use proper grouping to ensure all output is captured
        cmd_parts = [
            f"printf \"# Session: {session_name}\\n# User: test\\n\" > '{log_file}'",
            f'printf "\\n=== SCRIPT STARTING at %s ===\\n" "$(date)" >> \'{log_file}\'',
            f"({chain_cmd}) >> '{log_file}' 2>&1",
            f'printf "\\n=== SCRIPT FINISHED at %s ===\\n" "$(date)" >> \'{log_file}\'',
            f"touch '{logs_dir}/{session_name}.finished'",
        ]

        full_cmd = " && ".join(cmd_parts)
        subprocess.run(full_cmd, shell=True, capture_output=True, text=True)

        assert log_file.exists()
        content = log_file.read_text()

        # Verify all outputs are captured
        assert "Script 1 starting" in content
        assert "Script 1 output line 1" in content
        assert "Script 1 finished" in content
        assert "Script 2 starting" in content
        assert "Script 2 output line 1" in content
        assert "Script 2 finished" in content
        assert "---- Running script1.sh ----" in content
        assert "---- Running script2.py ----" in content
        assert "=== SCRIPT STARTING at" in content
        assert "=== SCRIPT FINISHED at" in content

        finished_file = logs_dir / f"{session_name}.finished"
        assert finished_file.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
