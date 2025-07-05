"""Main CLI application entry point for desto."""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

try:
    import typer
    from rich.console import Console

    TYPER_AVAILABLE = True
except ImportError:
    # Mock typer for development without dependencies
    class MockTyper:
        def __init__(self, name=None, help=None, add_completion=False):
            self.name = name
            self.help = help

        def callback(self):
            def decorator(func):
                return func

            return decorator

        def command(self, name=None):
            def decorator(func):
                return func

            return decorator

        def add_typer(self, *args, **kwargs):
            pass

        def Typer(self, **kwargs):
            return MockTyper(**kwargs)

        def Option(self, default=None, *args, help=None, **kwargs):
            return default

        def Exit(self, code=0):
            return SystemExit(code)

        def __call__(self):
            pass

    typer = MockTyper()

    class MockConsole:
        def print(self, *args, **kwargs):
            print(*args)

    Console = MockConsole
    TYPER_AVAILABLE = False

from desto.cli.scripts import scripts_app
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
