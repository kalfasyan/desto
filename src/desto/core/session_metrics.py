"""Per-session resource usage: CPU, memory, threads, CPU time and disk IO of each tmux session's processes.

One ``SessionMetricsSampler`` samples every tmux session on the machine. Each tick it lists the tmux
panes, walks the process tree under every pane, sums the figures per session and writes them to Redis.
A Redis lease makes sure only one sampler writes, even with the dashboard, the terminal UI and
``desto-cli monitor`` running at the same time.

History is kept at three resolutions so long sessions stay bounded in memory and still show their
whole run (see ``TIERS``): every sample for the last hour, one-minute points for the last day and
fifteen-minute points for the last 30 days. When a session ends, its totals (peak memory, CPU time,
disk IO, peak process count) are copied to SQLite, if enabled, so session history keeps them.

Redis layout, where <key> is the desto session id, or ``tmux-<name>-<created>`` for tmux sessions
desto did not start:

- ``desto:metrics:<key>:summary`` hash: the latest figures, peaks and totals
- ``desto:metrics:<key>:raw`` / ``:1m`` / ``:15m`` lists: JSON points, oldest first
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

import psutil
from loguru import logger

from desto.core.formatting import decode_hash, external_metrics_key

KEY_PREFIX = "desto:metrics:"
LOCK_KEY = "desto:metrics:lock"

# (name, bucket width in seconds, points kept). Width 0 = every sample.
TIERS = (("raw", 0, 720), ("1m", 60, 1440), ("15m", 900, 2880))

# Summary fields that only ever grow: kept as the max of the stored and the new value, so a sampler
# restart or a child process that has exited but not yet been reaped never makes them go backwards.
_MONOTONIC = ("peak_rss", "max_procs", "max_threads", "cpu_seconds", "read_bytes", "write_bytes")


def summary_key(key: str) -> str:
    return f"{KEY_PREFIX}{key}:summary"


def tier_key(key: str, tier: str) -> str:
    return f"{KEY_PREFIX}{key}:{tier}"


external_key = external_metrics_key


@dataclass
class Sample:
    """Figures for one session's process tree at one moment, summed over its processes."""

    ts: float
    cpu: float = 0.0  # percent of one core; 250 = two and a half cores busy
    rss: int = 0  # bytes
    procs: int = 0
    threads: int = 0
    cpu_seconds: float = 0.0  # user + system, including children that already exited
    read_bytes: int = 0
    write_bytes: int = 0

    def point(self) -> dict:
        return {"t": round(self.ts, 1), "cpu": round(self.cpu, 1), "rss": self.rss, "procs": self.procs, "threads": self.threads, "cpu_s": round(self.cpu_seconds, 2), "rd": self.read_bytes, "wr": self.write_bytes}


@dataclass
class _Bucket:
    """Running aggregate of the samples that fall into one coarse-tier bucket."""

    start: float
    n: int = 0
    cpu_sum: float = 0.0
    cpu_max: float = 0.0
    rss_sum: int = 0
    rss_max: int = 0
    procs: int = 0
    threads: int = 0
    last: Optional[Sample] = None

    def add(self, s: Sample) -> None:
        self.n += 1
        self.cpu_sum += s.cpu
        self.cpu_max = max(self.cpu_max, s.cpu)
        self.rss_sum += s.rss
        self.rss_max = max(self.rss_max, s.rss)
        self.procs = max(self.procs, s.procs)
        self.threads = max(self.threads, s.threads)
        self.last = s

    def point(self) -> dict:
        last = self.last
        return {
            "t": self.start,
            "cpu": round(self.cpu_sum / self.n, 1),
            "cpu_max": round(self.cpu_max, 1),
            "rss": self.rss_sum // self.n,
            "rss_max": self.rss_max,
            "procs": self.procs,
            "threads": self.threads,
            "cpu_s": round(last.cpu_seconds, 2),
            "rd": last.read_bytes,
            "wr": last.write_bytes,
        }


