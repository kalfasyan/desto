"""Session management commands for the desto CLI."""

from pathlib import Path
from typing import Optional

try:
    import typer
    from rich.console import Console
    from rich.table import Table

    TYPER_AVAILABLE = True
except ImportError:
    # Mock typer for development without dependencies
    class MockTyper:
        def __init__(self, help=None):
            self.help = help

        def command(self, name=None):
            def decorator(func):
                return func

            return decorator

        def Typer(self, help=None):
            return MockTyper(help)

        def Argument(self, default=None, help=None):
            return default

        def Option(self, default=None, *args, help=None, **kwargs):
            return default

        def confirm(self, message):
            return True

        def Exit(self, code=0):
            return SystemExit(code)

    typer = MockTyper()

    class MockConsole:
        def print(self, *args, **kwargs):
            print(*args)

    class MockTable:
        def __init__(self, title=None):
            self.title = title

        def add_column(self, *args, **kwargs):
            pass

        def add_row(self, *args, **kwargs):
            pass

    Console = MockConsole
    Table = MockTable
    TYPER_AVAILABLE = False

from .session_manager import CLISessionManager
from .utils import format_duration, format_timestamp

# Create the sessions command group
sessions_app = typer.Typer(help="Manage tmux sessions")
console = Console()


@sessions_app.command("list")
def list_sessions(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed information"
    ),
):
    """List all active tmux sessions."""
    manager = CLISessionManager()
    sessions = manager.list_sessions()

    if not sessions:
        console.print("[yellow]No active tmux sessions found.[/yellow]")
        return

    # Create a rich table
    table = Table(title="Active Tmux Sessions")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Status", style="green")
    table.add_column("Runtime", style="blue")
    table.add_column("Created", style="magenta")

    if verbose:
        table.add_column("ID", style="dim")
        table.add_column("Windows", style="dim")
        table.add_column("Attached", style="dim")

    for session_name, info in sessions.items():
        status = "🔴 Finished" if info["finished"] else "🟢 Running"
        runtime = format_duration(info["runtime"])
        created = format_timestamp(info["created"])

        row = [session_name, status, runtime, created]

        if verbose:
            attached = "Yes" if info["attached"] else "No"
            row.extend([info["id"], str(info["windows"]), attached])

        table.add_row(*row)

    console.print(table)


@sessions_app.command("start")
def start_session(
    session_name: str = typer.Argument(..., help="Name for the tmux session"),
    command: str = typer.Argument(..., help="Command to execute in the session"),
    keep_alive: bool = typer.Option(
        False, "--keep-alive", "-k", help="Keep session alive after command finishes"
    ),
    logs_dir: Optional[Path] = typer.Option(
        None, "--logs-dir", help="Custom logs directory"
    ),
    scripts_dir: Optional[Path] = typer.Option(
        None, "--scripts-dir", help="Custom scripts directory"
    ),
):
    """Start a new tmux session with a command."""
    try:
        manager = CLISessionManager(log_dir=logs_dir, scripts_dir=scripts_dir)

        # Check if session already exists
        if manager.session_exists(session_name):
            console.print(f"[red]Error: Session '{session_name}' already exists.[/red]")
            raise typer.Exit(1)

        if manager.start_session(session_name, command, keep_alive):
            console.print(
                f"[green]✅ Session '{session_name}' started successfully[/green]"
            )
            console.print(f"[dim]Command: {command}[/dim]")
            console.print(f"[dim]Logs: {manager.get_log_file(session_name)}[/dim]")
        else:
            console.print(f"[red]❌ Failed to start session '{session_name}'[/red]")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@sessions_app.command("kill")
