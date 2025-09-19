#!/usr/bin/env python3
"""Helper script to mark job completion in Redis.
This is called from within tmux sessions when jobs finish.
"""

import sys
from datetime import datetime
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

    # Prepare notifier helpers: try multiple import paths and a direct PushbulletNotifier fallback
    notify_job_finished = None
    notifier_obj = None
    try:
        from src.desto.notifications import notify_job_finished as _njf

        notify_job_finished = _njf
    except Exception:
        try:
            from desto.notifications import notify_job_finished as _njf

            notify_job_finished = _njf
        except Exception:
            notify_job_finished = None

    try:
        from src.desto.notifications import PushbulletNotifier as _pb

        notifier_obj = _pb()
    except Exception:
        try:
            from desto.notifications import PushbulletNotifier as _pb

            notifier_obj = _pb()
        except Exception:
            notifier_obj = None

    job_finished_time = None

    if client.is_connected():
        manager = DestoManager(client)

        # Mark job as finished/failed in Redis
        if exit_code == 0:
            manager.finish_job(session_name, exit_code)
            print(f"Marked job '{session_name}' as finished in Redis")
        else:
            manager.fail_job(session_name, f"Job exited with code {exit_code}")
            print(f"Marked job '{session_name}' as failed in Redis (exit code: {exit_code})")

        # Fetch job_finished_time from Redis and set session end_time to match
        try:
            session_key = client.get_session_key(session_name)
            session_data = client.redis.hgetall(session_key)
            if session_data:
                # Handle bytes from Redis
                if isinstance(list(session_data.values())[0], bytes):
                    session_data = {k.decode("utf-8") if isinstance(k, bytes) else k: v.decode("utf-8") if isinstance(v, bytes) else v for k, v in session_data.items()}
                job_finished_time = session_data.get("job_finished_time")
        except Exception:
            job_finished_time = None

        # Patch: set session end_time to job_finished_time if available
        if job_finished_time:
            try:
                client.redis.hset(session_key, "end_time", job_finished_time)
                print(f"Set session 'end_time' to job_finished_time: {job_finished_time}")
            except Exception:
                pass

        # Also mark the session as finished or failed (status, exit_code)
        if exit_code == 0:
            manager.finish_session(session_name, exit_code)
            print(f"Marked session '{session_name}' as finished in Redis (exit code: {exit_code})")
        else:
            # Look up session and pass session_id to fail_session
            session = manager.session_manager.get_session_by_name(session_name)
            if session:
                manager.session_manager.fail_session(session.session_id, f"Session failed (exit code: {exit_code})")
                print(f"Marked session '{session_name}' as failed in Redis (exit code: {exit_code})")
            else:
                print(f"Could not find session '{session_name}' to mark as failed", file=sys.stderr)

    else:
        print("Redis not available, skipping job completion tracking", file=sys.stderr)

    # Decide finished_at timestamp
    finished_at = job_finished_time or datetime.utcnow().isoformat()

    # Attempt to send a notification regardless of Redis availability
    try:
        if notify_job_finished:
            ok = notify_job_finished(session_name, exit_code, finished_at)
            print(f"notify_job_finished invoked, result: {ok}")
        elif notifier_obj:
            resp = notifier_obj.notify_with_response(
                title=f"Job finished: {session_name}",
                body=f"Session: {session_name}\nExit code: {exit_code}\nFinished at: {finished_at}",
            )
            print(f"Pushbullet notify response: {resp}")
        else:
            print("No notifier available to send push notification")
    except Exception as e:
        print(f"Failed to send notification: {e}", file=sys.stderr)

except ImportError as e:
    print(f"Could not import Redis modules: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Error marking job completion: {e}", file=sys.stderr)
    sys.exit(1)
