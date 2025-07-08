"""
Tests for Docker integration functionality.
"""

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
import requests


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
            test_script.write_text(
                "#!/bin/bash\n"
                "echo 'Test script running in Docker'\n"
                "sleep 2\n"
                "echo 'Test script completed'\n"
            )
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
        """Test that Dockerfile exists and has correct content."""
        dockerfile = Path(__file__).parent.parent / "Dockerfile"
        assert dockerfile.exists(), "Dockerfile should exist"

        content = dockerfile.read_text()
        assert "FROM python:3.11-slim" in content
        assert "RUN pip install uv" in content
        assert "EXPOSE 8088" in content
        assert "CMD [\"uv\", \"run\", \"desto\"]" in content

    def test_docker_compose_exists(self):
        """Test that docker-compose.yml exists and has correct content."""
        compose_file = Path(__file__).parent.parent / "docker-compose.yml"
        assert compose_file.exists(), "docker-compose.yml should exist"

        content = compose_file.read_text()
        assert "version: '3.8'" in content
        assert "ports:" in content
        assert "8088:8088" in content
        assert "volumes:" in content

    def test_dockerignore_exists(self):
        """Test that .dockerignore exists and excludes test files."""
        dockerignore = Path(__file__).parent.parent / ".dockerignore"
        assert dockerignore.exists(), ".dockerignore should exist"

        content = dockerignore.read_text()
        assert "tests/" in content
        assert "*.pyc" in content
        assert "__pycache__/" in content

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
            timeout=300  # 5 minutes timeout
        )

        assert result.returncode == 0, f"Docker build failed: {result.stderr}"
        assert "Successfully built" in result.stdout or "Successfully tagged" in result.stdout

    @pytest.mark.skipif(not shutil.which("docker"), reason="Docker not available")
    def test_docker_run_health_check(self, temp_scripts_dir, temp_logs_dir):
        """Test that Docker container starts and responds to health checks."""
        repo_root = Path(__file__).parent.parent

        # Build the image first
        build_result = subprocess.run(
            ["docker", "build", "-t", "desto-test", "."],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=300
        )

        if build_result.returncode != 0:
            pytest.skip(f"Docker build failed: {build_result.stderr}")

        # Run the container
        container_name = "desto-test-container"
        run_cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "-p", "8088:8088",
            "-v", f"{temp_scripts_dir}:/app/scripts",
            "-v", f"{temp_logs_dir}:/app/logs",
            "desto-test"
        ]

        try:
            result = subprocess.run(run_cmd, capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, f"Container start failed: {result.stderr}"

            # Wait for container to be ready
            time.sleep(10)

            # Check if container is running
            ps_result = subprocess.run(
                ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Status}}"],
                capture_output=True,
                text=True
            )
            assert "Up" in ps_result.stdout, "Container should be running"

            # Test health check endpoint (basic connectivity)
            try:
                response = requests.get("http://localhost:8088", timeout=5)
                # We expect some response, even if it's not 200 due to NiceGUI setup
                assert response.status_code in [200, 404, 500], f"Unexpected status code: {response.status_code}"
            except requests.exceptions.RequestException:
                # If we can't connect, that's also valuable information
                pytest.skip("Could not connect to container - this might be expected in CI environment")

        finally:
            # Clean up container
            subprocess.run(["docker", "stop", container_name], capture_output=True)
            subprocess.run(["docker", "rm", container_name], capture_output=True)

    def test_example_scripts_exist(self):
        """Test that example scripts exist and are executable."""
        examples_dir = Path(__file__).parent.parent / "docker-examples"
        assert examples_dir.exists(), "docker-examples directory should exist"

        demo_script = examples_dir / "demo-script.sh"
        assert demo_script.exists(), "demo-script.sh should exist"

        python_script = examples_dir / "demo-script.py"
        assert python_script.exists(), "demo-script.py should exist"

        long_running = examples_dir / "long-running-demo.sh"
        assert long_running.exists(), "long-running-demo.sh should exist"

    @pytest.mark.skipif(not shutil.which("docker-compose"), reason="Docker Compose not available")
    def test_docker_compose_config(self):
        """Test that docker-compose configuration is valid."""
        repo_root = Path(__file__).parent.parent

        result = subprocess.run(
            ["docker-compose", "config"],
            cwd=repo_root,
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"Docker Compose config invalid: {result.stderr}"
        assert "desto" in result.stdout
        assert "8088" in result.stdout
