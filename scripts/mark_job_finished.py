#!/usr/bin/env python3
"""
Helper script to mark job completion in Redis.
This is called from within tmux sessions when jobs finish.
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
        print("Usage: mark_job_finished.py <session_name> <exit_code>", file=sys.stderr)
        sys.exit(1)

    session_name = sys.argv[1]
    exit_code = int(sys.argv[2])

    # Try to mark job as finished in Redis
    client = DestoRedisClient()
    if client.is_connected():
        tracker = SessionStatusTracker(client)
        if exit_code == 0:
            tracker.mark_job_finished(session_name, exit_code)
            print(f"Marked job '{session_name}' as finished in Redis")
        else:
            tracker.mark_job_failed(session_name, f"Job exited with code {exit_code}")
            print(f"Marked job '{session_name}' as failed in Redis (exit code: {exit_code})")
    else:
        print("Redis not available, skipping job completion tracking", file=sys.stderr)

except ImportError as e:
    print(f"Could not import Redis modules: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Error marking job completion: {e}", file=sys.stderr)
    sys.exit(1)
