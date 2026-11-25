"""Characterization tests for every way desto starts a tmux session.

desto launches sessions from four places: the shared service used by the web
dashboard and the TUI, the CLI (single command and chain), and the hook that
``at`` runs for scheduled jobs. These tests run each path against real tmux and
Redis and check the behaviour they should all share, so that merging them into
one launch path can be done safely.

Known differences between the paths are marked ``xfail(strict=True)``: when a
fix makes one pass, the marker has to be removed, which keeps this file an
up-to-date record of how the paths differ.
"""

import os
import shutil
import subprocess
import sys
import time
import uuid

import pytest

from desto.redis.client import DestoRedisClient

pytestmark = pytest.mark.skipif(not shutil.which("tmux"), reason="tmux not available")


@pytest.fixture(scope="module")
def redis_client():
    client = DestoRedisClient()
    if not client.is_connected():
        pytest.skip("Redis not available")
    return client


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    scripts_dir = tmp_path / "scripts"
    log_dir.mkdir()
    scripts_dir.mkdir()
    monkeypatch.setenv("DESTO_LOGS_DIR", str(log_dir))
    monkeypatch.setenv("DESTO_SCRIPTS_DIR", str(scripts_dir))
    return log_dir, scripts_dir


@pytest.fixture
def session_name(redis_client):
    name = f"launchtest-{uuid.uuid4().hex[:8]}"
    yield name
    subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)
    for key in redis_client.redis.scan_iter(f"*{name}*"):
        redis_client.redis.delete(key)


def tmux_alive(name):
    return subprocess.run(["tmux", "has-session", "-t", name], capture_output=True).returncode == 0


