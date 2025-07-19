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
    from src.desto.redis.desto_manager import DestoManager

    if len(sys.argv) != 3:
        print("Usage: mark_job_finished.py <session_name> <exit_code>", file=sys.stderr)
        sys.exit(1)

    session_name = sys.argv[1]
    exit_code = int(sys.argv[2])

    # Try to mark job as finished in Redis
    client = DestoRedisClient()
    if client.is_connected():
        manager = DestoManager(client)
        from datetime import datetime

        # Mark job as finished/failed and get the job_finished_time from Redis
        if exit_code == 0:
            manager.finish_job(session_name, exit_code)
            print(f"Marked job '{session_name}' as finished in Redis")
        else:
            manager.fail_job(session_name, f"Job exited with code {exit_code}")
            print(f"Marked job '{session_name}' as failed in Redis (exit code: {exit_code})")

        # Fetch job_finished_time from Redis and set session end_time to match
        session_key = client.get_session_key(session_name)
        session_data = client.redis.hgetall(session_key)
        job_finished_time = None
        if session_data:
            # Handle bytes from Redis
            if isinstance(list(session_data.values())[0], bytes):
                session_data = {
                    k.decode("utf-8") if isinstance(k, bytes) else k: v.decode("utf-8") if isinstance(v, bytes) else v
                    for k, v in session_data.items()
                }
            job_finished_time = session_data.get("job_finished_time")

        # Patch: set session end_time to job_finished_time if available
        if job_finished_time:
            # Directly update end_time in Redis to match job_finished_time
            client.redis.hset(session_key, "end_time", job_finished_time)
            print(f"Set session 'end_time' to job_finished_time: {job_finished_time}")

        # Also mark the session as finished (status, exit_code)
        manager.finish_session(session_name, exit_code)
        print(f"Marked session '{session_name}' as finished in Redis (exit code: {exit_code})")
    else:
        print("Redis not available, skipping job completion tracking", file=sys.stderr)

except ImportError as e:
    print(f"Could not import Redis modules: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Error marking job completion: {e}", file=sys.stderr)
    sys.exit(1)
