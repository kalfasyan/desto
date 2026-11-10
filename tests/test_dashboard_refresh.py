"""Tests for the cheaper dashboard refresh, status filter, exit codes and re-run."""

import os
from unittest.mock import MagicMock, Mock, patch

import pytest

from desto.app.sessions import TmuxManager

pytestmark = pytest.mark.skipif(os.getenv("CI") == "true", reason="Redis is not available on GitHub Actions")


@pytest.fixture
def tmux(tmp_path):
    with patch("desto.app.sessions.DestoRedisClient") as mock_redis_class:
        client = Mock()
        client.is_connected.return_value = True
        client.redis = MagicMock()
        client.redis.scan_iter.return_value = []
        mock_redis_class.return_value = client
        manager = TmuxManager(MagicMock(), MagicMock(), log_dir=tmp_path, scripts_dir=tmp_path)
    return manager


def _jobs_redis(jobs):
    redis = MagicMock()
    redis.scan_iter.return_value = [f"desto:job:{j['job_id']}" for j in jobs]
    pipe = MagicMock()
    pipe.execute.return_value = jobs
    redis.pipeline.return_value = pipe
    return redis


def test_job_info_reads_all_jobs_in_one_batch(tmux):
    tmux.redis_client.redis = _jobs_redis(
        [
            {"job_id": "a", "session_id": "s1", "status": "failed", "exit_code": "", "error_message": "Job exited with code 3", "command": "echo a"},
            {"job_id": "b", "session_id": "s2", "status": "finished", "exit_code": "0", "command": "echo b"},
            {"job_id": "c", "session_id": "s3", "status": "running", "command": "sleep 9"},
        ]
    )
    info = tmux._job_info_by_session()
    assert info["s1"] == {"status": "failed", "exit_code": "3", "command": "echo a"}
    assert info["s2"]["status"] == "finished"
    assert info["s3"]["status"] == "running"
    tmux.redis_client.redis.pipeline.return_value.execute.assert_called_once()


@pytest.mark.parametrize(
    "session,active,job_info,expected",
    [
        ({"status": "finished"}, False, {}, ("finished", "✅ Finished")),
        ({"status": "failed", "session_id": "s"}, False, {"s": {"status": "failed", "exit_code": "2"}}, ("failed", "❌ Failed · exit 2")),
        ({"status": "running"}, True, {}, ("running", "🟡 Running")),
        ({"status": "running"}, False, {}, ("failed", "❌ Failed (tmux closed)")),
        ({"status": "running", "end_time": "2025-01-01T00:00:00"}, False, {}, ("finished", "✅ Finished")),
        ({"status": "scheduled"}, False, {}, ("scheduled", "📅 Scheduled")),
        ({"status": "running", "session_id": "s"}, True, {"s": {"status": "finished"}}, ("finished", "✅ Finished")),
    ],
)
def test_classify_session(session, active, job_info, expected):
    category, label, _ = TmuxManager._classify_session("x", session, active, job_info)
    assert (category, label) == expected


def test_counts_match_rows_and_skip_scheduled(tmux):
    sessions = {
        "a": {"status": "finished"},
        "b": {"status": "failed"},
        "c": {"status": "running"},
        "d": {"status": "scheduled"},
    }
    counts = tmux._count_by_category(sessions, tmux_active={"c"}, job_info={})
    assert counts == {"total": 3, "running": 1, "finished": 1, "failed": 1}


def test_periodic_refresh_skips_render_when_nothing_changed(tmux):
    tmux.get_all_sessions_status = Mock(return_value={"a": {"status": "finished"}})
    tmux.check_sessions = Mock(return_value={})
    tmux._job_info_by_session = Mock(return_value={})
    tmux._get_scheduled_jobs_with_metadata = Mock(return_value=[])
    tmux.add_to_sessions_container = Mock()
    tmux.clear_sessions_container = Mock()

    tmux.update_sessions_status(force=False)
    tmux.update_sessions_status(force=False)
    assert tmux.add_to_sessions_container.call_count == 1

    tmux.get_all_sessions_status.return_value = {"a": {"status": "finished"}, "b": {"status": "running"}}
    tmux.update_sessions_status(force=False)
    assert tmux.add_to_sessions_container.call_count == 2

    tmux.update_sessions_status(force=True)
    assert tmux.add_to_sessions_container.call_count == 3


def test_set_status_filter_toggles(tmux):
    tmux.update_sessions_status = Mock()
    tmux.set_status_filter("failed")
    assert tmux.status_filter == "failed"
    tmux.set_status_filter("failed")
    assert tmux.status_filter is None
    tmux.set_status_filter("running")
    tmux.set_status_filter(None)
    assert tmux.status_filter is None


def test_rerun_uses_next_free_name(tmux):
    tmux.check_sessions = Mock(return_value={})
    tmux.desto_manager = MagicMock()
    tmux.desto_manager.session_manager.list_all_sessions.return_value = [Mock(session_name="train"), Mock(session_name="train-2")]
    tmux.start_tmux_session = Mock()
    tmux.update_sessions_status = Mock()

    tmux.rerun_session("train-2", "python train.py")
    tmux.start_tmux_session.assert_called_once()
    assert tmux.start_tmux_session.call_args[0][:2] == ("train-3", "python train.py")

    tmux.start_tmux_session.reset_mock()
    tmux.desto_manager.session_manager.list_all_sessions.return_value = [Mock(session_name="backup-2025")]
    tmux.rerun_session("backup-2025", "echo hi")
    assert tmux.start_tmux_session.call_args[0][0] == "backup-2025-2"
