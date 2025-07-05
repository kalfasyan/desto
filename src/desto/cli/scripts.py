"""Script management commands for the desto CLI."""

import os
import stat
import subprocess
from datetime import datetime
from typing import List, Optional

try:
    import typer
    from rich.console import Console
    from rich.prompt import Confirm, Prompt
    from rich.syntax import Syntax
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

    class MockPrompt:
        @staticmethod
        def ask(*args, **kwargs):
            return "y"

    class MockConfirm:
        @staticmethod
        def ask(*args, **kwargs):
            return True

    class MockSyntax:
        def __init__(self, *args, **kwargs):
            pass

    Console = MockConsole
    Table = MockTable
    Prompt = MockPrompt
    Confirm = MockConfirm
    Syntax = MockSyntax
    TYPER_AVAILABLE = False

from .session_manager import CLISessionManager

# Create the scripts command group
scripts_app = typer.Typer(help="📝 Manage scripts - create, edit, delete, and run scripts")

console = Console()

# Script templates
BASH_TEMPLATE = """#!/bin/bash

# Description: Add your description here
# Usage: {script_name}

echo "🐚 Bash script started!"
echo "Script: {script_name}"
echo "Arguments: $@"

# Add your code here

echo "✅ Script completed successfully!"
"""

PYTHON_TEMPLATE = """#!/usr/bin/env python3

\"\"\"
Description: Add your description here
Usage: {script_name}
\"\"\"

import os
import sys
from pathlib import Path


def main():
    print("🐍 Python script started!")
    print(f"Script: {{sys.argv[0]}}")
    print(f"Arguments: {{sys.argv[1:] if len(sys.argv) > 1 else 'None'}}")

    # Add your code here

    print("✅ Script completed successfully!")


if __name__ == "__main__":
    main()
"""


def get_script_type(filename: str) -> str:
    """Determine script type from file extension."""
    if filename.endswith(".py"):
        return "python"
    elif filename.endswith(".sh"):
        return "bash"
    return "unknown"


def get_script_icon(script_type: str) -> str:
    """Get icon for script type."""
    icons = {"python": "🐍", "bash": "🐚", "unknown": "📄"}
    return icons.get(script_type, "📄")


def validate_script_name(name: str) -> str:
    """Validate and sanitize script name."""
    if not name:
        raise ValueError("Script name cannot be empty")

    # Replace spaces with underscores and remove invalid characters
    safe_name = name.replace(" ", "_")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._-").strip()
    safe_name = safe_name[:50]  # Limit length

    if not safe_name:
        raise ValueError("Script name must contain at least one alphanumeric character")

    return safe_name


def get_editor() -> str:
    """Get the user's preferred editor."""
    return os.environ.get("EDITOR", "nano")


@scripts_app.command("list")
def list_scripts(
    show_details: bool = typer.Option(False, "--details", "-d", help="Show detailed information about scripts"),
    filter_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by script type (bash/python)"),
):
    """List all available scripts."""
    manager = CLISessionManager()

    if not manager.scripts_dir.exists():
        console.print(f"[yellow]Scripts directory doesn't exist: {manager.scripts_dir}[/yellow]")
        console.print("Create it with: [bold]desto-cli scripts create <name>[/bold]")
        return

    # Get all script files
    script_files = []
    for pattern in ["*.sh", "*.py"]:
        script_files.extend(manager.scripts_dir.glob(pattern))

    if not script_files:
        console.print(f"[yellow]No scripts found in {manager.scripts_dir}[/yellow]")
        console.print("Create one with: [bold]desto-cli scripts create <name>[/bold]")
        return

    # Filter by type if specified
    if filter_type and hasattr(filter_type, "lower"):
        if filter_type.lower() not in ["bash", "python"]:
            console.print("[red]Invalid type. Use 'bash' or 'python'[/red]")
            raise typer.Exit(1)
        script_files = [f for f in script_files if get_script_type(f.name) == filter_type.lower()]

    if show_details:
        # Show detailed table
        table = Table(title=f"Scripts in {manager.scripts_dir}")
        table.add_column("Icon", width=4)
        table.add_column("Name", style="bold blue")
        table.add_column("Type", style="green")
        table.add_column("Size", justify="right")
        table.add_column("Modified", style="dim")
        table.add_column("Executable", justify="center")

        for script_file in sorted(script_files):
            script_type = get_script_type(script_file.name)
            icon = get_script_icon(script_type)
            stat_info = script_file.stat()
            size = f"{stat_info.st_size:,} bytes" if stat_info.st_size > 0 else "0 bytes"
            modified_time = datetime.fromtimestamp(stat_info.st_mtime)
            modified_str = modified_time.strftime("%Y-%m-%d %H:%M")
            executable = "✅" if os.access(script_file, os.X_OK) else "❌"

            table.add_row(icon, script_file.name, script_type.title(), size, modified_str, executable)

        console.print(table)
    else:
        # Simple list with icons
        console.print(f"[bold]📝 Scripts in {manager.scripts_dir}[/bold]")
        for script_file in sorted(script_files):
            script_type = get_script_type(script_file.name)
            icon = get_script_icon(script_type)
            console.print(f"  {icon} {script_file.name}")

    console.print(f"\n[dim]Total: {len(script_files)} script(s)[/dim]")


