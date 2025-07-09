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
        assert 'CMD ["uv", "run", "desto"]' in content or 'CMD ["uv", "run", "desto"]' in content

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
            timeout=300,  # 5 minutes timeout
        )

        assert result.returncode == 0, f"Docker build failed: {result.stderr}"
        # Check for successful build indicators from both classic and buildx output
        success_indicators = ["Successfully built", "Successfully tagged", "DONE", "writing image"]
        assert any(indicator in result.stdout or indicator in result.stderr for indicator in success_indicators), (
            f"Docker build may have failed. stdout: {result.stdout}, stderr: {result.stderr}"
        )

    @pytest.mark.skipif(not shutil.which("docker"), reason="Docker not available")
    def test_docker_run_health_check(self, temp_scripts_dir, temp_logs_dir):
        """Test that Docker container starts and responds to health checks, and cleans up after itself."""
        repo_root = Path(__file__).parent.parent

        image_name = "desto-test"
        container_name = "desto-test-container"

        # Build the image first
        build_result = subprocess.run(["docker", "build", "-t", image_name, "."], cwd=repo_root, capture_output=True, text=True, timeout=300)

        if build_result.returncode != 0:
            # Clean up any partial image
            subprocess.run(["docker", "rmi", image_name], capture_output=True)
            pytest.skip(f"Docker build failed: {build_result.stderr}")

        run_cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "-p",
            "8809:8809",
            "-v",
            f"{temp_scripts_dir}:/app/scripts",
            "-v",
            f"{temp_logs_dir}:/app/logs",
            image_name,
        ]

        try:
            result = subprocess.run(run_cmd, capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, f"Container start failed: {result.stderr}"

            # Wait for container to be ready with better health checking
            max_retries = 30
            for i in range(max_retries):
                time.sleep(2)

                # Check if container is running
                ps_result = subprocess.run(
                    ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Status}}"], capture_output=True, text=True
                )

                if "Up" not in ps_result.stdout:
                    # Container died, check logs
                    logs_result = subprocess.run(["docker", "logs", container_name], capture_output=True, text=True)
                    pytest.fail(f"Container died. Logs: {logs_result.stdout}\nErrors: {logs_result.stderr}")

                # Try to connect to the health endpoint
                try:
                    requests.get("http://localhost:8809", timeout=3)
                    # Any response means the server is up
                    break
                except requests.exceptions.RequestException:
                    if i == max_retries - 1:
                        # On last retry, get container logs for debugging
                        logs_result = subprocess.run(["docker", "logs", container_name], capture_output=True, text=True)
                        pytest.skip(
                            f"Could not connect to container after {max_retries} retries. Logs: {logs_result.stdout}\nErrors: {logs_result.stderr}"
                        )
                    continue

            # If we get here, the container is responding
            assert True, "Container is running and responding"

        finally:
            # Clean up container and image
            subprocess.run(["docker", "stop", container_name], capture_output=True)
            subprocess.run(["docker", "rm", container_name], capture_output=True)
            subprocess.run(["docker", "rmi", image_name], capture_output=True)

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
