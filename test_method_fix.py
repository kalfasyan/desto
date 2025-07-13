#!/usr/bin/env python3
"""Test script to verify get_session_start_command method works correctly."""

import sys
from pathlib import Path
from unittest.mock import Mock

from desto.app.sessions import TmuxManager

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))


def test_get_session_start_command():
    """Test the get_session_start_command method."""
    print("Testing get_session_start_command method...")

    # Create mock objects
    mock_ui = Mock()
    mock_logger = Mock()

    try:
        # Create TmuxManager instance
        tm = TmuxManager(mock_ui, mock_logger)

        # Test the method
        session_name = "test_session"
        command = "echo 'hello world'"

        result = tm.get_session_start_command(session_name, command)

        print(f"✅ Method exists and returned: {result}")

        # Verify the result contains expected components
        assert "mark_session_started.py" in result, "Should contain script path"
        assert session_name in result, "Should contain session name"
        assert "python" in result.lower(), "Should contain python command"

        print("✅ All assertions passed!")
        print("🎉 get_session_start_command method is working correctly!")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_get_session_start_command()
    sys.exit(0 if success else 1)
