"""
Integration test for logging functionality.
This test can be run manually to verify the logging fix works in practice.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock

from desto.app.sessions import TmuxManager


def test_logging_integration():
    """Integration test demonstrating the logging fix."""
    print("🧪 Testing logging functionality integration...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        log_dir = temp_path / "logs"
        scripts_dir = temp_path / "scripts"

        log_dir.mkdir()
        scripts_dir.mkdir()

        # Create a test script
        test_script = scripts_dir / "test_script.sh"
        test_script.write_text("#!/bin/bash\necho 'Test script output'\nsleep 1\necho 'Script completed'\n")
        test_script.chmod(0o755)

        mock_ui = Mock()
        mock_logger = Mock()

        tmux_manager = TmuxManager(mock_ui, mock_logger, log_dir=log_dir, scripts_dir=scripts_dir)

        # Test 1: First session
        print("📝 Running first session...")
        session_name = "integration_test"
        command = f"bash {test_script}"

        tmux_manager.start_tmux_session(session_name, command, mock_logger, keep_alive=False)

        # Wait for completion
        import time
        time.sleep(4)

        log_file = log_dir / f"{session_name}.log"
        if log_file.exists():
            content1 = log_file.read_text()
            print(f"✅ First session log created ({len(content1)} chars)")
            print("📄 First session content:")
            print("=" * 50)
            print(content1)
            print("=" * 50)
        else:
            print("❌ First session log file not created")
            return False

        # Test 2: Second session (should append)
        print("\n📝 Running second session...")
        command2 = "echo 'Second session test'"

        tmux_manager.start_tmux_session(session_name, command2, mock_logger, keep_alive=False)
        time.sleep(3)

        if log_file.exists():
            content2 = log_file.read_text()
            print(f"✅ Second session appended to log ({len(content2)} chars)")
            print("📄 Final log content:")
            print("=" * 50)
            print(content2)
            print("=" * 50)

            # Verify both sessions are present
            if "Test script output" in content2 and "Second session test" in content2:
                print("✅ Both sessions preserved in log")
            else:
                print("❌ Log content was overwritten")
                return False

            if "---- NEW SESSION" in content2:
                print("✅ Session separator found")
            else:
                print("⚠️  Session separator not found")

            start_count = content2.count("=== SCRIPT STARTING at")
            finish_count = content2.count("=== SCRIPT FINISHED at")

            print(f"📊 Found {start_count} start entries and {finish_count} finish entries")

            if start_count == 2 and finish_count == 2:
                print("✅ Correct number of start/finish entries")
            else:
                print("⚠️  Unexpected number of start/finish entries")
        else:
            print("❌ Second session log file not found")
            return False

    print("\n🎉 Integration test completed successfully!")
    return True


if __name__ == "__main__":
    success = test_logging_integration()
    exit(0 if success else 1)
