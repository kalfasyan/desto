"""Tests for the per-session metrics sampler (desto.core.session_metrics)."""

import fnmatch
import json
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from desto.core import session_metrics as sm
from desto.core.formatting import format_bytes, metrics_key, usage_cells
from desto.store.models import DestoSession, SessionStatus
from desto.store.sqlite_store import METRIC_COLUMNS, SQLiteStore


class FakeRedis:
    """Just enough of redis.Redis (decode_responses=True) for the sampler."""

    def __init__(self):
        self.data = {}
        self.ttl = {}

    # strings / keys
    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return None
        self.data[key] = str(value)
        if ex:
            self.ttl[key] = ex
        return True

    def get(self, key):
        return self.data.get(key)

    def expire(self, key, seconds):
        if key in self.data:
            self.ttl[key] = seconds
        return True

    def delete(self, key):
        self.data.pop(key, None)

    def scan_iter(self, match="*", count=None):
        return [k for k in list(self.data) if fnmatch.fnmatchcase(k, match)]

    # hashes
    def hset(self, key, mapping):
        h = self.data.setdefault(key, {})
        h.update({k: str(v) for k, v in mapping.items()})

    def hgetall(self, key):
        return dict(self.data.get(key, {}))

    def hmget(self, key, *fields):
        h = self.data.get(key, {})
        return [h.get(f) for f in fields]

    def hincrby(self, key, field, amount):
        h = self.data.setdefault(key, {})
        h[field] = str(int(h.get(field, 0)) + amount)

    # lists
    def rpush(self, key, value):
        self.data.setdefault(key, []).append(value)

    def ltrim(self, key, start, end):
        items = self.data.get(key, [])
        n = len(items)
        start = max(0, n + start) if start < 0 else start
        end = n + end if end < 0 else end
        self.data[key] = items[start : end + 1]

    def lrange(self, key, start, end):
        items = self.data.get(key, [])
        return items[start:] if end == -1 else items[start : end + 1]

    def pipeline(self, transaction=False):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis):
        self.redis, self.calls = redis, []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self

        return call

    def execute(self):
        results = [getattr(self.redis, name)(*args, **kwargs) for name, args, kwargs in self.calls]
        self.calls = []
        return results


class FakeProc:
    """A psutil.Process stand-in with fixed figures."""

    def __init__(
        self,
        pid,
        cpu=0.0,
        rss=0,
        threads=1,
        user=0.0,
        system=0.0,
        children_user=0.0,
        children_system=0.0,
        read=0,
        write=0,
    ):
        self.pid = pid
        self._cpu, self._rss, self._threads = cpu, rss, threads
        self._times = SimpleNamespace(
            user=user, system=system, children_user=children_user, children_system=children_system
        )
        self._io = SimpleNamespace(read_bytes=read, write_bytes=write)

    def oneshot(self):
        import contextlib

        return contextlib.nullcontext()

    def cpu_percent(self, interval=None):
        return self._cpu

    def memory_info(self):
        return SimpleNamespace(rss=self._rss)

    def num_threads(self):
        return self._threads

    def cpu_times(self):
        return self._times

    def io_counters(self):
        return self._io


class World:
    """Fake tmux panes and process table that a test changes between ticks."""

    def __init__(self, monkeypatch):
        self.panes = {}
        self.procs = {}
        self.parents = {}
        monkeypatch.setattr(sm, "list_panes", lambda: {k: (c, list(p)) for k, (c, p) in self.panes.items()})
        monkeypatch.setattr(sm, "process_table", self.table)

    def add(self, proc, ppid):
        self.procs[proc.pid] = proc
        self.parents[proc.pid] = ppid

    def table(self):
        children = {}
        for pid, ppid in self.parents.items():
            children.setdefault(ppid, []).append(pid)
        return children, dict(self.procs)


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def world(monkeypatch):
    return World(monkeypatch)


def make_sampler(redis, clock, sqlite_store=None):
    return sm.SessionMetricsSampler(redis, sqlite_store=sqlite_store, interval=5, retention_seconds=3600, clock=clock)


def add_desto_session(redis, session_id, name, status="running", start="2026-11-23T10:00:00"):
    redis.hset(
        f"desto:session:{session_id}",
        {"session_id": session_id, "session_name": name, "status": status, "start_time": start},
    )


# --- Process tree --------------------------------------------------------------------------


def test_tree_pids_walks_descendants_once():
    children = {1: [2, 3], 2: [4], 4: [5], 9: [10]}
    assert sorted(sm.tree_pids([1], children)) == [1, 2, 3, 4, 5]
    # A pid listed as its own descendant must not loop forever
    assert sorted(sm.tree_pids([1], {1: [2], 2: [1]})) == [1, 2]


