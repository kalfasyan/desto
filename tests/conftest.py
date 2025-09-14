import os
import subprocess
from pathlib import Path

import pytest

from .docker_test_utils import ensure_docker_available, ensure_docker_compose_available, safe_docker_cleanup, wait_for_http


@pytest.fixture(scope="session", autouse=True)
def docker_compose():
    """Bring up docker-compose once for tests that opt-in.

    Yields the project_root Path. Tests can call `safe_docker_cleanup(..., remove_volumes=False)`
    to cleanup without removing volumes when appropriate.
    """
    project_root = Path(__file__).parent.parent

    # Allow CI to disable automatic compose start via env var
    # Set DOCKER_COMPOSE_AUTOSTART to '0', 'false', 'no', or 'off' to disable
    autostart_env = os.getenv("DOCKER_COMPOSE_AUTOSTART", "true").strip().lower()
    autostart = autostart_env not in ("0", "false", "no", "off")

    if not autostart:
        # Autostart disabled by environment — do nothing.
        return

    # Skip starting compose if Docker or Docker Compose are not available on this runner
    if not ensure_docker_available() or not ensure_docker_compose_available():
        pytest.skip("Docker or Docker Compose not available for tests")

    # Bring up compose for tests, using test override if available to shorten healthchecks
    override_path = project_root / "tests" / "docker-compose.test.yml"
    if override_path.exists():
        up_cmd = ["docker", "compose", "-f", "docker-compose.yml", "-f", "tests/docker-compose.test.yml", "up", "-d"]
    else:
        up_cmd = ["docker", "compose", "up", "-d"]

    up = subprocess.run(up_cmd, cwd=project_root, capture_output=True, text=True)
    if up.returncode != 0:
        raise RuntimeError(f"docker compose up failed in fixture: {up.stderr}")

    # Wait for service readiness
    wait_for_http("http://localhost:8809", timeout=60, interval=0.5)

    try:
        yield project_root
    finally:
        # At session end, remove containers but skip volumes removal by default
        safe_docker_cleanup(project_root, remove_volumes=False)
        # Allow some time for compose to stop
        wait_for_http("http://localhost:8809", timeout=3, interval=0.5)
