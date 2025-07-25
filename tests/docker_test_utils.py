"""
Safe Docker test utilities for desto tests.

This module provides utilities for managing Docker containers in tests while
ensuring we don't interfere with user's existing containers.
"""

import subprocess
import time
from pathlib import Path

from loguru import logger


def check_for_existing_containers():
    """Check for existing containers that might conflict and warn user."""
    try:
        # Check for any running containers on ports we need
        ports_to_check = ["8809", "6380"]
        conflicting_containers = []

        for port in ports_to_check:
            result = subprocess.run(["docker", "ps", "--filter", f"publish={port}", "--format", "{{.Names}}"], capture_output=True, text=True)
            if result.stdout.strip():
                containers = result.stdout.strip().split("\n")
                for container in containers:
                    if container and not container.startswith("desto-"):
                        conflicting_containers.append(f"{container} (port {port})")

        if conflicting_containers:
            logger.warning("⚠️  Found existing containers using ports needed for desto tests:")
            for container in conflicting_containers:
                logger.warning(f"   - {container}")
            logger.warning("These tests will only manage containers with 'desto-' prefix.")
            logger.warning("If tests fail due to port conflicts, please stop conflicting containers.")
            return conflicting_containers

    except Exception as e:
        logger.debug(f"Could not check for existing containers: {e}")

    return []


def safe_docker_cleanup(project_root=None):
    """Safely cleanup only desto-related containers without affecting user containers."""
    try:
        if project_root is None:
            project_root = Path(__file__).parent.parent

        # Clean up any tmux sessions that might be running in containers
        cleanup_desto_sessions_via_container()

        # Only target containers with desto- prefix to avoid affecting user containers
        logger.debug("Stopping desto-specific containers...")

        # Get list of desto containers
        result = subprocess.run(["docker", "ps", "-a", "--filter", "name=desto-", "--format", "{{.Names}}"], capture_output=True, text=True)

        if result.stdout.strip():
            desto_containers = result.stdout.strip().split("\n")
            logger.info(f"Found desto containers to cleanup: {desto_containers}")

            # Use docker compose down but only in our project directory
            # This ensures we only affect containers defined in our compose file
            result = subprocess.run(["docker", "compose", "down", "-v", "--remove-orphans"], capture_output=True, text=True, cwd=project_root)

            if result.returncode != 0:
                logger.warning(f"Docker compose down returned non-zero: {result.stderr}")
            else:
                logger.debug("Docker compose down completed successfully")
        else:
            logger.debug("No desto containers found to cleanup")

        # Also clean up any local tmux sessions that might have been created
        cleanup_tmux_test_sessions()

    except Exception as e:
        logger.error(f"Error during safe cleanup: {e}")


def wait_for_compose_down(timeout=30):
    """Wait for docker compose down to complete properly."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            result = subprocess.run(["docker", "ps", "--filter", "name=desto-", "--format", "{{.Names}}"], capture_output=True, text=True)
            if not result.stdout.strip():
                logger.debug("All desto containers stopped")
                return True
            time.sleep(1)
        except Exception:
            pass
    logger.warning(f"Docker containers did not stop within {timeout} seconds")
    return False


def ensure_docker_available():
    """Check if Docker is available and accessible."""
    try:
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.debug(f"Docker available: {result.stdout.strip()}")
            return True
    except Exception as e:
        logger.warning(f"Docker not available: {e}")
    return False


def ensure_docker_compose_available():
    """Check if Docker Compose is available and accessible."""
    try:
        result = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.debug(f"Docker Compose available: {result.stdout.strip()}")
            return True
    except Exception as e:
        logger.warning(f"Docker Compose not available: {e}")
    return False


def get_desto_container_status():
    """Get the status of desto-related containers."""
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", "name=desto-", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"], capture_output=True, text=True
        )
        if result.returncode == 0:
            return result.stdout
    except Exception as e:
        logger.debug(f"Could not get container status: {e}")
    return ""


def is_port_available(port):
    """Check if a port is available (not in use by any container)."""
    try:
        result = subprocess.run(["docker", "ps", "--filter", f"publish={port}", "--format", "{{.Names}}"], capture_output=True, text=True)
        return not bool(result.stdout.strip())
    except Exception:
        return True  # Assume available if we can't check


def cleanup_test_artifacts():
    """Clean up any test artifacts that might have been created."""
    try:
        # Remove any test-specific files
        test_files = [
            "desto_scripts/test_script.txt",
            "desto_logs/test_log.txt",
        ]

        for file_path in test_files:
            try:
                Path(file_path).unlink(missing_ok=True)
            except Exception:
                pass

        logger.debug("Cleaned up test artifacts")
    except Exception as e:
        logger.debug(f"Error cleaning up test artifacts: {e}")


def cleanup_tmux_test_sessions():
    """Clean up any tmux sessions that might have been created by tests."""
    try:
        # List of test session names that might be created
        test_session_names = ["mysess", "test", "test_session", "integration_test"]

        for session_name in test_session_names:
            try:
                # Check if session exists
                result = subprocess.run(["tmux", "has-session", "-t", session_name], capture_output=True, text=True)

                if result.returncode == 0:
                    # Session exists, kill it
                    subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True, text=True)
                    logger.info(f"Cleaned up test tmux session: {session_name}")

            except Exception as e:
                logger.debug(f"Error cleaning up tmux session {session_name}: {e}")

    except Exception as e:
        logger.debug(f"Error during tmux session cleanup: {e}")


def cleanup_desto_sessions_via_container():
    """Clean up sessions through the desto container if it's running."""
    try:
        # Check if desto-dashboard container is running
        result = subprocess.run(["docker", "ps", "--filter", "name=desto-dashboard", "--format", "{{.Names}}"], capture_output=True, text=True)

        if "desto-dashboard" in result.stdout:
            # Try to clean up sessions through the container
            test_session_names = ["mysess", "test", "test_session", "integration_test"]

            for session_name in test_session_names:
                try:
                    # Use docker exec to kill sessions inside the container
                    subprocess.run(["docker", "exec", "desto-dashboard", "tmux", "kill-session", "-t", session_name], capture_output=True, text=True)
                    logger.debug(f"Attempted to clean up container session: {session_name}")
                except Exception as e:
                    logger.debug(f"Could not clean up container session {session_name}: {e}")

    except Exception as e:
        logger.debug(f"Error during container session cleanup: {e}")
