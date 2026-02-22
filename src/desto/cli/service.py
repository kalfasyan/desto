#!/usr/bin/env python3
"""Service management module for systemd integration."""

import getpass
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Tuple

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


class ServiceManager:
    """Manages systemd service installation and configuration for desto."""

    def __init__(self):
        self.package_root = Path(__file__).parent.parent
        self.templates_dir = self.package_root / "systemd"
        self.user_service_dir = Path.home() / ".config" / "systemd" / "user"
        self.system_service_dir = Path("/etc/systemd/system")
        self.user_service_file = self.user_service_dir / "desto.service"
        self.system_service_file = self.system_service_dir / "desto.service"
        self.console = Console()

    def is_systemd_available(self) -> bool:
        """Check if systemd is available on this system."""
        try:
            result = subprocess.run(
                ["systemctl", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def is_user_service_installed(self) -> bool:
        """Check if user service is installed."""
        return self.user_service_file.exists()

    def is_system_service_installed(self) -> bool:
        """Check if system service is installed."""
        return self.system_service_file.exists()

    def get_desto_path(self) -> str:
        """Get the path to the desto executable."""
        # Try to find desto in PATH
        desto_path = shutil.which("desto")
        if desto_path:
            return desto_path

        # Fall back to python -m desto
        python_path = sys.executable
        return f"{python_path} -m desto"

    def get_redis_config(self) -> Tuple[str, str]:
        """Get Redis configuration from environment or defaults."""
        host = os.environ.get("REDIS_HOST", "localhost")
        port = os.environ.get("REDIS_PORT", "6379")
        return host, port

    def render_template(self, template_path: Path, variables: dict) -> str:
        """Render a template file with the given variables."""
        content = template_path.read_text()
        for key, value in variables.items():
            content = content.replace(f"{{{{{key}}}}}", str(value))
        return content

    def install_user_service(self) -> bool:
        """Install user-level systemd service."""
        if not self.is_systemd_available():
            self.console.print("[red]❌ systemd is not available on this system[/red]")
            return False

        # Get configuration
        scripts_dir = os.environ.get("DESTO_SCRIPTS_DIR", str(Path.home() / "desto_scripts"))
        logs_dir = os.environ.get("DESTO_LOGS_DIR", str(Path.home() / "desto_logs"))
        working_dir = Path.home()
        desto_path = self.get_desto_path()
        redis_host, redis_port = self.get_redis_config()
        current_user = getpass.getuser()

        # Prepare template variables
        variables = {
            "USER": current_user,
            "GROUP": current_user,
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(Path.home()),
            "SCRIPTS_DIR": scripts_dir,
            "LOGS_DIR": logs_dir,
            "WORKING_DIR": str(working_dir),
            "EXEC_START": f"{desto_path}",
            "REDIS_HOST": redis_host,
            "REDIS_PORT": redis_port,
        }

        # Render template
        template_path = self.templates_dir / "desto.service.template"
        if not template_path.exists():
            self.console.print(f"[red]❌ Template file not found: {template_path}[/red]")
            return False

        service_content = self.render_template(template_path, variables)

        # Create user service directory if needed
        self.user_service_dir.mkdir(parents=True, exist_ok=True)

        # Write service file
        self.user_service_file.write_text(service_content)
        self.console.print(f"[green]✅ Service file created: {self.user_service_file}[/green]")

        # Reload systemd daemon
        try:
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.console.print("[green]✅ systemd daemon reloaded[/green]")
        except subprocess.CalledProcessError as e:
            self.console.print(f"[yellow]⚠️  daemon-reload failed: {e.stderr}[/yellow]")
            self.console.print("   You may need to run: systemctl --user daemon-reload")

        # Enable lingering (so user services run without login)
        try:
            subprocess.run(
                ["loginctl", "enable-linger", current_user],
                check=True,
                capture_output=True,
                text=True,
            )
            self.console.print("[green]✅ User lingering enabled (services run without login)[/green]")
        except subprocess.CalledProcessError:
            self.console.print("[yellow]⚠️  Could not enable lingering - services may stop when you log out[/yellow]")
            self.console.print(f"   Run: sudo loginctl enable-linger {current_user}")

        self.console.print("\n[bold]📋 Next steps:[/bold]")
        self.console.print("   1. Enable auto-start: [cyan]systemctl --user enable desto.service[/cyan]")
        self.console.print("   2. Start now: [cyan]systemctl --user start desto.service[/cyan]")
        self.console.print("   3. Check status: [cyan]systemctl --user status desto.service[/cyan]")
        self.console.print("   4. View logs: [cyan]journalctl --user -u desto.service -f[/cyan]")

        return True

    def install_system_service(self) -> bool:
        """Install system-level systemd service (requires sudo)."""
        if not self.is_systemd_available():
            self.console.print("[red]❌ systemd is not available on this system[/red]")
            return False

        # Check for sudo
        if os.geteuid() != 0:
            self.console.print("[red]❌ System service installation requires root privileges[/red]")
            self.console.print("   Run with: [cyan]sudo desto-cli service install --system[/cyan]")
            return False

        # Get configuration
        user = os.environ.get("SUDO_USER", getpass.getuser())
        user_home = Path("/home") / user
        if not user_home.exists():
            user_home = Path.home()

        scripts_dir = os.environ.get("DESTO_SCRIPTS_DIR", str(user_home / "desto_scripts"))
        logs_dir = os.environ.get("DESTO_LOGS_DIR", str(user_home / "desto_logs"))
        working_dir = user_home
        desto_path = self.get_desto_path()
        redis_host, redis_port = self.get_redis_config()

        # Prepare template variables
        variables = {
            "USER": user,
            "GROUP": user,
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(user_home),
            "SCRIPTS_DIR": scripts_dir,
            "LOGS_DIR": logs_dir,
            "WORKING_DIR": str(working_dir),
            "EXEC_START": f"{desto_path}",
            "REDIS_HOST": redis_host,
            "REDIS_PORT": redis_port,
        }

        # Render template
        template_path = self.templates_dir / "desto-system.service.template"
        if not template_path.exists():
            self.console.print(f"[red]❌ Template file not found: {template_path}[/red]")
            return False

        service_content = self.render_template(template_path, variables)

        # Write service file
        self.system_service_file.write_text(service_content)
        self.console.print(f"[green]✅ Service file created: {self.system_service_file}[/green]")

        # Reload systemd daemon
        try:
            subprocess.run(
                ["systemctl", "daemon-reload"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.console.print("[green]✅ systemd daemon reloaded[/green]")
        except subprocess.CalledProcessError as e:
            self.console.print(f"[yellow]⚠️  daemon-reload failed: {e.stderr}[/yellow]")

        self.console.print("\n[bold]📋 Next steps:[/bold]")
        self.console.print("   1. Enable auto-start: [cyan]systemctl enable desto.service[/cyan]")
        self.console.print("   2. Start now: [cyan]systemctl start desto.service[/cyan]")
        self.console.print("   3. Check status: [cyan]systemctl status desto.service[/cyan]")
        self.console.print("   4. View logs: [cyan]journalctl -u desto.service -f[/cyan]")

        return True

    def uninstall_service(self, system: bool = False) -> bool:
        """Uninstall the systemd service."""
        service_file = self.system_service_file if system else self.user_service_file
        systemctl_cmd = ["systemctl"] + (["--user"] if not system else [])

        if not service_file.exists():
            self.console.print(f"[red]❌ Service not installed: {service_file}[/red]")
            return False

        # Stop and disable service
        try:
            subprocess.run(
                systemctl_cmd + ["stop", "desto.service"],
                check=False,  # Don't fail if not running
                capture_output=True,
            )
            subprocess.run(
                systemctl_cmd + ["disable", "desto.service"],
                check=False,
                capture_output=True,
            )
        except subprocess.SubprocessError:
            pass

        # Remove service file
        try:
            service_file.unlink()
            self.console.print(f"[green]✅ Service file removed: {service_file}[/green]")
        except Exception as e:
            self.console.print(f"[red]❌ Failed to remove service file: {e}[/red]")
            return False

        # Reload daemon
        try:
            subprocess.run(
                systemctl_cmd + ["daemon-reload"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.console.print("[green]✅ systemd daemon reloaded[/green]")
        except subprocess.SubprocessError:
            self.console.print("[yellow]⚠️  daemon-reload failed - you may need to run it manually[/yellow]")

        return True

    def start_service(self) -> bool:
        """Start the systemd service."""
        return self._run_systemctl(["start"])

    def stop_service(self) -> bool:
        """Stop the systemd service."""
        return self._run_systemctl(["stop"])

    def restart_service(self) -> bool:
        """Restart the systemd service."""
        return self._run_systemctl(["restart"])

    def status_service(self) -> bool:
        """Show service status."""
        return self._run_systemctl(["status"])

    def _run_systemctl(self, args: list) -> bool:
        """Run systemctl command for user or system service."""
        if not self.is_systemd_available():
            self.console.print("[red]❌ systemd is not available[/red]")
            return False

        # Determine if user or system service
        is_system = self.is_system_service_installed() and not self.is_user_service_installed()
        systemctl_cmd = ["systemctl"] + (["--user"] if not is_system else [])

        try:
            result = subprocess.run(
                systemctl_cmd + args + ["desto.service"],
                capture_output=True,
                text=True,
            )
            if result.stdout:
                self.console.print(result.stdout)
            if result.stderr:
                self.console.print(result.stderr)
            return result.returncode == 0
        except subprocess.SubprocessError as e:
            self.console.print(f"[red]❌ Failed: {e}[/red]")
            return False

    def logs_service(self, follow: bool = False) -> bool:
        """Show service logs."""
        if not self.is_systemd_available():
            self.console.print("[red]❌ systemd is not available[/red]")
            return False

        is_system = self.is_system_service_installed() and not self.is_user_service_installed()
        journalctl_cmd = ["journalctl"] + (["--user"] if not is_system else [])

        args = ["-u", "desto.service"]
        if follow:
            args.append("-f")

        try:
            # Run interactively so user can see logs
            subprocess.run(journalctl_cmd + args)
            return True
        except subprocess.SubprocessError as e:
            self.console.print(f"[red]❌ Failed: {e}[/red]")
            return False

    def enable_service(self) -> bool:
        """Enable service to start on boot."""
        return self._run_systemctl(["enable"])

    def disable_service(self) -> bool:
        """Disable service from starting on boot."""
        return self._run_systemctl(["disable"])


# Create the service command group
service_app = typer.Typer(help="Manage systemd service for auto-start on boot")


@service_app.command("install")
def service_install(
    system: bool = typer.Option(False, "--system", help="Install as system service (requires sudo)"),
):
    """Install systemd service for auto-start on boot."""
    manager = ServiceManager()
    if system:
        manager.install_system_service()
    else:
        manager.install_user_service()


@service_app.command("uninstall")
def service_uninstall(
    system: bool = typer.Option(False, "--system", help="Uninstall system service"),
):
    """Uninstall systemd service."""
    manager = ServiceManager()
    manager.uninstall_service(system=system)


@service_app.command("start")
def service_start():
    """Start the systemd service."""
    manager = ServiceManager()
    manager.start_service()


@service_app.command("stop")
def service_stop():
    """Stop the systemd service."""
    manager = ServiceManager()
    manager.stop_service()


@service_app.command("restart")
def service_restart():
    """Restart the systemd service."""
    manager = ServiceManager()
    manager.restart_service()


@service_app.command("status")
def service_status():
    """Show service status."""
    manager = ServiceManager()
    manager.status_service()


@service_app.command("logs")
def service_logs(
    follow: bool = typer.Option(False, "-f", "--follow", help="Follow logs"),
):
    """Show service logs."""
    manager = ServiceManager()
    manager.logs_service(follow=follow)


@service_app.command("enable")
def service_enable():
    """Enable service to start on boot."""
    manager = ServiceManager()
    manager.enable_service()


@service_app.command("disable")
def service_disable():
    """Disable service from starting on boot."""
    manager = ServiceManager()
    manager.disable_service()


def main():
    """Main entry point for service management CLI."""
    service_app()


if __name__ == "__main__":
    main()
