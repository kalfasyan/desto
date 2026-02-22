import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from desto.cli.service import ServiceManager


@pytest.fixture
def service_manager():
    with patch("pathlib.Path.home", return_value=Path("/tmp/desto_test_home")):
        return ServiceManager()


def test_service_manager_init(service_manager):
    """Test that ServiceManager initializes with correct paths."""
    assert "systemd" in str(service_manager.templates_dir)
    assert "desto.service" in str(service_manager.user_service_file)
    assert "/etc/systemd/system" in str(service_manager.system_service_file)


def test_get_redis_config(service_manager):
    """Test Redis config retrieval from environment."""
    with patch.dict(os.environ, {"REDIS_HOST": "test-host", "REDIS_PORT": "1234"}):
        host, port = service_manager.get_redis_config()
        assert host == "test-host"
        assert port == "1234"

    with patch.dict(os.environ, {}, clear=True):
        host, port = service_manager.get_redis_config()
        assert host == "localhost"
        assert port == "6379"


def test_render_template(service_manager, tmp_path):
    """Test template rendering logic."""
    template_file = tmp_path / "test.template"
    template_file.write_text("User={{USER}}\nExec={{EXEC_START}}")

    variables = {"USER": "testuser", "EXEC_START": "/usr/bin/desto"}
    rendered = service_manager.render_template(template_file, variables)

    assert "User=testuser" in rendered
    assert "Exec=/usr/bin/desto" in rendered


@patch("subprocess.run")
def test_is_systemd_available(mock_run, service_manager):
    """Test systemd availability check."""
    mock_run.return_value = MagicMock(returncode=0)
    assert service_manager.is_systemd_available() is True

    mock_run.side_effect = FileNotFoundError
    assert service_manager.is_systemd_available() is False


@patch("shutil.which")
def test_get_desto_path(mock_which, service_manager):
    """Test desto path discovery."""
    mock_which.return_value = "/usr/local/bin/desto"
    assert service_manager.get_desto_path() == "/usr/local/bin/desto"

    mock_which.return_value = None
    path = service_manager.get_desto_path()
    assert "python" in path
    assert "-m desto" in path
