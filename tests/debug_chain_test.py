#!/usr/bin/env python3

import subprocess
import tempfile
import time
from pathlib import Path


def test_simple_chain_logging():
    """Test simple chain logging to isolate the issue."""

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
sleep 1
echo "Script 1 finished"
""")
        script1.chmod(0o755)

        script2 = scripts_dir / "script2.sh"
        script2.write_text("""#!/bin/bash
echo "Script 2 starting"
sleep 1
echo "Script 2 finished"
""")
        script2.chmod(0o755)

        # Build chain command like the UI manager does
        chain_commands = []
        for script in [script1, script2]:
            chain_commands.append(f"echo '---- Running {script.name} ----'")
            chain_commands.append(f"bash '{script}'")

        full_chain_cmd = " && ".join(chain_commands)
        print(f"Chain command: {full_chain_cmd}")

        # Build logging command
        session_name = "debug_chain_test"
        log_file = logs_dir / f"{session_name}.log"
        finished_marker = f"touch '{logs_dir}/{session_name}.finished'"
        info_block = f"# Session: {session_name}\\n# User: test"

        cmd_parts = [
            f"printf '%s\\n' {repr(info_block)} > '{log_file}'",
            f"printf '\\n=== SCRIPT STARTING at %s ===\\n' \"$(date)\" >> '{log_file}'",
            f"({full_chain_cmd}) >> '{log_file}' 2>&1",
            f"printf '\\n=== SCRIPT FINISHED at %s ===\\n' \"$(date)\" >> '{log_file}'",
            finished_marker,
        ]

        logging_cmd = " && ".join(cmd_parts)
        print(f"Logging command: {logging_cmd}")

        # Run via tmux using shlex for proper quoting
        import shlex

        tmux_cmd = f"tmux new-session -d -s {session_name} bash -c {shlex.quote(logging_cmd)}"
        print(f"Tmux command: {tmux_cmd}")

        result = subprocess.run(tmux_cmd, shell=True, capture_output=True, text=True)
        print(f"Tmux start return code: {result.returncode}")
        print(f"Tmux start stdout: {result.stdout}")
        print(f"Tmux start stderr: {result.stderr}")

        # Wait for completion
        for i in range(10):  # Wait up to 10 seconds
            time.sleep(1)
            try:
                check_result = subprocess.run(["tmux", "has-session", "-t", session_name], capture_output=True)
                if check_result.returncode != 0:
                    print(f"Session completed after {i + 1} seconds")
                    break
            except Exception:
                break
        else:
            print("Session still running after 10 seconds")
            # Kill it
            subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True)

        # Check results
        finished_file = logs_dir / f"{session_name}.finished"
        print(f"Log file exists: {log_file.exists()}")
        print(f"Finished file exists: {finished_file.exists()}")

        if log_file.exists():
            content = log_file.read_text()
            print(f"Log content:\n{content}")
        else:
            print("No log file created!")

        if finished_file.exists():
            print("Finished marker created successfully!")
        else:
            print("Finished marker NOT created!")


if __name__ == "__main__":
    test_simple_chain_logging()