@dataclass
class _Tracked:
    """What the sampler remembers about a session between ticks."""

    key: str
    name: str
    session_id: str  # empty for tmux sessions desto did not start
    first_ts: float
    buckets: dict = field(default_factory=dict)  # tier name -> _Bucket
    peaks: dict = field(default_factory=dict)  # _MONOTONIC field -> value


# --- Reading the process table -----------------------------------------------------------


def list_panes() -> dict[str, tuple[str, list[int]]]:
    """Return {session_name: (session_created, [pane pids])} for every tmux session, or {} without a server."""
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{session_name}\t#{session_created}\t#{pane_pid}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    panes: dict[str, tuple[str, list[int]]] = {}
    for line in result.stdout.splitlines():
        try:
            name, created, pid = line.rsplit("\t", 2)
            panes.setdefault(name, (created, []))[1].append(int(pid))
        except ValueError:
            continue
    return panes


def process_table() -> tuple[dict[int, list[int]], dict[int, psutil.Process]]:
    """One pass over the process table: ({ppid: [child pids]}, {pid: Process}).

    psutil.process_iter caches its Process objects between calls, so cpu_percent() on them measures
    the time since the previous tick without blocking.
    """
    children: dict[int, list[int]] = {}
    procs: dict[int, psutil.Process] = {}
    for p in psutil.process_iter(["ppid"]):
        procs[p.pid] = p
        children.setdefault(p.info["ppid"], []).append(p.pid)
    return children, procs


def tree_pids(roots: list[int], children: dict[int, list[int]]) -> list[int]:
    """The root pids and all their descendants."""
    seen, stack = [], list(roots)
    visited = set()
    while stack:
        pid = stack.pop()
        if pid in visited:
            continue
        visited.add(pid)
        seen.append(pid)
        stack.extend(children.get(pid, ()))
    return seen


def measure(pids: list[int], procs: dict[int, psutil.Process], now: float) -> Sample:
    """Sum the figures of the given processes. Processes that vanish or deny access are skipped."""
    s = Sample(ts=now)
    for pid in pids:
        p = procs.get(pid)
        if p is None:
            continue
        try:
            with p.oneshot():
                cpu = p.cpu_percent(interval=None)
                rss = p.memory_info().rss
                threads = p.num_threads()
                t = p.cpu_times()
                # children_* = CPU time of children this process has already waited for. Summed over the
                # live tree it counts every finished descendant exactly once.
                cpu_seconds = t.user + t.system + getattr(t, "children_user", 0.0) + getattr(t, "children_system", 0.0)
                io = p.io_counters() if hasattr(p, "io_counters") else None
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        except psutil.AccessDenied:
            continue
        s.cpu += cpu
        s.rss += rss
        s.threads += threads
        s.cpu_seconds += cpu_seconds
        s.procs += 1
        if io is not None:
            s.read_bytes += io.read_bytes
            s.write_bytes += io.write_bytes
    return s


# --- The sampler -------------------------------------------------------------------------


