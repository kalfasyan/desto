"""Fire one run of a recurring schedule and queue the next one.

Queued with ``at`` by RecurringScheduleManager::

    python -m desto.hooks.run_recurring <schedule_id> <occurrence YYYY-MM-DDTHH:MM>
"""

import os
import subprocess
import sys
from datetime import datetime


def main(argv=None) -> int:
    """Run the given occurrence if the schedule is still active. Returns a process exit code."""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("Usage: python -m desto.hooks.run_recurring <schedule_id> <occurrence>", file=sys.stderr)
        return 1

    from desto.redis.client import DestoRedisClient
    from desto.redis.recurring import OCCURRENCE_FORMAT, RecurringScheduleManager, next_occurrence, occurrence_session_name

    schedule_id = argv[0]
    try:
        occurrence = datetime.strptime(argv[1], OCCURRENCE_FORMAT)
    except ValueError:
        print(f"Invalid occurrence '{argv[1]}', expected YYYY-MM-DDTHH:MM", file=sys.stderr)
        return 1

    client = DestoRedisClient()
    if not client.is_connected():
        print("Redis not available, cannot run recurring schedule", file=sys.stderr)
        return 1
    manager = RecurringScheduleManager(client)

    schedule = manager.get(schedule_id)
    if not schedule or schedule.get("status") != "active":
        print(f"Recurring schedule {schedule_id} is not active, nothing to do")
        return 0
    if not manager.claim(schedule_id, occurrence):
        print(f"Run {argv[1]} of recurring schedule {schedule_id} was already handled")
        return 0

    # Queue the next run before launching this one, so a failed launch never ends the series
    anchor = datetime.strptime(schedule["anchor"], OCCURRENCE_FORMAT)
    following = next_occurrence(anchor, int(schedule["interval_minutes"]), after=max(datetime.now(), occurrence))
    manager.arm(schedule, following)

    previous = schedule.get("last_session_name")
    if previous and subprocess.run(["tmux", "has-session", "-t", f"={previous}"], capture_output=True).returncode == 0:
        print(f"Skipping run {argv[1]}: previous run '{previous}' is still active")
        manager.record_run(schedule_id, "skipped: previous run still active")
        return 0

    session_name = occurrence_session_name(schedule["session_name"], occurrence)
    env = {**os.environ, "DESTO_LOGS_DIR": schedule["log_dir"]}
    result = subprocess.run([sys.executable, "-m", "desto.hooks.start_scheduled_session", session_name, schedule["command"]], env=env)
    manager.record_run(schedule_id, "started" if result.returncode == 0 else f"failed to start (exit code {result.returncode})", session_name)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