@scripts_app.command("create")
def create_script(
    name: str = typer.Argument(..., help="Name of the script to create"),
    script_type: str = typer.Option("bash", "--type", "-t", help="Script type: bash or python"),
    template: bool = typer.Option(True, "--template/--no-template", help="Use default template"),
    edit: bool = typer.Option(False, "--edit", "-e", help="Open script in editor after creation"),
):
    """Create a new script with optional template."""
    manager = CLISessionManager()

    try:
        safe_name = validate_script_name(name)
    except ValueError as e:
        console.print(f"[red]Invalid script name: {e}[/red]")
        raise typer.Exit(1)

    # Determine file extension
    if script_type.lower() == "python":
        extension = ".py"
        template_content = PYTHON_TEMPLATE if template else "#!/usr/bin/env python3\n\n"
    elif script_type.lower() == "bash":
        extension = ".sh"
        template_content = BASH_TEMPLATE if template else "#!/bin/bash\n\n"
    else:
        console.print("[red]Invalid script type. Use 'bash' or 'python'[/red]")
        raise typer.Exit(1)

    # Add extension if not present
    if not safe_name.endswith(extension):
        safe_name += extension

    script_path = manager.get_script_file(safe_name)

    # Check if script already exists
    if script_path.exists():
        if not Confirm.ask(f"Script '{safe_name}' already exists. Overwrite?"):
            console.print("[yellow]Script creation cancelled[/yellow]")
            return

    # Create scripts directory if it doesn't exist
    manager.scripts_dir.mkdir(exist_ok=True)

    try:
        # Format template with script name
        if template:
            content = template_content.format(script_name=safe_name)
        else:
            content = template_content

        # Write script file
        script_path.write_text(content)

        # Make executable
        script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

        icon = get_script_icon(script_type.lower())
        console.print(f"[green]✅ Created {icon} {safe_name} in {manager.scripts_dir}[/green]")

        if edit:
            edit_script_command(safe_name)

    except Exception as e:
        console.print(f"[red]Failed to create script: {e}[/red]")
        raise typer.Exit(1)


@scripts_app.command("edit")
def edit_script(
    name: str = typer.Argument(..., help="Name of the script to edit"),
    editor: Optional[str] = typer.Option(None, "--editor", "-e", help="Editor to use (default: $EDITOR or nano)"),
):
    """Edit an existing script."""
    edit_script_command(name, editor)


