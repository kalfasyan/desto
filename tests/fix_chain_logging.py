#!/usr/bin/env python3
"""
This script demonstrates the issues with chain logging and provides a fixed implementation.
"""

import subprocess
import tempfile
from pathlib import Path


def demonstrate_current_issues():
    """Demonstrate the current issues with chain logging."""
    print("=== DEMONSTRATING CURRENT ISSUES ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        log_file = Path(temp_dir) / "test.log"
        quoted_log_file = f"'{log_file}'"

        # This is what the current implementation does
        current_commands = [
            f'echo -e "\\n=== SCRIPT STARTING at $(date) ===\\n" > {quoted_log_file}',
            f"echo 'First' && echo 'Second' && echo 'Third' >> {quoted_log_file} 2>&1",
            f'echo -e "\\n=== SCRIPT FINISHED at $(date) ===\\n" >> {quoted_log_file}',
        ]

        current_command = " && ".join(current_commands)
        print(f"Current command: {current_command}")

        result = subprocess.run(current_command, shell=True, capture_output=True, text=True)
        print(f"Return code: {result.returncode}")
        print(f"Stdout: {result.stdout}")
        print(f"Stderr: {result.stderr}")

        if log_file.exists():
            content = log_file.read_text()
            print(f"Current log content:\n{content}")
            print("Issues:")
            print("  1. '-e' appears literally (not interpreted)")
            print("  2. Only 'Third' appears in log (chain redirect issue)")
            print("  3. 'First' and 'Second' go to stdout, not log")

def demonstrate_fixed_version():
    """Demonstrate the fixed version of chain logging."""
    print("\n=== DEMONSTRATING FIXED VERSION ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        log_file = Path(temp_dir) / "test_fixed.log"
        quoted_log_file = f"'{log_file}'"

        # Fixed version: Use printf instead of echo -e, and proper grouping
        fixed_commands = [
            f'printf "\\n=== SCRIPT STARTING at %s ===\\n" "$(date)" > {quoted_log_file}',
            f'(echo "First" && echo "Second" && echo "Third") >> {quoted_log_file} 2>&1',
            f'printf "\\n=== SCRIPT FINISHED at %s ===\\n" "$(date)" >> {quoted_log_file}',
        ]

        fixed_command = " && ".join(fixed_commands)
        print(f"Fixed command: {fixed_command}")

        result = subprocess.run(fixed_command, shell=True, capture_output=True, text=True)
        print(f"Return code: {result.returncode}")
        print(f"Stdout: {result.stdout}")
        print(f"Stderr: {result.stderr}")

        if log_file.exists():
            content = log_file.read_text()
            print(f"Fixed log content:\n{content}")
            print("Improvements:")
            print("  1. Proper date formatting")
            print("  2. All commands logged correctly")
            print("  3. No stdout leakage")

def demonstrate_failure_handling():
    """Demonstrate how to handle failures in chains."""
    print("\n=== DEMONSTRATING FAILURE HANDLING ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        log_file = Path(temp_dir) / "test_failures.log"
        quoted_log_file = f"'{log_file}'"

        # Create a failing script
        failing_script = Path(temp_dir) / "fail.sh"
        failing_script.write_text("#!/bin/bash\necho 'This will fail'\nexit 1\n")
        failing_script.chmod(0o755)

        # Option 1: Current behavior (chain stops on failure)
        print("--- Option 1: Stop on failure (current behavior) ---")
        stop_on_fail = [
            f'printf "\\n=== SCRIPT STARTING at %s ===\\n" "$(date)" > {quoted_log_file}',
            f'(echo "Before failure" && bash {failing_script} && echo "After failure") >> {quoted_log_file} 2>&1',
            f'printf "\\n=== SCRIPT FINISHED at %s ===\\n" "$(date)" >> {quoted_log_file}',
        ]

        cmd = " && ".join(stop_on_fail)
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(f"Return code: {result.returncode}")

        if log_file.exists():
            content = log_file.read_text()
            print(f"Stop-on-failure log:\n{content}")

        # Option 2: Continue on failure with exit code logging
        print("\n--- Option 2: Continue on failure (proposed fix) ---")
        log_file2 = Path(temp_dir) / "test_continue.log"
        quoted_log_file2 = f"'{log_file2}'"

        continue_on_fail = [
            f'printf "\\n=== SCRIPT STARTING at %s ===\\n" "$(date)" > {quoted_log_file2}',
            f'echo "Before failure" >> {quoted_log_file2} 2>&1',
            f'bash {failing_script} >> {quoted_log_file2} 2>&1; echo "Exit code: $?" >> {quoted_log_file2}',
            f'echo "After failure" >> {quoted_log_file2} 2>&1',
            f'printf "\\n=== SCRIPT FINISHED at %s ===\\n" "$(date)" >> {quoted_log_file2}',
        ]

        cmd2 = "; ".join(continue_on_fail)  # Use semicolons to continue on failure
        result2 = subprocess.run(cmd2, shell=True, capture_output=True, text=True)
        print(f"Return code: {result2.returncode}")

        if log_file2.exists():
            content2 = log_file2.read_text()
            print(f"Continue-on-failure log:\n{content2}")

if __name__ == "__main__":
    demonstrate_current_issues()
    demonstrate_fixed_version()
    demonstrate_failure_handling()