def wait_until(predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return predicate()


def redis_session(name):
    from desto.redis.session_manager import SessionManager

    return SessionManager(DestoRedisClient()).get_session_by_name(name)


def wait_for_end(name, log_file):
    """Wait until tmux has exited and the completion hook has recorded a final status."""
    assert wait_until(lambda: not tmux_alive(name)), "tmux session did not exit"
    assert wait_until(lambda: redis_session(name) is not None and redis_session(name).status.value in ("finished", "failed")), "no final status in Redis"
    assert log_file.exists()
    return log_file.read_text(), redis_session(name)


# --- Launchers: each starts `command` in a session called `name` and returns the log file --------


def launch_service(name, command, dirs):
    from desto.core.service import DestoService

    log_dir, scripts_dir = dirs
    service = DestoService(log_dir=log_dir, scripts_dir=scripts_dir)
    assert service.start_tmux_session(name, command)
    return service.get_log_file(name)


def launch_cli(name, command, dirs):
    from desto.cli.session_manager import CLISessionManager

    log_dir, scripts_dir = dirs
    manager = CLISessionManager(log_dir=log_dir, scripts_dir=scripts_dir)
    assert manager.start_session(name, command)
    return manager.get_log_file(name)


def launch_hook(name, command, dirs):
    log_dir, _ = dirs
    result = subprocess.run([sys.executable, "-m", "desto.hooks.start_scheduled_session", name, command], capture_output=True, text=True, env=os.environ.copy(), timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return log_dir / f"{name}.log"


CLI_NO_FINISH_BANNER = pytest.mark.xfail(strict=True, reason="CLI launch writes no SCRIPT FINISHED banner (plan F1)")

LAUNCHERS = [
    pytest.param(launch_service, id="service"),
    pytest.param(launch_cli, id="cli"),
    pytest.param(launch_hook, id="scheduled-hook"),
]


@pytest.mark.parametrize("launch", LAUNCHERS)
def test_output_reaches_log_and_success_is_recorded(launch, dirs, session_name):
    log_file = launch(session_name, "echo hello-from-desto", dirs)
    text, session = wait_for_end(session_name, log_file)
    assert "hello-from-desto" in text
    assert session.status.value == "finished"


@pytest.mark.parametrize("launch", LAUNCHERS)
def test_failure_is_recorded_with_exit_code(launch, dirs, session_name):
    log_file = launch(session_name, "echo about-to-fail; exit 3", dirs)
    text, session = wait_for_end(session_name, log_file)
    assert "about-to-fail" in text
    assert session.status.value == "failed"


@pytest.mark.parametrize(
    "launch",
    [
        pytest.param(launch_service, id="service"),
        pytest.param(launch_cli, id="cli", marks=CLI_NO_FINISH_BANNER),
        pytest.param(launch_hook, id="scheduled-hook"),
    ],
)
def test_log_has_start_and_finish_banners(launch, dirs, session_name):
    log_file = launch(session_name, "exit 3", dirs)
    text, _ = wait_for_end(session_name, log_file)
    assert "=== SCRIPT STARTING" in text
    assert "=== SCRIPT FINISHED" in text
    assert "exit code: 3" in text


@pytest.mark.parametrize(
    "launch",
    [
        pytest.param(launch_service, id="service"),
        pytest.param(launch_cli, id="cli", marks=CLI_NO_FINISH_BANNER),
    ],
)
def test_relaunch_appends_to_existing_log(launch, dirs, session_name):
    log_file = launch(session_name, "echo first-run", dirs)
    wait_for_end(session_name, log_file)
    for key in DestoRedisClient().redis.scan_iter(f"*{session_name}*"):
        DestoRedisClient().redis.delete(key)
    launch(session_name, "echo second-run", dirs)
    text, _ = wait_for_end(session_name, log_file)
    assert "first-run" in text and "second-run" in text
    assert text.count("=== SCRIPT FINISHED") == 2


# --- Killing -------------------------------------------------------------------------------------


def test_service_kill_stops_tmux(dirs, session_name):
    from desto.core.service import DestoService

    log_dir, scripts_dir = dirs
    service = DestoService(log_dir=log_dir, scripts_dir=scripts_dir)
    assert service.start_tmux_session(session_name, "sleep 60")
    assert wait_until(lambda: tmux_alive(session_name))
    assert service.kill_session(session_name)
    assert wait_until(lambda: not tmux_alive(session_name))


@pytest.mark.xfail(strict=True, reason="`desto-cli sessions kill` marks the session finished but leaves tmux running (plan F3)")
def test_cli_kill_stops_tmux(dirs, session_name):
    from desto.cli.session_manager import CLISessionManager

    log_dir, scripts_dir = dirs
    manager = CLISessionManager(log_dir=log_dir, scripts_dir=scripts_dir)
    assert manager.start_session(session_name, "sleep 60")
    assert wait_until(lambda: tmux_alive(session_name))
    assert manager.kill_session(session_name)
    assert wait_until(lambda: not tmux_alive(session_name), timeout=3)


# --- Chains --------------------------------------------------------------------------------------


def test_service_chain_runs_every_step(dirs, session_name):
    from desto.core import scripts
    from desto.core.service import DestoService

    log_dir, scripts_dir = dirs
    for i in (1, 2):
        (scripts_dir / f"step{i}.sh").write_text(f"#!/bin/bash\necho step-{i}-ran\n")
    service = DestoService(log_dir=log_dir, scripts_dir=scripts_dir)
    command = scripts.chain_command([(scripts_dir / "step1.sh", ""), (scripts_dir / "step2.sh", "")], service.python_executable)
    assert service.start_tmux_session(session_name, command)
    text, session = wait_for_end(session_name, service.get_log_file(session_name))
    assert "step-1-ran" in text and "step-2-ran" in text
    assert session.status.value == "finished"


def test_cli_chain_runs_every_step(dirs):
    from desto.cli.session_manager import CLISessionManager

    log_dir, scripts_dir = dirs
    for i in (1, 2):
        (scripts_dir / f"step{i}.sh").write_text(f"#!/bin/bash\necho step-{i}-ran\n")
    manager = CLISessionManager(log_dir=log_dir, scripts_dir=scripts_dir)
    name = manager.start_chain_session([["step1.sh"], ["step2.sh"]])
    assert name
    try:
        text, session = wait_for_end(name, manager.get_log_file(name))
        assert "step-1-ran" in text and "step-2-ran" in text
        assert session.status.value == "finished"
    finally:
        subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)
        for key in DestoRedisClient().redis.scan_iter(f"*{name}*"):
            DestoRedisClient().redis.delete(key)