def kill_session(
    session_name: Optional[str] = typer.Argument(
        None, help="Name of the session to kill"
    ),
    all_sessions: bool = typer.Option(False, "--all", "-a", help="Kill all sessions"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """Kill one or all tmux sessions."""
    manager = CLISessionManager()

    if all_sessions:
        # Kill all sessions
        if not force:
            sessions = manager.list_sessions()
            if not sessions:
                console.print("[yellow]No active sessions to kill.[/yellow]")
                return

            console.print(f"[yellow]About to kill {len(sessions)} session(s):[/yellow]")
            for name in sessions.keys():
                console.print(f"  • {name}")

            if not typer.confirm("Are you sure you want to kill all sessions?"):
                console.print("[blue]Operation cancelled.[/blue]")
                return

        success_count, total_count, errors = manager.kill_all_sessions()

        if success_count == total_count:
            console.print(
                f"[green]✅ Successfully killed all {total_count} session(s)[/green]"
            )
        else:
            console.print(
                f"[yellow]⚠️  Killed {success_count}/{total_count} sessions[/yellow]"
            )
            for error in errors:
                console.print(f"[red]  • {error}[/red]")

    elif session_name:
        # Kill specific session
        if not manager.session_exists(session_name):
            console.print(f"[red]Error: Session '{session_name}' not found.[/red]")
            raise typer.Exit(1)

        if not force:
            if not typer.confirm(f"Kill session '{session_name}'?"):
                console.print("[blue]Operation cancelled.[/blue]")
                return

        if manager.kill_session(session_name):
            console.print(
                f"[green]✅ Session '{session_name}' killed successfully[/green]"
            )
        else:
            console.print(f"[red]❌ Failed to kill session '{session_name}'[/red]")
            raise typer.Exit(1)

    else:
        console.print(
            "[red]Error: Must specify either a session name or --all flag.[/red]"
        )
        raise typer.Exit(1)


@sessions_app.command("attach")
def attach_session(
    session_name: str = typer.Argument(..., help="Name of the session to attach to"),
):
    """Attach to an existing tmux session."""
    manager = CLISessionManager()

    if not manager.session_exists(session_name):
        console.print(f"[red]Error: Session '{session_name}' not found.[/red]")
        raise typer.Exit(1)

    console.print(f"[blue]Attaching to session '{session_name}'...[/blue]")

    # This will replace the current process
    if not manager.attach_session(session_name):
        console.print(f"[red]❌ Failed to attach to session '{session_name}'[/red]")
        raise typer.Exit(1)


@sessions_app.command("logs")
def view_logs(
    session_name: str = typer.Argument(..., help="Name of the session"),
    lines: Optional[int] = typer.Option(
        None, "--lines", "-n", help="Number of lines to show from the end"
    ),
    follow: bool = typer.Option(
        False, "--follow", "-f", help="Follow log output (like tail -f)"
    ),
):
    """View logs for a session."""
    manager = CLISessionManager()

    log_file = manager.get_log_file(session_name)
    if not log_file.exists():
        console.print(
            f"[red]Error: No log file found for session '{session_name}'[/red]"
        )
        console.print(f"[dim]Expected location: {log_file}[/dim]")
        raise typer.Exit(1)

    if follow:
        console.print(
            f"[blue]Following logs for session '{session_name}' (Press Ctrl+C to exit)...[/blue]"
        )
        # This will replace the current process with tail -f
        if not manager.follow_log(session_name):
            console.print(
                f"[red]❌ Failed to follow logs for session '{session_name}'[/red]"
            )
            raise typer.Exit(1)
    else:
        content = manager.get_log_content(session_name, lines)
        if content is None:
            console.print(
                f"[red]Error: Could not read log file for session '{session_name}'[/red]"
            )
            raise typer.Exit(1)

        if not content.strip():
            console.print(
                f"[yellow]Log file for session '{session_name}' is empty.[/yellow]"
            )
        else:
            console.print(f"[dim]--- Logs for session '{session_name}' ---[/dim]")
            console.print(content)


@sessions_app.command("status")
def session_status(
    session_name: Optional[str] = typer.Argument(
        None, help="Name of specific session to check"
    ),
):
    """Show detailed status for a session or all sessions."""
    manager = CLISessionManager()
    sessions = manager.list_sessions()

    if not sessions:
        console.print("[yellow]No active tmux sessions found.[/yellow]")
        return

    if session_name:
        if session_name not in sessions:
            console.print(f"[red]Error: Session '{session_name}' not found.[/red]")
            raise typer.Exit(1)

        sessions = {session_name: sessions[session_name]}

    for name, info in sessions.items():
        status_color = "red" if info["finished"] else "green"
        status_text = "Finished" if info["finished"] else "Running"

        console.print(f"\n[bold cyan]Session: {name}[/bold cyan]")
        console.print(f"  Status: [{status_color}]{status_text}[/{status_color}]")
        console.print(f"  ID: {info['id']}")
        console.print(f"  Created: {format_timestamp(info['created'])}")
        console.print(f"  Runtime: {format_duration(info['runtime'])}")
        console.print(f"  Windows: {info['windows']}")
        console.print(f"  Attached: {'Yes' if info['attached'] else 'No'}")

        # Show log file info
        log_file = manager.get_log_file(name)
        if log_file.exists():
            log_size = log_file.stat().st_size
            console.print(f"  Log file: {log_file} ({log_size} bytes)")
        else:
            console.print("  Log file: [dim]Not found[/dim]")