def edit_script_command(name: str, editor: Optional[str] = None):
    """Helper function to edit a script."""
    manager = CLISessionManager()

    # Find the script file (try with and without extension)
    script_path = None
    for candidate in [name, f"{name}.sh", f"{name}.py"]:
        candidate_path = manager.get_script_file(candidate)
        if candidate_path.exists():
            script_path = candidate_path
            break

    if not script_path:
        console.print(f"[red]Script '{name}' not found in {manager.scripts_dir}[/red]")
        available_scripts = [f.name for f in manager.scripts_dir.glob("*.sh")] + [f.name for f in manager.scripts_dir.glob("*.py")]
        if available_scripts:
            console.print(f"Available scripts: {', '.join(available_scripts)}")
        raise typer.Exit(1)

    # Get editor
    editor_cmd = editor or get_editor()

    try:
        console.print(f"[blue]Opening {script_path.name} with {editor_cmd}...[/blue]")
        subprocess.run([editor_cmd, str(script_path)], check=True)
        console.print(f"[green]✅ Finished editing {script_path.name}[/green]")
    except subprocess.CalledProcessError:
        console.print(f"[red]Failed to open editor '{editor_cmd}'[/red]")
        raise typer.Exit(1)
    except FileNotFoundError:
        console.print(f"[red]Editor '{editor_cmd}' not found[/red]")
        console.print("Set your preferred editor with: export EDITOR=vim")
        raise typer.Exit(1)


@scripts_app.command("delete")
def delete_script(
    name: str = typer.Argument(..., help="Name of the script to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Delete without confirmation"),
):
    """Delete a script."""
    manager = CLISessionManager()

    # Find the script file (try with and without extension)
    script_path = None
    for candidate in [name, f"{name}.sh", f"{name}.py"]:
        candidate_path = manager.get_script_file(candidate)
        if candidate_path.exists():
            script_path = candidate_path
            break

    if not script_path:
        console.print(f"[red]Script '{name}' not found in {manager.scripts_dir}[/red]")
        raise typer.Exit(1)

    # Confirm deletion unless force flag is used
    if not force:
        script_type = get_script_type(script_path.name)
        icon = get_script_icon(script_type)
        if not Confirm.ask(f"Delete {icon} {script_path.name}?"):
            console.print("[yellow]Deletion cancelled[/yellow]")
            return

    try:
        script_path.unlink()
        console.print(f"[green]✅ Deleted {script_path.name}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to delete script: {e}[/red]")
        raise typer.Exit(1)


@scripts_app.command("show")
def show_script(
    name: str = typer.Argument(..., help="Name of the script to show"),
    line_numbers: bool = typer.Option(False, "--line-numbers", "-n", help="Show line numbers"),
    max_lines: Optional[int] = typer.Option(None, "--lines", "-l", help="Maximum number of lines to show"),
):
    """Display the contents of a script."""
    manager = CLISessionManager()

    # Find the script file (try with and without extension)
    script_path = None
    for candidate in [name, f"{name}.sh", f"{name}.py"]:
        candidate_path = manager.get_script_file(candidate)
        if candidate_path.exists():
            script_path = candidate_path
            break

    if not script_path:
        console.print(f"[red]Script '{name}' not found in {manager.scripts_dir}[/red]")
        raise typer.Exit(1)

    try:
        content = script_path.read_text()

        # Limit lines if specified
        if max_lines:
            lines = content.splitlines()
            if len(lines) > max_lines:
                content = "\n".join(lines[:max_lines])
                content += f"\n... ({len(lines) - max_lines} more lines)"

        # Determine language for syntax highlighting
        script_type = get_script_type(script_path.name)
        language = "python" if script_type == "python" else "bash"

        # Display with syntax highlighting
        syntax = Syntax(content, language, line_numbers=line_numbers, theme="default")

        script_icon = get_script_icon(script_type)
        console.print(f"[bold]{script_icon} {script_path.name}[/bold]")
        console.print(syntax)

        # Show file info
        stat_info = script_path.stat()
        size = f"{stat_info.st_size:,} bytes"
        executable = "✅" if os.access(script_path, os.X_OK) else "❌"
        console.print(f"[dim]Size: {size} | Executable: {executable}[/dim]")

    except Exception as e:
        console.print(f"[red]Failed to read script: {e}[/red]")
        raise typer.Exit(1)


