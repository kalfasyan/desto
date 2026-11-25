"""CPU, memory, disk and tmux server usage, as shown in the dashboard and the terminal UI."""

import time
from dataclasses import dataclass

import psutil

GB = 1024**3
MB = 1024**2


@dataclass(frozen=True)
class SystemStats:
    cpu_percent: float
    cpu_cores: list[float]
    memory_percent: float
    memory_used_gb: float
    memory_available_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_free_gb: float
    tmux_cpu: str  # e.g. "1.5%", or "N/A" without a tmux server
    tmux_mem: str  # e.g. "4.2 MB", or "N/A"


class SystemMonitor:
    """Reads SystemStats without blocking: CPU figures are measured since the previous read."""

    def __init__(self, tmux_rescan_interval: float = 10.0):
        self._tmux_rescan_interval = tmux_rescan_interval
        self._tmux_proc = None
        self._tmux_last_scan = 0.0

    def read(self, per_core: bool = False) -> SystemStats:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        tmux_cpu, tmux_mem = "N/A", "N/A"
        try:
            proc = self._tmux_server_proc()
            if proc is not None:
                tmux_cpu = f"{proc.cpu_percent(interval=None):.1f}%"
                tmux_mem = f"{proc.memory_info().rss / MB:.1f} MB"
        except psutil.Error:
            self._tmux_proc = None
        return SystemStats(
            cpu_percent=psutil.cpu_percent(interval=None),
            cpu_cores=psutil.cpu_percent(percpu=True, interval=None) if per_core else [],
            memory_percent=memory.percent,
            memory_used_gb=round(memory.used / GB, 2),
            memory_available_gb=round(memory.available / GB, 2),
            disk_percent=disk.percent,
            disk_used_gb=round(disk.used / GB, 2),
            disk_free_gb=round(disk.free / GB, 2),
            tmux_cpu=tmux_cpu,
            tmux_mem=tmux_mem,
        )

    def _tmux_server_proc(self):
        """Return the cached tmux server process, re-scanning the process list at most every rescan interval.

        Reusing one psutil.Process keeps cpu_percent() non-blocking (it measures since the previous call).
        """
        if self._tmux_proc is not None and self._tmux_proc.is_running():
            return self._tmux_proc
        now = time.monotonic()
        if now - self._tmux_last_scan < self._tmux_rescan_interval:
            return None
        self._tmux_last_scan = now
        candidates = [p for p in psutil.process_iter(["name", "ppid"]) if "tmux" in (p.info["name"] or "")]
        if not candidates:
            self._tmux_proc = None
            return None
        proc = next((p for p in candidates if p.info["ppid"] == 1), None) or min(
            candidates, key=lambda p: p.info["ppid"]
        )
        proc.cpu_percent(interval=None)  # prime the counter
        self._tmux_proc = proc
        return proc
