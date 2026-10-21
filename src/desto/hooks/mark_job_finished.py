"""Mark job completion in Redis and send a notification.

Called from within tmux sessions when jobs finish::

    python -m desto.hooks.mark_job_finished <session_name> <exit_code>
"""

import sys
from datetime import datetime


def main(argv=None) -> int:
    """Record the job/session outcome in Redis and notify. Returns a process exit code."""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("Usage: python -m desto.hooks.mark_job_finished <session_name> <exit_code>", file=sys.stderr)
        return 1

    try:
        from desto.notifications import notify_job_finished
        from desto.redis.client import DestoRedisClient
        from desto.redis.desto_manager import DestoManager

        session_name = argv[0]
        exit_code = int(argv[1])

        client = DestoRedisClient()
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
            session_key = client.get_session_key(session_name)
            try:
                session_data = client.redis.hgetall(session_key)
                if session_data:
                    # Handle bytes from Redis
                    if isinstance(list(session_data.values())[0], bytes):
                        session_data = {k.decode("utf-8") if isinstance(k, bytes) else k: v.decode("utf-8") if isinstance(v, bytes) else v for k, v in session_data.items()}
                    job_finished_time = session_data.get("job_finished_time")
            except Exception:
                job_finished_time = None

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
                session = manager.session_manager.get_session_by_name(session_name)
                if session:
                    manager.session_manager.fail_session(session.session_id, f"Session failed (exit code: {exit_code})")
                    print(f"Marked session '{session_name}' as failed in Redis (exit code: {exit_code})")
                else:
                    print(f"Could not find session '{session_name}' to mark as failed", file=sys.stderr)
        else:
            print("Redis not available, skipping job completion tracking", file=sys.stderr)

        # Attempt to send a notification regardless of Redis availability
        finished_at = job_finished_time or datetime.utcnow().isoformat()
        try:
            ok = notify_job_finished(session_name, exit_code, finished_at)
            print(f"notify_job_finished invoked, result: {ok}")
        except Exception as e:
            print(f"Failed to send notification: {e}", file=sys.stderr)

    except ImportError as e:
        print(f"Could not import Redis modules: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error marking job completion: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