def test_measure_sums_the_tree_and_counts_reaped_children_cpu():
    procs = {
        1: FakeProc(
            1, cpu=10, rss=100, threads=1, user=1, system=1, children_user=3, children_system=1, read=5, write=7
        ),
        2: FakeProc(2, cpu=90, rss=900, threads=4, user=10, system=2, read=1, write=3),
    }
    s = sm.measure([1, 2, 3], procs, now=5.0)  # pid 3 has already gone
    assert (s.cpu, s.rss, s.threads, s.procs) == (100, 1000, 5, 2)
    assert s.cpu_seconds == pytest.approx(18)
    assert (s.read_bytes, s.write_bytes) == (6, 10)


def test_measure_on_a_real_process_tree():
    child = subprocess.Popen([sys.executable, "-c", "import time; x = bytearray(30 * 1024 * 1024); time.sleep(30)"])
    try:
        time.sleep(1.0)
        children, procs = sm.process_table()
        s = sm.measure(sm.tree_pids([child.pid], children), procs, now=time.time())
        assert s.procs == 1
        assert s.rss > 25 * 1024 * 1024
        assert s.threads >= 1
    finally:
        child.kill()
        child.wait()


# --- Sampler ---------------------------------------------------------------------------------


def test_tick_stores_summary_and_raw_points_keyed_by_session_id(world):
    redis, clock = FakeRedis(), Clock()
    add_desto_session(redis, "sid-1", "train")
    world.panes = {"train": ("1700000000", [100])}
    world.add(FakeProc(100, cpu=5, rss=1000), ppid=1)
    world.add(FakeProc(101, cpu=95, rss=9000, threads=8), ppid=100)

    sampler = make_sampler(redis, clock)
    samples = sampler.tick()

    assert list(samples) == ["sid-1"]
    summary = redis.hgetall(sm.summary_key("sid-1"))
    assert summary["session_name"] == "train"
    assert summary["active"] == "1"
    assert float(summary["cpu"]) == 100
    assert int(summary["rss"]) == 10000
    assert summary["samples"] == "1"
    raw = [json.loads(p) for p in redis.lrange(sm.tier_key("sid-1", "raw"), 0, -1)]
    assert raw[0]["rss"] == 10000
    assert redis.ttl[sm.summary_key("sid-1")] == 3600


def test_sessions_desto_does_not_know_use_name_and_creation_time(world):
    redis = FakeRedis()
    add_desto_session(redis, "old", "adhoc", status="finished")
    world.panes = {"adhoc": ("1700000000", [100])}
    world.add(FakeProc(100, rss=10), ppid=1)

    samples = make_sampler(redis, Clock()).tick()
    assert list(samples) == ["tmux-adhoc-1700000000"]
    assert metrics_key("adhoc", {"created": 1700000000}) == "tmux-adhoc-1700000000"


def test_peaks_and_totals_never_go_down(world):
    redis, clock = FakeRedis(), Clock()
    world.panes = {"job": ("1", [100])}
    world.add(FakeProc(100, rss=5000, user=10), ppid=1)
    sampler = make_sampler(redis, clock)
    sampler.tick()
    world.procs[100] = FakeProc(100, rss=1000, user=4)
    clock.t += 5
    sampler.tick()

    summary = redis.hgetall(sm.summary_key("tmux-job-1"))
    assert int(summary["rss"]) == 1000
    assert int(summary["peak_rss"]) == 5000
    assert float(summary["cpu_seconds"]) == 10


def test_coarse_tiers_aggregate_per_bucket(world):
    redis, clock = FakeRedis(), Clock(t=6000.0)  # a 1 minute bucket boundary
    world.panes = {"job": ("1", [100])}
    sampler = make_sampler(redis, clock)
    for cpu, rss in [(10, 100), (30, 300), (50, 200)]:
        world.procs.clear()
        world.add(FakeProc(100, cpu=cpu, rss=rss), ppid=1)
        sampler.tick()
        clock.t += 20
    # Still inside the first minute's bucket: nothing flushed yet
    assert redis.lrange(sm.tier_key("tmux-job-1", "1m"), 0, -1) == []
    sampler.tick()  # t = 6060, next bucket: the first one is written
    (point,) = [json.loads(p) for p in redis.lrange(sm.tier_key("tmux-job-1", "1m"), 0, -1)]
    assert point["t"] == 6000.0
    assert point["cpu"] == 30.0
    assert point["cpu_max"] == 50
    assert point["rss"] == 200
    assert point["rss_max"] == 300


def test_raw_tier_is_capped(world, monkeypatch):
    monkeypatch.setattr(sm, "TIERS", (("raw", 0, 3), ("1m", 60, 2)))
    redis, clock = FakeRedis(), Clock()
    world.panes = {"job": ("1", [100])}
    world.add(FakeProc(100), ppid=1)
    sampler = make_sampler(redis, clock)
    for _ in range(10):
        sampler.tick()
        clock.t += 5
    assert len(redis.lrange(sm.tier_key("tmux-job-1", "raw"), 0, -1)) == 3


