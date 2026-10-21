"""Tests for the desto.hooks helpers that run inside tmux sessions and ``at`` jobs.

These run the hooks as subprocesses from an unrelated working directory, the way tmux
and ``at`` invoke them, so they fail if the hooks only work from a source checkout.
"""

import subprocess
import sys
import uuid

import pytest

from desto.redis.client import DestoRedisClient
from desto.redis.desto_manager import DestoManager
from desto.redis.models import SessionStatus


def run_hook(module, *args, cwd):
    return subprocess.run([sys.executable, "-m", f"desto.hooks.{module}", *args], cwd=cwd, capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("module", ["mark_job_finished", "start_scheduled_session"])
def test_hook_is_runnable_outside_source_tree(module, tmp_path):
    """Missing arguments should hit the hook's usage check, not an import or file-not-found error."""
    result = run_hook(module, cwd=tmp_path)

    assert result.returncode == 1
    assert "No module named" not in result.stderr
    assert "can't open file" not in result.stderr


@pytest.fixture
def manager():
    client = DestoRedisClient()
    if not client.is_connected():
        pytest.skip("Redis not available")
    yield DestoManager(client)


@pytest.mark.parametrize("exit_code, expected", [(0, SessionStatus.FINISHED), (3, SessionStatus.FAILED)])
def test_mark_job_finished_records_exit_status(manager, tmp_path, exit_code, expected):
    session_name = f"test-hook-{uuid.uuid4().hex[:8]}"
    session, job = manager.start_session_with_job(session_name=session_name, command="true", script_path="true")
    try:
        result = run_hook("mark_job_finished", session_name, str(exit_code), cwd=tmp_path)

        assert result.returncode == 0, result.stderr
        assert manager.session_manager.get_session(session.session_id).status == expected
    finally:
        manager.redis.redis.delete(f"desto:session:{session.session_id}", f"desto:job:{job.job_id}")
