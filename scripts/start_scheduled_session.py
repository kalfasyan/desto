#!/usr/bin/env python3
"""
Wrapper script for starting scheduled tmux sessions with proper Redis tracking.
This ensures scheduled jobs get the same Redis tracking as manually started sessions.
"""

import subprocess
import sys
import threading
import time
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def start_redis_monitoring(session_name, desto_manager):
    """Monitor tmux session and update Redis - same logic as TmuxManager._start_redis_monitoring"""

    def monitor():
        try:
            while True:
                time.sleep(1)
                result = subprocess.run(
                    ["tmux", "list-sessions", "-F", "#{session_name}"],
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0 or session_name not in result.stdout:
                    # Session finished (entire tmux session ended)
                    try:
                        # Try to get exit status from Redis job
                        job_status = desto_manager.get_job_status(session_name)
                        if job_status not in ["finished", "failed"]:
                            # Session ended but job wasn't marked complete - mark as finished
                            desto_manager.finish_job(session_name, 0)
                            print(f"Session '{session_name}' ended - marked as finished in Redis")
                        else:
                            print(f"Session '{session_name}' ended - already marked as {job_status} in Redis")

                        # Mark session as finished
                        desto_manager.session_manager.finish_session(session_name)
                        break
                    except Exception as e:
                        print(f"Error updating Redis for finished session {session_name}: {e}")
                        break
        except Exception as e:
            print(f"Error in Redis monitoring for {session_name}: {e}")

    # Start monitoring in a daemon thread
    threading.Thread(target=monitor, daemon=True).start()


def main():
    if len(sys.argv) < 3:
        print("Usage: start_scheduled_session.py <session_name> <command>", file=sys.stderr)
        sys.exit(1)

    session_name = sys.argv[1]
    command = " ".join(sys.argv[2:])  # Join all remaining args as the command

    try:
        from src.desto.redis.client import DestoRedisClient
        from src.desto.redis.desto_manager import DestoManager

        # Start the tmux session
        print(f"Starting scheduled tmux session: {session_name}")
        result = subprocess.run(["tmux", "new-session", "-d", "-s", session_name, "bash", "-c", command], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Failed to start tmux session: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        print(f"Tmux session '{session_name}' started successfully")

        # Initialize Redis tracking
        client = DestoRedisClient()
        if client.is_connected():
            manager = DestoManager(client)

            # Create session and job in Redis (similar to TmuxManager.start_tmux_session)
            session, job = manager.start_session_with_job(
                session_name=session_name,
                command=command,
                script_path=command,
                keep_alive=False,  # Default for scheduled jobs
            )

            # Start Redis monitoring
            start_redis_monitoring(session_name, manager)
            print(f"Redis tracking initialized for session '{session_name}'")

            # Keep the script running to maintain monitoring
            # This process will exit when the session ends
            while True:
                time.sleep(60)  # Check every minute if session still exists
                result = subprocess.run(
                    ["tmux", "list-sessions", "-F", "#{session_name}"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0 or session_name not in result.stdout:
                    print(f"Session '{session_name}' has ended - exiting monitor")
                    break

        else:
            print("Redis not available - session will run without tracking", file=sys.stderr)

    except ImportError as e:
        print(f"Could not import Redis modules: {e}", file=sys.stderr)
        # Still start the session even without Redis
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name, "bash", "-c", command])
    except Exception as e:
        print(f"Error starting scheduled session: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