@scripts_app.command("run")
def run_script(
    name: str = typer.Argument(..., help="Name of the script to run"),
    args: List[str] = typer.Argument(None, help="Arguments to pass to the script"),
    session_name: Optional[str] = typer.Option(None, "--session", "-s", help="Run in a specific tmux session"),
    keep_alive: bool = typer.Option(False, "--keep-alive", "-k", help="Keep session alive after script finishes"),
    direct: bool = typer.Option(False, "--direct", "-d", help="Run directly without tmux session"),
):
    """Run a script directly or in a tmux session."""
    manager = CLISessionManager()

    # Find the script file (try with and without extension)
    script_path = None
    for candidate in [name, f"{name}.sh", f"{name}.py"]:
        candidate_path = manager.get_script_file(candidate)
        if candidate_path.exists():
            script_path = candidate_path
            break

    if not script_path:
        console.print(f"[red]Script '{name}' not found in {manager.scripts_dir}[/red]")
        raise typer.Exit(1)

    # Check if script is executable
    if not os.access(script_path, os.X_OK):
        console.print(f"[yellow]Warning: {script_path.name} is not executable[/yellow]")
        if Confirm.ask("Make it executable?"):
            script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)
            console.print("[green]✅ Made script executable[/green]")

    # Build command
    script_type = get_script_type(script_path.name)
    if script_type == "python":
        base_command = ["python3", str(script_path)]
    else:
        base_command = ["bash", str(script_path)]

    if args:
        base_command.extend(args)

    if direct:
        # Run directly without tmux
        try:
            console.print(f"[blue]Running {script_path.name} directly...[/blue]")
            result = subprocess.run(base_command, check=False)
            if result.returncode == 0:
                console.print(f"[green]✅ {script_path.name} completed successfully[/green]")
            else:
                console.print(f"[red]❌ {script_path.name} exited with code {result.returncode}[/red]")
                raise typer.Exit(result.returncode)
        except KeyboardInterrupt:
            console.print(f"\n[yellow]⚠️ {script_path.name} interrupted by user[/yellow]")
            raise typer.Exit(130)
    else:
        # Run in tmux session
        if not session_name:
            session_name = f"{script_path.stem}_{int(datetime.now().timestamp())}"

        command_str = " ".join(base_command)

        if manager.start_session(session_name, command_str, keep_alive):
            icon = get_script_icon(script_type)
            console.print(f"[green]✅ Started {icon} {script_path.name} in session '{session_name}'[/green]")

            if keep_alive:
                console.print("[dim]Session will stay alive after script finishes[/dim]")

            console.print(f"[blue]View logs with: desto-cli sessions logs {session_name}[/blue]")
            console.print(f"[blue]Attach to session: tmux attach -t {session_name}[/blue]")
        else:
            console.print(f"[red]❌ Failed to start session '{session_name}'[/red]")
            raise typer.Exit(1)


@scripts_app.command("copy")
def copy_script(
    source: str = typer.Argument(..., help="Name of the script to copy"),
    destination: str = typer.Argument(..., help="Name for the new script"),
    edit: bool = typer.Option(False, "--edit", "-e", help="Open new script in editor after copying"),
):
    """Copy an existing script to a new name."""
    manager = CLISessionManager()

    # Find source script
    source_path = None
    for candidate in [source, f"{source}.sh", f"{source}.py"]:
        candidate_path = manager.get_script_file(candidate)
        if candidate_path.exists():
            source_path = candidate_path
            break

    if not source_path:
        console.print(f"[red]Source script '{source}' not found in {manager.scripts_dir}[/red]")
        raise typer.Exit(1)

    try:
        # Validate destination name
        safe_dest = validate_script_name(destination)

        # Preserve extension if not provided
        source_ext = source_path.suffix
        if not safe_dest.endswith(source_ext):
            safe_dest += source_ext

        dest_path = manager.get_script_file(safe_dest)

        # Check if destination exists
        if dest_path.exists():
            if not Confirm.ask(f"Script '{safe_dest}' already exists. Overwrite?"):
                console.print("[yellow]Copy cancelled[/yellow]")
                return

        # Copy file and preserve permissions
        content = source_path.read_text()
        dest_path.write_text(content)
        dest_path.chmod(source_path.stat().st_mode)

        script_type = get_script_type(dest_path.name)
        icon = get_script_icon(script_type)
        console.print(f"[green]✅ Copied {source_path.name} to {icon} {safe_dest}[/green]")

        if edit:
            edit_script_command(safe_dest)

    except ValueError as e:
        console.print(f"[red]Invalid destination name: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Failed to copy script: {e}[/red]")
        raise typer.Exit(1)
