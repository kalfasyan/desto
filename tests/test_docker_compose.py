"""Tests for Docker Compose setup."""

import os
import subprocess
import time
from pathlib import Path

import pytest
from loguru import logger

from .docker_test_utils import (
    check_for_existing_containers,
    cleanup_tmux_test_sessions,
    compose_up_if_needed,
    ensure_docker_available,
    ensure_docker_compose_available,
    safe_docker_cleanup,
    wait_for_compose_down,
    wait_for_http,
)

pytestmark = pytest.mark.skipif(not ensure_docker_available() or not ensure_docker_compose_available(), reason="Docker and Docker Compose are required for these tests.")


class TestDockerCompose:
    """Test Docker Compose functionality."""

    @pytest.fixture(scope="class", autouse=True)
    def compose_once(self):
        """Start compose once for the test class and tear down at the end.

        This reduces repeated compose up/down per test which is slow.
        """
        # Rely on session-scoped autouse fixture `docker_compose` to have started compose.
        # Wait briefly for HTTP readiness before running tests
        wait_for_http("http://localhost:8809", timeout=30, interval=0.5)
        yield
        # No class-level teardown; session fixture will handle final cleanup.

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and teardown for Docker Compose tests."""
        # Ensure we're in the project root
        project_root = Path(__file__).parent.parent
        os.chdir(project_root)
        logger.info(f"Changed to project root: {project_root}")

        # Check for existing containers that might conflict
        check_for_existing_containers()

        # Detect whether desto containers are already present (e.g. started by class fixture)
        res = subprocess.run(["docker", "ps", "--filter", "name=desto-", "--format", "{{.Names}}"], capture_output=True, text=True)
        containers_present = bool(res.stdout.strip())

        # Cleanup only if no desto containers are present; this avoids removing class-level compose
        if not containers_present:
            logger.info("Cleaning up existing desto test containers...")
            safe_docker_cleanup(project_root)
        else:
            logger.debug("Desto containers already present; skipping initial cleanup")

        yield

        # Cleanup after test only when we did not detect pre-existing containers
        if not containers_present:
            logger.info("Cleaning up desto test containers after test...")
            safe_docker_cleanup(project_root, remove_volumes=False)
            wait_for_compose_down()
        else:
            logger.debug("Skipping per-test cleanup because containers were present at setup")

        # Additional explicit session cleanup
        cleanup_tmux_test_sessions()

    def test_docker_compose_build(self):
        """Test that Docker Compose can build the service."""
        logger.info("Starting Docker Compose build test...")
        # Do NOT tear down existing containers started by fixtures; just build images.
        result = subprocess.run(["docker", "compose", "build"], capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Build failed with stderr: {result.stderr}")
        else:
            logger.info("Docker Compose build completed successfully")

        assert result.returncode == 0, f"Build failed: {result.stderr}"

        # Ensure services are (back) up for subsequent tests if build interrupted them
        compose_up_if_needed(timeout=60)
        wait_for_http("http://localhost:8809", timeout=60, interval=0.5)

    def test_docker_compose_up_and_health(self):
        """Test that Docker Compose can start the service and it becomes healthy."""
        logger.info("Starting Docker Compose up and health test...")
        # Proactively ensure compose is up (idempotent if already running)
        compose_up_if_needed(timeout=60)
        # Allow a slightly longer window; cold starts or CI can be slower
        healthy = wait_for_http("http://localhost:8809", timeout=60, interval=0.5)
        if not healthy:
            # Dump diagnostic info to help debugging
            logger.error("Service did not become healthy within timeout; dumping diagnostics")
            try:
                ps = subprocess.run(["docker", "compose", "ps"], capture_output=True, text=True)
                logs_dash = subprocess.run(["docker", "compose", "logs", "dashboard"], capture_output=True, text=True)
                logger.error(f"Compose ps output:\n{ps.stdout}")
                logger.error(f"Dashboard logs:\n{logs_dash.stdout}")
            except Exception as e:
                logger.error(f"Failed to collect diagnostics: {e}")
        assert healthy, "Service did not become healthy within timeout"

    @pytest.mark.skipif(os.getenv("CI") == "true", reason="Skip volume test on GitHub Actions due to permission issues")
    def test_docker_compose_volumes(self):
        """Test that volumes are mounted correctly in the container."""
        logger.info("Starting Docker Compose volumes test...")
        # Ensure service is running (build test may have rebuilt images)
        compose_up_if_needed(timeout=60)
        wait_for_http("http://localhost:8809", timeout=60, interval=0.5)

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

        # The class fixture ensures compose is up; allow more time for mounts (slower FS / CI)
        time.sleep(1.0)

        # Check that the files exist inside the container
        logger.info("Checking if files are accessible inside container...")
        result_script = subprocess.run(["docker", "compose", "exec", "-T", "dashboard", "cat", "/app/desto_scripts/test_script.txt"], capture_output=True, text=True)
        result_log = subprocess.run(["docker", "compose", "exec", "-T", "dashboard", "cat", "/app/desto_logs/test_log.txt"], capture_output=True, text=True)

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
        # The class fixture starts compose; wait for HTTP readiness
        wait_for_http("http://localhost:8809", timeout=20)

        # Check environment variables in container
        logger.info("Checking environment variables in container...")

        # Wait (short) for container to be running
        for _ in range(6):
            status = subprocess.run(["docker", "compose", "ps", "--services", "--filter", "status=running"], capture_output=True, text=True)
            if "dashboard" in status.stdout:
                break
            time.sleep(0.5)
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

        # Wait for initial startup (use helper)
        logger.info("Waiting for initial service startup...")
        assert wait_for_http("http://localhost:8809", timeout=30), "Service did not become healthy before restart"

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
        assert wait_for_http("http://localhost:8809", timeout=30), "Service did not become healthy after restart"
