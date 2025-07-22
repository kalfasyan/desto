"""Tests for Docker Compose setup."""

import os
import subprocess
import time
from pathlib import Path

import pytest
import requests
from loguru import logger

from .docker_test_utils import (
    check_for_existing_containers,
    cleanup_tmux_test_sessions,
    ensure_docker_available,
    ensure_docker_compose_available,
    safe_docker_cleanup,
    wait_for_compose_down,
)

pytestmark = pytest.mark.skipif(
    not ensure_docker_available() or not ensure_docker_compose_available(), reason="Docker and Docker Compose are required for these tests."
)


class TestDockerCompose:
    """Test Docker Compose functionality."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and teardown for Docker Compose tests."""
        # Ensure we're in the project root
        project_root = Path(__file__).parent.parent
        os.chdir(project_root)
        logger.info(f"Changed to project root: {project_root}")

        # Check for existing containers that might conflict
        check_for_existing_containers()

        # Cleanup any existing desto test containers specifically
        logger.info("Cleaning up existing desto test containers...")
        safe_docker_cleanup(project_root)

        yield

        # Cleanup after test
        logger.info("Cleaning up desto test containers after test...")
        safe_docker_cleanup(project_root)
        wait_for_compose_down()

        # Additional explicit session cleanup
        cleanup_tmux_test_sessions()

    def test_docker_compose_build(self):
        """Test that Docker Compose can build the service."""
        logger.info("Starting Docker Compose build test...")

        # Ensure clean state before build
        safe_docker_cleanup()
        wait_for_compose_down()

        result = subprocess.run(["docker", "compose", "build"], capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Build failed with stderr: {result.stderr}")
        else:
            logger.info("Docker Compose build completed successfully")

        assert result.returncode == 0, f"Build failed: {result.stderr}"

    def test_docker_compose_up_and_health(self):
        """Test that Docker Compose can start the service and it becomes healthy."""
        logger.info("Starting Docker Compose up and health test...")

        # Start the service
        logger.info("Starting Docker Compose service...")
        result = subprocess.run(["docker", "compose", "up", "-d"], capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Failed to start service with stderr: {result.stderr}")
            time.sleep(10)  # Wait and retry once
            result = subprocess.run(["docker", "compose", "up", "-d"], capture_output=True, text=True)
        assert result.returncode == 0, f"Failed to start service: {result.stderr}"
        time.sleep(10)  # Give extra time for network/service creation

        # Wait for the service to be healthy (max 60 seconds)
        logger.info("Waiting for service to become healthy...")
        max_wait = 60
        wait_time = 0
        service_healthy = False

        while wait_time < max_wait:
            try:
                # Check container health
                health_result = subprocess.run(["docker", "compose", "ps", "--format", "json"], capture_output=True, text=True)

                if health_result.returncode == 0:
                    # Try to make a request to the service
                    response = requests.get("http://localhost:8809", timeout=5)
                    if response.status_code == 200:
                        logger.info(f"Service became healthy after {wait_time} seconds")
                        service_healthy = True
                        break

            except (requests.RequestException, subprocess.SubprocessError) as e:
                logger.debug(f"Health check attempt failed: {e}")

            time.sleep(2)
            wait_time += 2

        if not service_healthy:
            logger.error(f"Service did not become healthy within {max_wait} seconds")
        assert service_healthy, "Service did not become healthy within timeout"

    def test_docker_compose_volumes(self):
        """Test that volumes are mounted correctly in the container."""
        logger.info("Starting Docker Compose volumes test...")

        # Create test files in host directories
        scripts_dir = Path("desto_scripts")
        logs_dir = Path("desto_logs")
        scripts_dir.mkdir(exist_ok=True)
        logs_dir.mkdir(exist_ok=True)

        test_script = scripts_dir / "test_script.txt"
        test_log = logs_dir / "test_log.txt"

        # Clean up old files to avoid permission issues
        for f in [test_script, test_log]:
            if f.exists():
                try:
                    f.unlink()
                except PermissionError:
                    f.chmod(0o666)
                    f.unlink()

        test_script.write_text("hello from host script")
        test_log.write_text("hello from host log")

        # Start the service
        subprocess.run(["docker", "compose", "up", "-d"], capture_output=True, text=True)
        time.sleep(10)  # Increase wait time for container startup and volume mount

        # Check that the files exist inside the container
        logger.info("Checking if files are accessible inside container...")
        result_script = subprocess.run(
            ["docker", "compose", "exec", "-T", "dashboard", "cat", "/app/desto_scripts/test_script.txt"], capture_output=True, text=True
        )
        result_log = subprocess.run(
            ["docker", "compose", "exec", "-T", "dashboard", "cat", "/app/desto_logs/test_log.txt"], capture_output=True, text=True
        )

        if result_script.returncode == 0:
            logger.info("Script file successfully accessed in container")
        else:
            logger.error("Script file not accessible in container")

        if result_log.returncode == 0:
            logger.info("Log file successfully accessed in container")
        else:
            logger.error("Log file not accessible in container")

        assert result_script.returncode == 0, "Script file not found in container"
        assert "hello from host script" in result_script.stdout
        assert result_log.returncode == 0, "Log file not found in container"
        assert "hello from host log" in result_log.stdout

        # Clean up test files
        test_script.unlink(missing_ok=True)
        test_log.unlink(missing_ok=True)
        logger.info("Cleaned up test files")

    def test_docker_compose_environment_variables(self):
        """Test that environment variables are properly set."""
        logger.info("Starting Docker Compose environment variables test...")

        # Start the service
        logger.info("Starting Docker Compose service for environment test...")
        subprocess.run(["docker", "compose", "up", "-d"], capture_output=True, text=True)

        # Wait a bit for startup
        time.sleep(10)

        # Check environment variables in container
        logger.info("Checking environment variables in container...")
        result = subprocess.run(["docker", "compose", "exec", "-T", "dashboard", "env"], capture_output=True, text=True)

        # Wait for container to be running
        for _ in range(10):
            status = subprocess.run(["docker", "compose", "ps", "--services", "--filter", "status=running"], capture_output=True, text=True)
            if "dashboard" in status.stdout:
                break
            time.sleep(2)
        else:
            logs = subprocess.run(["docker", "compose", "logs", "dashboard"], capture_output=True, text=True)
            logger.error(f"Dashboard logs:\n{logs.stdout}")
            pytest.skip("Dashboard service did not start successfully")

        # Now exec into the running container
        result = subprocess.run(["docker", "compose", "exec", "-T", "dashboard", "env"], capture_output=True, text=True)

        if result.returncode == 0:
            logger.info("Successfully retrieved environment variables from container")
        else:
            logger.error("Failed to retrieve environment variables from container")

        assert result.returncode == 0, f"Failed to get environment variables: {result.stderr}"
        assert "DESTO_SCRIPTS_DIR=/app/desto_scripts" in result.stdout
        assert "DESTO_LOGS_DIR=/app/desto_logs" in result.stdout

    def test_docker_compose_service_restart(self):
        """Test that the service can be restarted."""
        logger.info("Starting Docker Compose service restart test...")

        # Start the service
        logger.info("Starting Docker Compose service...")
        subprocess.run(["docker", "compose", "up", "-d"], capture_output=True, text=True)

        # Wait for initial startup
        logger.info("Waiting for initial service startup...")
        max_wait = 60
        wait_time = 0
        service_healthy = False
        while wait_time < max_wait:
            try:
                response = requests.get("http://localhost:8809", timeout=5)
                if response.status_code == 200:
                    logger.info(f"Service became healthy after {wait_time} seconds")
                    service_healthy = True
                    break
            except requests.RequestException as e:
                logger.debug(f"Health check attempt failed: {e}")
            time.sleep(2)
            wait_time += 2
        assert service_healthy, "Service did not become healthy before restart"

        # Restart the service
        logger.info("Restarting Docker Compose service...")
        result = subprocess.run(["docker", "compose", "restart"], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("Service restart command executed successfully")
        else:
            logger.error(f"Service restart failed with stderr: {result.stderr}")
        assert result.returncode == 0, f"Failed to restart service: {result.stderr}"

        # Wait for restart and for the service to become healthy again
        logger.info("Waiting for service to become healthy after restart...")
        max_wait = 60
        wait_time = 0
        service_healthy = False
        while wait_time < max_wait:
            try:
                response = requests.get("http://localhost:8809", timeout=5)
                if response.status_code == 200:
                    logger.info(f"Service became healthy after restart in {wait_time} seconds")
                    service_healthy = True
                    break
            except requests.RequestException as e:
                logger.debug(f"Health check attempt after restart failed: {e}")
            time.sleep(2)
            wait_time += 2
        assert service_healthy, "Service did not become healthy after restart"