class SessionMetricsSampler:
    """Samples every tmux session's process tree and stores the figures in Redis.

    Args:
        redis: a redis.Redis client with decode_responses=True.
        sqlite_store: optional SQLiteStore; ended sessions' totals are saved there.
        interval: seconds between samples.
        retention_seconds: how long metrics keys live after their last update.
    """

    def __init__(self, redis, sqlite_store=None, interval: float = 5.0, retention_seconds: int = 7 * 86400, clock: Callable[[], float] = time.time):
        self.redis = redis
        self.sqlite_store = sqlite_store
        self.interval = max(1.0, float(interval))
        self.retention_seconds = int(retention_seconds)
        self.clock = clock
        self.token = uuid.uuid4().hex
        self._tracked: dict[str, _Tracked] = {}
        self._adopt = True  # on the first tick, finish sessions an earlier sampler left marked active
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # Lease ------------------------------------------------------------------------------

    def acquire_lease(self) -> bool:
        """Hold the sampler lease, or renew it. Only the holder samples."""
        ttl = int(max(15, self.interval * 3))
        try:
            if self.redis.set(LOCK_KEY, self.token, nx=True, ex=ttl):
                return True
            if self.redis.get(LOCK_KEY) == self.token:
                self.redis.expire(LOCK_KEY, ttl)
                return True
        except Exception as e:
            logger.debug(f"Metrics lease check failed: {e}")
        return False

    def release_lease(self) -> None:
        try:
            if self.redis.get(LOCK_KEY) == self.token:
                self.redis.delete(LOCK_KEY)
        except Exception:
            pass

    # Session ids ------------------------------------------------------------------------

    def _active_session_ids(self) -> dict[str, str]:
        """{session_name: session_id} of the running desto sessions, the newest per name."""
        keys = list(self.redis.scan_iter(match="desto:session:*", count=500))
        if not keys:
            return {}
        pipe = self.redis.pipeline(transaction=False)
        for k in keys:
            pipe.hmget(k, "session_id", "session_name", "status", "start_time")
        best: dict[str, tuple[str, str]] = {}
        for sid, name, status, start in pipe.execute():
            if not sid or not name or status not in ("running", "starting"):
                continue
            if name not in best or (start or "") > best[name][1]:
                best[name] = (sid, start or "")
        return {name: sid for name, (sid, _) in best.items()}

    # One tick ---------------------------------------------------------------------------

    def tick(self) -> dict[str, Sample]:
        """Sample every tmux session once and store the results. Returns {metrics key: Sample}."""
        now = self.clock()
        panes = list_panes()
        children, procs = process_table()
        ids = self._active_session_ids() if panes else {}

        samples: dict[str, Sample] = {}
        current: dict[str, _Tracked] = {}
        for name, (created, roots) in panes.items():
            session_id = ids.get(name, "")
            key = session_id or external_key(name, created)
            tracked = self._tracked.get(key) or _Tracked(key=key, name=name, session_id=session_id, first_ts=now)
            current[key] = tracked
            samples[key] = measure(tree_pids(roots, children), procs, now)

        self._load_peaks([t for k, t in current.items() if k not in self._tracked])
        self._store(current, samples, now)

        ended = [t for k, t in self._tracked.items() if k not in current]
        if self._adopt:
            self._adopt = False
            ended += self._orphans(set(current) | set(self._tracked))
        self._finish(ended, now)
        self._tracked = current
        return samples

    def _orphans(self, live: set) -> list[_Tracked]:
        """Sessions an earlier sampler marked active that are no longer running (it stopped before they ended)."""
        orphans = []
        for skey in self.redis.scan_iter(match=f"{KEY_PREFIX}*:summary", count=500):
            data = decode_hash(self.redis.hgetall(skey) or {})
            key = data.get("key") or skey[len(KEY_PREFIX) : -len(":summary")]
            if data.get("active") != "1" or key in live:
                continue
            t = _Tracked(key=key, name=data.get("session_name", ""), session_id=data.get("session_id", ""), first_ts=float(data.get("first_ts") or 0))
            for f in _MONOTONIC:
                try:
                    t.peaks[f] = float(data[f])
                except (KeyError, ValueError):
                    pass
            orphans.append(t)
        return orphans

    def _load_peaks(self, new: list[_Tracked]) -> None:
        """For sessions first seen by this sampler, pick up totals an earlier sampler stored."""
        if not new:
            return
        pipe = self.redis.pipeline(transaction=False)
        for t in new:
            pipe.hgetall(summary_key(t.key))
        for t, data in zip(new, pipe.execute()):
            data = decode_hash(data or {})
            for f in _MONOTONIC:
                try:
                    t.peaks[f] = float(data[f])
                except (KeyError, ValueError):
                    pass
            if data.get("first_ts"):
                try:
                    t.first_ts = float(data["first_ts"])
                except ValueError:
                    pass

    def _store(self, current: dict[str, _Tracked], samples: dict[str, Sample], now: float) -> None:
        if not current:
            return
        pipe = self.redis.pipeline(transaction=False)
        for key, t in current.items():
            s = samples[key]
            values = {"peak_rss": s.rss, "max_procs": s.procs, "max_threads": s.threads, "cpu_seconds": s.cpu_seconds, "read_bytes": s.read_bytes, "write_bytes": s.write_bytes}
            for f, v in values.items():
                t.peaks[f] = max(t.peaks.get(f, 0), v)

            for tier, width, keep in TIERS:
                lkey = tier_key(key, tier)
                if width == 0:
                    pipe.rpush(lkey, json.dumps(s.point(), separators=(",", ":")))
                    pipe.ltrim(lkey, -keep, -1)
                else:
                    start = now - (now % width)
                    bucket = t.buckets.get(tier)
                    if bucket is not None and bucket.start != start:
                        pipe.rpush(lkey, json.dumps(bucket.point(), separators=(",", ":")))
                        pipe.ltrim(lkey, -keep, -1)
                        bucket = None
                    if bucket is None:
                        bucket = t.buckets[tier] = _Bucket(start=start)
                    bucket.add(s)
                pipe.expire(lkey, self.retention_seconds)

            skey = summary_key(key)
            pipe.hset(
                skey,
                mapping={
                    "key": key,
                    "session_name": t.name,
                    "session_id": t.session_id,
                    "active": "1",
                    "first_ts": t.first_ts,
                    "last_ts": round(now, 1),
                    "cpu": round(s.cpu, 1),
                    "rss": s.rss,
                    "procs": s.procs,
                    "threads": s.threads,
                    **{f: (round(v, 2) if f == "cpu_seconds" else int(v)) for f, v in t.peaks.items()},
                },
            )
            pipe.hincrby(skey, "samples", 1)
            pipe.expire(skey, self.retention_seconds)
        pipe.execute()

    def _finish(self, ended: list[_Tracked], now: float) -> None:
        """Flush partial coarse buckets of sessions that are gone, mark them ended and archive their totals."""
        if not ended:
            return
        pipe = self.redis.pipeline(transaction=False)
        for t in ended:
            for tier, width, keep in TIERS:
                bucket = t.buckets.get(tier)
                if width and bucket is not None and bucket.n:
                    lkey = tier_key(t.key, tier)
                    pipe.rpush(lkey, json.dumps(bucket.point(), separators=(",", ":")))
                    pipe.ltrim(lkey, -keep, -1)
            pipe.hset(summary_key(t.key), mapping={"active": "0", "cpu": 0, "procs": 0, "threads": 0, "rss": 0, "ended_ts": round(now, 1)})
        pipe.execute()

        if self.sqlite_store is not None and getattr(self.sqlite_store, "enabled", False):
            for t in ended:
                if not t.session_id:
                    continue
                try:
                    self.sqlite_store.save_session_metrics(
                        t.session_id,
                        peak_rss_bytes=int(t.peaks.get("peak_rss", 0)),
                        cpu_seconds=float(t.peaks.get("cpu_seconds", 0.0)),
                        read_bytes=int(t.peaks.get("read_bytes", 0)),
                        write_bytes=int(t.peaks.get("write_bytes", 0)),
                        max_processes=int(t.peaks.get("max_procs", 0)),
                    )
                except Exception as e:
                    logger.debug(f"Could not archive metrics of session {t.session_id}: {e}")

    # Loop -------------------------------------------------------------------------------

    def run(self) -> None:
        """Sample until stop() is called. Ticks only while this sampler holds the lease."""
        logger.info(f"Session metrics sampler started (every {self.interval:g}s)")
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                if self.acquire_lease():
                    if self._adopt:
                        # cpu_percent() measures since the previous call, so the first call per process
                        # reads 0. Prime the counters and sample a moment later.
                        self.prime()
                        self._stop.wait(1.0)
                    self.tick()
                else:
                    # Another sampler is writing. Forget our state so a later takeover starts clean.
                    self._tracked = {}
                    self._adopt = True
            except Exception as e:
                logger.debug(f"Session metrics tick failed: {e}")
            self._stop.wait(max(0.0, self.interval - (time.monotonic() - started)))
        self.release_lease()

    def prime(self) -> None:
        """Start the CPU counters of every process in a tmux session."""
        children, procs = process_table()
        for _, roots in list_panes().values():
            for pid in tree_pids(roots, children):
                try:
                    procs[pid].cpu_percent(interval=None)
                except (KeyError, psutil.Error):
                    pass

    def start(self) -> "SessionMetricsSampler":
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self.run, name="desto-metrics", daemon=True)
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval + 5)