def test_ended_session_is_marked_and_archived_to_sqlite(world, tmp_path):
    redis, clock = FakeRedis(), Clock()
    store = SQLiteStore(db_path=str(tmp_path / "desto.db"), enabled=True)
    store.save_session(DestoSession(session_id="sid-1", session_name="train", status=SessionStatus.RUNNING))
    add_desto_session(redis, "sid-1", "train")
    world.panes = {"train": ("1", [100])}
    world.add(FakeProc(100, cpu=50, rss=4096, user=2, system=1, read=10, write=20), ppid=1)
    sampler = make_sampler(redis, clock, sqlite_store=store)
    sampler.tick()

    world.panes = {}
    clock.t += 5
    sampler.tick()

    summary = redis.hgetall(sm.summary_key("sid-1"))
    assert summary["active"] == "0"
    assert summary["ended_ts"]
    # The partial one-minute bucket is flushed when the session ends
    assert len(redis.lrange(sm.tier_key("sid-1", "1m"), 0, -1)) == 1
    assert store.get_session_metrics("sid-1") == {
        "peak_rss_bytes": 4096,
        "cpu_seconds": 3.0,
        "read_bytes": 10,
        "write_bytes": 20,
        "max_processes": 1,
    }
    # Saving the session again (status change) keeps the totals
    store.save_session(DestoSession(session_id="sid-1", session_name="train", status=SessionStatus.FINISHED))
    assert store.get_session_metrics("sid-1")["peak_rss_bytes"] == 4096


def test_new_sampler_finishes_sessions_an_earlier_one_left_active(world, tmp_path):
    redis, clock = FakeRedis(), Clock()
    world.panes = {"job": ("1", [100])}
    world.add(FakeProc(100, rss=10), ppid=1)
    make_sampler(redis, clock).tick()  # this sampler then "dies"

    world.panes = {}
    clock.t += 60
    make_sampler(redis, clock).tick()
    assert redis.hgetall(sm.summary_key("tmux-job-1"))["active"] == "0"


def test_only_the_lease_holder_samples():
    redis = FakeRedis()
    a, b = make_sampler(redis, Clock()), make_sampler(redis, Clock())
    assert a.acquire_lease()
    assert not b.acquire_lease()
    assert a.acquire_lease()  # renewal
    a.release_lease()
    assert b.acquire_lease()


def test_read_history_merges_tiers_coarse_to_fine():
    redis = FakeRedis()
    for t in (0, 900, 1800):
        redis.rpush(sm.tier_key("k", "15m"), json.dumps({"t": t, "cpu": 1, "rss": 1, "rss_max": 2}))
    for t in (1800, 1860, 1920):
        redis.rpush(sm.tier_key("k", "1m"), json.dumps({"t": t, "cpu": 2, "rss": 2, "rss_max": 3}))
    for t in (1920.0, 1925.0):
        redis.rpush(sm.tier_key("k", "raw"), json.dumps({"t": t, "cpu": 3, "rss": 3}))

    points = sm.read_history(redis, "k")
    assert [p["t"] for p in points] == [0, 900, 1800, 1860, 1920.0, 1925.0]
    assert points[-1]["rss_max"] == 3  # raw points get rss_max = rss


# --- Formatting -------------------------------------------------------------------------------


def test_usage_cells_for_running_and_ended_sessions():
    assert usage_cells(None) == ("", "")
    assert usage_cells({"active": "1", "cpu": "97.4", "rss": str(314 * 1024**2)}) == ("97%", "314 MB")
    assert usage_cells({"active": "0", "cpu_seconds": "65.2", "peak_rss": str(3 * 1024**3)}) == (
        "1m 5s cpu",
        "peak 3.0 GB",
    )


@pytest.mark.parametrize(
    "value, expected", [(512, "512 B"), (2048, "2 KB"), (5 * 1024**2, "5 MB"), (1.5 * 1024**3, "1.5 GB"), ("x", "N/A")]
)
def test_format_bytes(value, expected):
    assert format_bytes(value) == expected


def test_sqlite_migration_adds_metric_columns_to_an_old_database(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, session_name TEXT NOT NULL, tmux_session_name TEXT NOT NULL DEFAULT '',"
        " status TEXT NOT NULL DEFAULT 'starting', start_time TEXT, end_time TEXT, last_heartbeat TEXT, job_ids TEXT DEFAULT '',"
        " tmux_active INTEGER DEFAULT 0, at_job_id TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        " updated_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    conn.commit()
    conn.close()

    store = SQLiteStore(db_path=str(path), enabled=True)
    columns = {row[1] for row in store._get_connection().execute("PRAGMA table_info(sessions)")}
    assert set(METRIC_COLUMNS) <= columns
