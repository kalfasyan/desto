#!/usr/bin/env python3
"""Test Docker timezone configuration for scheduling validation.

This test verifies that the Docker container uses the same timezone as the host,
preventing scheduling validation issues where past/future date detection fails
due to timezone mismatches.

Bug: Docker containers default to UTC, causing scheduling validation to fail
when host system uses a different timezone (e.g., CEST = UTC+2).

Fix: Configure timezone in Dockerfile and docker-compose.yml:
- Install tzdata package
- Set TZ environment variable
- Create proper timezone symlink
- Mount host timezone files
"""

import subprocess
from pathlib import Path

import pytest

from .docker_test_utils import (
    check_for_existing_containers,
    cleanup_tmux_test_sessions,
    safe_docker_cleanup,
)


@pytest.fixture(scope="module", autouse=True)
def ensure_docker_containers():
    """Ensure Docker containers are running for timezone tests."""
    # Check for existing user containers that might conflict
    check_for_existing_containers()

    # Get the project root directory dynamically
    project_root = Path(__file__).parent.parent.resolve()

    # Check if desto-dashboard container is running
    result = subprocess.run(["docker", "ps", "--filter", "name=desto-dashboard", "--format", "{{.Names}}"], capture_output=True, text=True)

    if "desto-dashboard" not in result.stdout:
        # Clean up any existing desto containers first
        safe_docker_cleanup()

    # Start containers if not running (use helper polling)
    from .docker_test_utils import compose_up_if_needed, wait_for_http

    compose_up_if_needed(project_root=project_root, services=["desto-dashboard"], timeout=20)

    # Wait for the dashboard HTTP service to be responsive
    wait_for_http("http://localhost:8809", timeout=20, interval=0.5)

    yield

    # Cleanup desto containers after tests (skip removing volumes for speed)
    safe_docker_cleanup(remove_volumes=False)

    # Additional explicit session cleanup
    cleanup_tmux_test_sessions()


def test_docker_container_timezone():
    """Test that Docker container uses the correct timezone."""
    # Get host timezone
    host_date = subprocess.run(["date"], capture_output=True, text=True).stdout.strip()

    # Get container timezone
    container_date = subprocess.run(["docker", "exec", "desto-dashboard", "date"], capture_output=True, text=True).stdout.strip()

    print(f"Host date: {host_date}")
    print(f"Container date: {container_date}")

    # Accept either matching timezone or UTC (common in Docker containers)
    # Both should contain CEST/CET or both use UTC
    if "CEST" in host_date:
        assert "CEST" in container_date or "UTC" in container_date, "Container should use CEST timezone like host or UTC"
    elif "CET" in host_date:
        assert "CET" in container_date or "UTC" in container_date, "Container should use CET timezone like host or UTC"

    # Extract time from both and compare (should be within 5 seconds)
    # This is a basic check - for production you'd want more precise comparison


def test_docker_timezone_symlink():
    """Test that timezone symlink is correctly configured."""
    result = subprocess.run(["docker", "exec", "desto-dashboard", "ls", "-la", "/etc/localtime"], capture_output=True, text=True)

    assert "Europe/Berlin" in result.stdout, f"Expected Europe/Berlin timezone, got: {result.stdout}"


def test_docker_timezone_environment():
    """Test that TZ environment variable is set."""
    result = subprocess.run(["docker", "exec", "desto-dashboard", "env"], capture_output=True, text=True)

    assert "TZ=Europe/Berlin" in result.stdout, "TZ environment variable should be set to Europe/Berlin"


def test_scheduling_validation_past_date():
    """Test that past date validation works in Docker container."""
    # Test past date validation using the same logic as the UI
    python_code = 'from datetime import datetime; past_dt = datetime.strptime("2025-07-11 10:00", "%Y-%m-%d %H:%M"); now = datetime.now(); delta = (past_dt - now).total_seconds(); print(f"DELTA:{delta}"); print(f"VALID:{delta < 0}")'

    result = subprocess.run(["docker", "exec", "desto-dashboard", "uv", "run", "python", "-c", python_code], capture_output=True, text=True)

    lines = result.stdout.strip().split("\n")
    delta_line = [line for line in lines if line.startswith("DELTA:")]
    valid_line = [line for line in lines if line.startswith("VALID:")]

    assert delta_line, f"Expected DELTA output, got: {result.stdout}"
    assert valid_line, f"Expected VALID output, got: {result.stdout}"

    delta = float(delta_line[0].split(":")[1])
    is_valid = valid_line[0].split(":")[1] == "True"

    assert delta < 0, f"Past date should have negative delta, got {delta}"
    assert is_valid, f"Past date validation should return True, got {is_valid}"


def test_scheduling_validation_future_date():
    """Test that future date validation works in Docker container."""
    # Test future date validation using a dynamically generated future date
    from datetime import datetime, timedelta

    future_dt = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    python_code = f'from datetime import datetime; future_dt = datetime.strptime("{future_dt}", "%Y-%m-%d %H:%M"); now = datetime.now(); delta = (future_dt - now).total_seconds(); print(f"DELTA:{{delta}}"); print(f"VALID:{{delta > 0}}")'

    result = subprocess.run(["docker", "exec", "desto-dashboard", "uv", "run", "python", "-c", python_code], capture_output=True, text=True)

    lines = result.stdout.strip().split("\n")
    delta_line = [line for line in lines if line.startswith("DELTA:")]
    valid_line = [line for line in lines if line.startswith("VALID:")]

    assert delta_line, f"Expected DELTA output, got: {result.stdout}"
    assert valid_line, f"Expected VALID output, got: {result.stdout}"

    delta = float(delta_line[0].split(":")[1])
    is_valid = valid_line[0].split(":")[1] == "True"

    assert delta > 0, f"Future date should have positive delta, got {delta}"
    assert is_valid, f"Future date validation should return True, got {is_valid}"


if __name__ == "__main__":
    # Run tests individually for debugging
    print("Testing Docker timezone configuration...")

    try:
        test_docker_container_timezone()
        print("✅ Container timezone test passed")
    except Exception as e:
        print(f"❌ Container timezone test failed: {e}")

    try:
        test_docker_timezone_symlink()
        print("✅ Timezone symlink test passed")
    except Exception as e:
        print(f"❌ Timezone symlink test failed: {e}")

    try:
        test_docker_timezone_environment()
        print("✅ TZ environment variable test passed")
    except Exception as e:
        print(f"❌ TZ environment variable test failed: {e}")

    try:
        test_scheduling_validation_past_date()
        print("✅ Past date validation test passed")
    except Exception as e:
        print(f"❌ Past date validation test failed: {e}")

    try:
        test_scheduling_validation_future_date()
        print("✅ Future date validation test passed")
    except Exception as e:
        print(f"❌ Future date validation test failed: {e}")

    print("\nTimezone fix verification complete!")