_background: Optional[SessionMetricsSampler] = None
_background_lock = threading.Lock()


def start_background_sampler(settings: Optional[dict] = None) -> Optional[SessionMetricsSampler]:
    """Start this process's sampler thread once, using desto's settings. Returns None when disabled or Redis is down."""
    global _background
    with _background_lock:
        if _background is not None:
            return _background
        from desto.app.config import config as default_settings
        from desto.redis.client import DestoRedisClient

        settings = settings or default_settings
        metrics_cfg = settings.get("metrics", {})
        if not metrics_cfg.get("enabled", True):
            logger.info("Session metrics are disabled")
            return None
        client = DestoRedisClient(settings.get("redis"))
        if not client.is_connected():
            return None
        sqlite_store = None
        sqlite_cfg = settings.get("sqlite", {})
        if sqlite_cfg.get("enabled", False):
            from desto.redis.sqlite_store import SQLiteStore

            sqlite_store = SQLiteStore(db_path=sqlite_cfg.get("db_path") or None, enabled=True)
        retention = int(settings.get("redis", {}).get("session_history_days", 7)) * 86400
        _background = SessionMetricsSampler(client.redis, sqlite_store, interval=metrics_cfg.get("interval", 5.0), retention_seconds=retention).start()
        return _background


# --- Reading ------------------------------------------------------------------------------


