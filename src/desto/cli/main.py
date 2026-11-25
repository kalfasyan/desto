"""Main CLI application entry point for desto."""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from desto.cli.scripts import scripts_app
from desto.cli.service import ServiceManager, service_app
from desto.cli.session_manager import CLISessionManager
from desto.cli.sessions import sessions_app
from desto.cli.utils import setup_logging

# Create the main CLI application
app = typer.Typer(
    name="desto-cli",
    help="🚀 Desto CLI - Manage tmux sessions and scripts from the command line",
    add_completion=False,
)

# Add the sessions command group
app.add_typer(sessions_app, name="sessions")

# Add the scripts command group
app.add_typer(scripts_app, name="scripts")

# Add the service command group
app.add_typer(service_app, name="service")


console = Console()


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
    log_file: Optional[Path] = typer.Option(None, "--log-file", help="Write logs to file"),
):
    """Desto CLI - Manage tmux sessions and scripts from the command line."""
    level = "DEBUG" if verbose else "INFO"
    setup_logging(level=level, log_file=str(log_file) if log_file else None)


@app.command()
def monitor(
    interval: Optional[float] = typer.Option(None, "--interval", "-i", help="Seconds between samples (default: DESTO_METRICS_INTERVAL or 5)"),
):
    """Record CPU, memory and IO of every tmux session until stopped (Ctrl+C).

    The dashboard and the terminal UI already do this while they run; use this command when
    neither is open. Only one sampler writes at a time, so it is safe to run alongside them.
    """
    from desto.config import config as ui_settings
    from desto.core.session_metrics import SessionMetricsSampler
    from desto.store.client import DestoRedisClient

    client = DestoRedisClient(ui_settings.get("redis"))
    if not client.is_connected():
        console.print("[red]Redis is not available; session metrics are stored in Redis.[/red]")
        raise typer.Exit(1)
    sqlite_store = None
    if ui_settings.get("sqlite", {}).get("enabled", False):
        from desto.store.sqlite_store import SQLiteStore

        sqlite_store = SQLiteStore(db_path=ui_settings["sqlite"].get("db_path") or None, enabled=True)
    every = interval or ui_settings.get("metrics", {}).get("interval", 5.0)
    retention = int(ui_settings.get("redis", {}).get("session_history_days", 7)) * 86400
    sampler = SessionMetricsSampler(client.redis, sqlite_store, interval=every, retention_seconds=retention)
    console.print(f"[green]Recording session metrics every {sampler.interval:g}s. Press Ctrl+C to stop.[/green]")
    try:
        sampler.run()
    except KeyboardInterrupt:
        sampler.release_lease()
        console.print("Stopped.")


@app.command()
def version():
    """Show version information."""
    from . import __version__

    console.print(f"[bold blue]desto-cli[/bold blue] version [green]{__version__}[/green]")


@app.command()
def doctor():
    """Check system requirements and configuration."""
    console.print("[bold blue]🔍 Desto CLI System Check[/bold blue]\n")

    # Check tmux
    if shutil.which("tmux"):
        try:
            result = subprocess.run(["tmux", "-V"], capture_output=True, text=True)
            version = result.stdout.strip() if result.returncode == 0 else "unknown"
            console.print(f"[green]✅ tmux: {version}[/green]")
        except Exception:
            console.print("[yellow]⚠️  tmux: installed but version check failed[/yellow]")
    else:
        console.print("[red]❌ tmux: not found - please install tmux[/red]")

    # Check Python version
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    console.print(f"[green]✅ Python: {python_version}[/green]")

    # Check Redis connection
    try:
        from desto.config import config as ui_settings
        from desto.store.client import DestoRedisClient

        redis_client = DestoRedisClient(ui_settings.get("redis"))
        if redis_client.is_connected():
            console.print("[green]✅ Redis: connected[/green]")
        else:
            console.print("[yellow]⚠️  Redis: not connected (real-time updates disabled)[/yellow]")
    except Exception as e:
        console.print(f"[yellow]⚠️  Redis: connection failed - {e}[/yellow]")

    # Check directories
    manager = CLISessionManager()

    console.print("\n[bold]📁 Directory Configuration[/bold]")
    console.print(f"Scripts: {manager.scripts_dir}")
    console.print(f"Logs: {manager.log_dir}")

    if manager.scripts_dir.exists():
        scripts_count = len(list(manager.scripts_dir.glob("*.sh")) + list(manager.scripts_dir.glob("*.py")))
        console.print(f"[green]✅ Scripts directory exists ({scripts_count} scripts found)[/green]")
    else:
        console.print("[yellow]⚠️  Scripts directory does not exist (will be created when needed)[/yellow]")

    if manager.log_dir.exists():
        logs_count = len(list(manager.log_dir.glob("*.log")))
        console.print(f"[green]✅ Logs directory exists ({logs_count} log files found)[/green]")
    else:
        console.print("[yellow]⚠️  Logs directory does not exist (will be created when needed)[/yellow]")

    # Check systemd service
    try:
        manager_service = ServiceManager()
        if manager_service.is_systemd_available():
            user_installed = manager_service.is_user_service_installed()
            system_installed = manager_service.is_system_service_installed()
            if user_installed:
                console.print("[green]✅ systemd service: installed (user)[/green]")
            elif system_installed:
                console.print("[green]✅ systemd service: installed (system)[/green]")
            else:
                console.print("[yellow]⚠️  systemd service: not installed (auto-start disabled)[/yellow]")
    except Exception:
        # Silently skip if ServiceManager fails (e.g. in some test environments)
        pass

    # Check active sessions
    sessions = manager.list_sessions()
    if sessions:
        console.print("\n[bold]🖥️  Active Sessions[/bold]")
        console.print(f"Found {len(sessions)} active tmux session(s):")
        for name, info in sessions.items():
            status = "finished" if info["finished"] else "running"
            console.print(f"  • {name} ({status})")
    else:
        console.print("\n[dim]No active tmux sessions found[/dim]")


if __name__ == "__main__":
    app()
