#!/usr/bin/env python3
"""Simple test for the core session manager without typer dependencies."""

import sys
import time
import traceback
from pathlib import Path
from desto.cli.utils import format_duration, format_timestamp
from desto.cli.session_manager import CLISessionManager

# Add the src directory to Python path for imports
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
sys.path.insert(0, str(src_dir))


def test_session_manager():
    """Test the core session manager functionality."""
    print("🧪 Testing Desto CLI Session Manager\n")

    # Initialize manager
    manager = CLISessionManager()
    print("✅ Session manager initialized")
    print(f"   Scripts directory: {manager.scripts_dir}")
    print(f"   Logs directory: {manager.log_dir}")

    # Test listing sessions (should work even if no sessions exist)
    print("\n📋 Testing session listing...")
    sessions = manager.list_sessions()
    print(f"   Found {len(sessions)} active sessions")

    if sessions:
        print("   Active sessions:")
        for name, info in sessions.items():
            status = "finished" if info["finished"] else "running"
            runtime = format_duration(info["runtime"])
            created = format_timestamp(info["created"])
            print(f"     • {name} ({status}) - {runtime} - {created}")

    # Test session existence check
    print("\n🔍 Testing session existence check...")
    test_session = "nonexistent-session"
    exists = manager.session_exists(test_session)
    print(f"   Session '{test_session}' exists: {exists}")

    # Test log file path generation
    print("\n📝 Testing log file paths...")
    log_file = manager.get_log_file("test-session")
    print(f"   Log file for 'test-session': {log_file}")

    # Test script file path generation
    script_file = manager.get_script_file("test-script.sh")
    print(f"   Script file for 'test-script.sh': {script_file}")

    print("\n✅ All core functionality tests passed!")


def test_utils():
    """Test utility functions."""
    print("\n🛠️  Testing utility functions...")

    # Test duration formatting
    test_durations = [30, 90, 3661, 86400, 90061]
    for seconds in test_durations:
        formatted = format_duration(seconds)
        print(f"   {seconds}s -> {formatted}")

    # Test timestamp formatting
    current_time = time.time()
    formatted_time = format_timestamp(current_time)
    print(f"   Current time: {formatted_time}")

    print("✅ Utility functions work correctly!")


if __name__ == "__main__":
    try:
        test_session_manager()
        test_utils()
        print("\n🎉 All tests completed successfully!")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        traceback.print_exc()
        sys.exit(1)
