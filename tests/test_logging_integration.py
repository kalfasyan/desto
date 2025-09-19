"""Integration test for logging functionality.
This test can be run manually to verify the logging fix works in practice.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest
from loguru import logger

from desto.app.sessions import TmuxManager

pytestmark = pytest.mark.skipif(os.getenv("CI") == "true", reason="Redis is not available on GitHub Actions")


@pytest.mark.skip(reason="Integration test for manual execution only")
def test_logging_integration():
    """Integration test demonstrating the logging fix."""
    logger.info("🧪 Testing logging functionality integration...")

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
        logger.info("📝 Running first session...")
        session_name = "integration_test"
        command = f"bash {test_script}"

        tmux_manager.start_tmux_session(session_name, command, mock_logger)

        # Wait for completion
        import time

        time.sleep(4)

        log_file = log_dir / f"{session_name}.log"
        if log_file.exists():
            content1 = log_file.read_text()
            logger.info(f"✅ First session log created ({len(content1)} chars)")
            logger.debug("📄 First session content:")
            logger.debug("=" * 50)
            logger.debug(content1)
            logger.debug("=" * 50)
        else:
            logger.error("❌ First session log file not created")
            return False

        # Test 2: Second session (should append)
        logger.info("\n📝 Running second session...")
        command2 = "echo 'Second session test'"

        tmux_manager.start_tmux_session(session_name, command2, mock_logger)
        time.sleep(3)

        if log_file.exists():
            content2 = log_file.read_text()
            logger.info(f"✅ Second session appended to log ({len(content2)} chars)")
            logger.debug("📄 Final log content:")
            logger.debug("=" * 50)
            logger.debug(content2)
            logger.debug("=" * 50)

            # Verify both sessions are present
            if "Test script output" in content2 and "Second session test" in content2:
                logger.info("✅ Both sessions preserved in log")
            else:
                logger.error("❌ Log content was overwritten")
                return False

            if "---- NEW SESSION" in content2:
                logger.info("✅ Session separator found")
            else:
                logger.warning("⚠️  Session separator not found")

            start_count = content2.count("=== SCRIPT STARTING at")
            finish_count = content2.count("=== SCRIPT FINISHED at")

            logger.info(f"📊 Found {start_count} start entries and {finish_count} finish entries")

            if start_count == 2 and finish_count == 2:
                logger.info("✅ Correct number of start/finish entries")
            else:
                logger.warning("⚠️  Unexpected number of start/finish entries")
        else:
            logger.error("❌ Second session log file not found")
            return False

    logger.info("\n🎉 Integration test completed successfully!")
    return True


if __name__ == "__main__":
    success = test_logging_integration()
    exit(0 if success else 1)
