"""The system usage bar at the top of the terminal UI."""

from rich.text import Text
from textual.widgets import Static

from desto.core.system_stats import SystemStats

BAR_WIDTH = 10


def meter(label: str, percent: float, detail: str = "") -> Text:
    """A labelled bar such as 'CPU ▰▰▰▱▱▱▱▱▱▱ 31%', green, then yellow above 60% and red above 85%."""
    filled = round(max(0.0, min(percent, 100.0)) / 100 * BAR_WIDTH)
    color = "red" if percent > 85 else "yellow" if percent > 60 else "green"
    text = Text.assemble(
        (f"{label} ", "bold"), ("▰" * filled, color), ("▱" * (BAR_WIDTH - filled), "dim"), f" {percent:.0f}%"
    )
    if detail:
        text.append(f" {detail}", "dim")
    return text


class StatsBar(Static):
    """CPU, memory, disk and tmux server usage on one line."""

    def show(self, stats: SystemStats) -> None:
        gap = Text("   ")
        self.update(
            Text.assemble(
                meter("CPU", stats.cpu_percent),
                gap,
                meter("MEM", stats.memory_percent, f"{stats.memory_used_gb} GB used"),
                gap,
                meter("DISK", stats.disk_percent, f"{stats.disk_free_gb} GB free"),
                gap,
                Text.assemble(("tmux ", "bold"), (f"{stats.tmux_cpu} · {stats.tmux_mem}", "dim")),
            )
        )
