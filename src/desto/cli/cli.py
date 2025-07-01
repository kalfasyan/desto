#!/usr/bin/env python3
"""Entry point for desto-cli that works with or without typer."""

import sys


def cli_main():
    """Main entry point for the CLI."""
    try:
        # Try to use the full typer CLI
        from desto.cli.main import app

        app()
    except ImportError as e:
        # Fall back to simple CLI if typer not available
        print("⚠️  Typer not available, using simple CLI interface")
        print("Install with: uv add typer rich")
        print(f"Error: {e}\n")

        # Use the simple CLI test interface
        from desto.cli.session_manager import CLISessionManager
        from desto.cli.utils import format_duration

        if len(sys.argv) < 2:
            print("Usage: desto-cli <command> [args...]")
            print("Commands: list, start, kill, logs, status")
            print("Example: desto-cli list")
            return

        command = sys.argv[1]

        try:
            manager = CLISessionManager()
        except Exception as e:
            print(f"❌ Error initializing session manager: {e}")
            return

        try:
            if command == "list":
                sessions = manager.list_sessions()
                if not sessions:
                    print("No active sessions")
                else:
                    print("Active sessions:")
                    for name, info in sessions.items():
                        status = "🔴 Finished" if info["finished"] else "🟢 Running"
                        runtime = format_duration(info["runtime"])
                        print(f"  • {name} - {status} - {runtime}")

            elif command == "start" and len(sys.argv) >= 4:
                session_name = sys.argv[2]
                command_to_run = " ".join(sys.argv[3:])
                if manager.start_session(session_name, command_to_run):
                    print(f"✅ Session '{session_name}' started")
                else:
                    print("❌ Failed to start session")

            elif command == "kill" and len(sys.argv) >= 3:
                session_name = sys.argv[2]
                if manager.kill_session(session_name):
                    print(f"✅ Session '{session_name}' killed")
                else:
                    print("❌ Failed to kill session")

            elif command == "logs" and len(sys.argv) >= 3:
                session_name = sys.argv[2]
                content = manager.get_log_content(session_name)
                if content:
                    print(f"--- Logs for {session_name} ---")
                    print(content)
                else:
                    print("No logs found")

            else:
                print("Invalid command or missing arguments")
        except Exception as e:
            print(f"❌ Error executing command: {e}")


if __name__ == "__main__":
    cli_main()
