#!/usr/bin/env python3
"""
Helper script to mark session started in Redis.
This is called from within tmux sessions when sessions start.
"""

import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from src.desto.redis.client import DestoRedisClient
    from src.desto.redis.status_tracker import SessionStatusTracker

    if len(sys.argv) != 3:
        print("Usage: mark_session_started.py <session_name> <command>", file=sys.stderr)
        sys.exit(1)

    session_name = sys.argv[1]
    command = sys.argv[2]

    # Try to mark session as started in Redis
    client = DestoRedisClient()
    if client.is_connected():
        tracker = SessionStatusTracker(client)
        tracker.mark_session_started(session_name=session_name, command=command, script_path=command)
        print(f"Marked session '{session_name}' as started in Redis")
    else:
        print("Redis not available, skipping session tracking", file=sys.stderr)

except ImportError as e:
    print(f"Could not import Redis modules: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Error marking session started: {e}", file=sys.stderr)
    sys.exit(1)