def read_summaries(redis, keys: list[str]) -> dict[str, dict]:
    """{key: summary dict} for the keys that have one, in one round trip."""
    keys = [k for k in dict.fromkeys(keys) if k]
    if not keys:
        return {}
    pipe = redis.pipeline(transaction=False)
    for k in keys:
        pipe.hgetall(summary_key(k))
    return {k: decode_hash(d) for k, d in zip(keys, pipe.execute()) if d}


def read_history(redis, key: str) -> list[dict]:
    """The session's points oldest first, coarsest tier for the oldest part and finest for the newest.

    Every point has t (epoch seconds), cpu (percent), rss (bytes) and rss_max (bytes).
    """
    pipe = redis.pipeline(transaction=False)
    for tier, _, _ in TIERS:
        pipe.lrange(tier_key(key, tier), 0, -1)
    tiers = []
    for raw in pipe.execute():
        points = []
        for item in raw or []:
            try:
                points.append(json.loads(item))
            except (TypeError, ValueError):
                continue
        tiers.append(points)

    merged: list[dict] = []
    cutoff = float("inf")
    # Finest first: a coarser tier only fills in the time before the finer one starts, with whole
    # buckets (a bucket that overlaps the finer tier is already covered by it).
    for (_, width, _), points in zip(TIERS, tiers):
        older = [p for p in points if p.get("t", 0) + width <= cutoff]
        merged = older + merged
        if points:
            cutoff = min(cutoff, points[0].get("t", cutoff))
    for p in merged:
        p.setdefault("rss_max", p.get("rss", 0))
        p.setdefault("cpu_max", p.get("cpu", 0))
    return merged
