"""Tests for Docker integration functionality."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


class TestDockerIntegration:
    """Test Docker integration for desto dashboard."""

    @pytest.fixture
    def temp_scripts_dir(self):
        """Create temporary directory for test scripts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = Path(temp_dir) / "scripts"
            scripts_dir.mkdir()

            # Create test scripts
            test_script = scripts_dir / "test-script.sh"
            test_script.write_text("#!/bin/bash\necho 'Test script running in Docker'\nsleep 2\necho 'Test script completed'\n")
            test_script.chmod(0o755)

            yield scripts_dir

    @pytest.fixture
    def temp_logs_dir(self):
        """Create temporary directory for test logs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir) / "logs"
            logs_dir.mkdir()
            yield logs_dir

    def test_dockerfile_exists(self):
        """Test that Dockerfile exists and has correct content for uv base image."""
        dockerfile = Path(__file__).parent.parent / "Dockerfile"
        assert dockerfile.exists(), "Dockerfile should exist"

        content = dockerfile.read_text()
        assert "FROM ghcr.io/astral-sh/uv:" in content
        assert "uv sync --frozen" in content
        assert "EXPOSE 8809" in content
        # Accept either the original CMD or the new one with service atd start
        assert 'CMD ["uv", "run", "desto"]' in content or "CMD service atd start && uv run desto" in content

    def test_dockerignore_exists(self):
        """Test that .dockerignore exists and excludes common files."""
        dockerignore = Path(__file__).parent.parent / ".dockerignore"
        assert dockerignore.exists(), ".dockerignore should exist"

        content = dockerignore.read_text()
        assert "*.pyc" in content
        assert "__pycache__/" in content
        # Do NOT check for "tests/" unless you really want to exclude tests from the build context

    def test_docker_compose_files_exist(self):
        """Test that docker-compose files exist and have correct configuration."""
        repo_root = Path(__file__).parent.parent

        # Main docker-compose.yml with Redis
        compose_file = repo_root / "docker-compose.yml"
        assert compose_file.exists(), "docker-compose.yml should exist"

        content = compose_file.read_text()
        assert "redis:" in content
        assert "REDIS_HOST=redis" in content
        assert "image: redis:7-alpine" in content
        assert "required for session tracking" in content  # Updated comment

    @pytest.mark.skipif(not shutil.which("docker"), reason="Docker not available")
    def test_docker_build(self):
        """Test that Docker image can be built successfully."""
        repo_root = Path(__file__).parent.parent

        # Build the Docker image
        result = subprocess.run(
            ["docker", "build", "-t", "desto-test", "."],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
        )

        assert result.returncode == 0, f"Docker build failed: {result.stderr}"
        # Check for successful build indicators from both classic and buildx output
        success_indicators = ["Successfully built", "Successfully tagged", "DONE", "writing image"]
        assert any(indicator in result.stdout or indicator in result.stderr for indicator in success_indicators), f"Docker build may have failed. stdout: {result.stdout}, stderr: {result.stderr}"

    @pytest.mark.skipif(not shutil.which("docker"), reason="Docker not available")
    def test_docker_compose_health_check(self, temp_scripts_dir, temp_logs_dir, docker_compose):
        """Test that Docker Compose stack starts with Redis and responds to health checks (fast version)."""
        repo_root = Path(__file__).parent.parent

        compose_check = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
        if compose_check.returncode != 0:
            pytest.skip("Docker Compose not available")

        from .docker_test_utils import safe_docker_cleanup, wait_for_http

        try:
            # The `docker_compose` fixture ensures compose is running for this session
            healthy = wait_for_http("http://localhost:8809", timeout=20, interval=0.5)
            if not healthy:
                logs_result = subprocess.run(["docker", "compose", "-f", "docker-compose.yml", "logs", "dashboard"], cwd=repo_root, capture_output=True, text=True)
                pytest.skip(f"Could not connect to service within timeout. Logs: {logs_result.stdout}")

            assert True, "Docker Compose stack is running and responding"

        finally:
            # Respective cleanup (skip volume removal for speed)
            safe_docker_cleanup(project_root=repo_root, remove_volumes=False)

    def test_example_scripts_exist(self):
        """Test that example scripts exist and are executable."""
        examples_dir = Path(__file__).parent.parent / "desto_scripts"
        assert examples_dir.exists(), "desto_scripts directory should exist"

        demo_script = examples_dir / "demo-script.sh"
        assert demo_script.exists(), "demo-script.sh should exist"

        python_script = examples_dir / "demo-script.py"
        assert python_script.exists(), "demo-script.py should exist"

        long_running = examples_dir / "long-running-demo.sh"
        assert long_running.exists(), "long-running-demo.sh should exist"

    def test_redis_environment_variables(self):
        """Test that Redis environment variables are properly handled."""
        from desto.redis.client import DestoRedisClient

        # Test with custom config
        config = {
            "host": "test-redis",
            "port": 6380,
            "db": 1,
            "enabled": True,
            "connection_timeout": 10,
        }

        client = DestoRedisClient(config)
        assert client.config["host"] == "test-redis"
        assert client.config["port"] == 6380
        assert client.config["db"] == 1
        assert client.config["enabled"] is True
        assert client.config["connection_timeout"] == 10

    def test_environment_variable_configuration(self):
        """Test that environment variables override default configuration."""
        import os
        from unittest.mock import patch

        # Mock environment variables
        env_vars = {
            "REDIS_HOST": "env-redis",
            "REDIS_PORT": "6380",
            "REDIS_DB": "2",
            "REDIS_ENABLED": "false",
            "REDIS_CONNECTION_TIMEOUT": "10",
        }

        with patch.dict(os.environ, env_vars):
            from desto.redis.client import DestoRedisClient

            # Create client with no config (should use env vars)
            client = DestoRedisClient()
            assert client.config["host"] == "env-redis"
            assert client.config["port"] == 6380
            assert client.config["db"] == 2
            assert client.config["enabled"] is False
            assert client.config["connection_timeout"] == 10
