"""Pure helpers for turning raw session/job data into what the dashboard shows.

Nothing in here touches tmux, Redis or the UI, so it can be unit tested directly.
"""

import re
from datetime import datetime


def decode_hash(data):
    """Decode a Redis hash whose keys/values may be bytes into a str dict."""
    return {k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in data.items()}


def parse_iso(value):
    """Parse an ISO timestamp, accepting a trailing 'Z' for UTC."""
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def seconds_since(start_dt):
    """Whole seconds elapsed since start_dt, in start_dt's timezone if it has one."""
    now_dt = datetime.now(start_dt.tzinfo) if start_dt.tzinfo else datetime.now()
    return int((now_dt - start_dt).total_seconds())


def format_seconds(elapsed_seconds):
    """Format seconds as '1h 2m 3s', '2m 3s' or '3s'; negative values give 'N/A'."""
    if elapsed_seconds < 0:
        return "N/A"
    hours, remainder = divmod(elapsed_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s" if hours > 0 else (f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s")


def format_duration(duration_str):
    """Normalise a duration string such as '1 day, 2:03:04' or '0:05:00' to the '1h 2m 3s' style.

    Values that are not in H:MM:SS form are returned unchanged (as a string).
    """
    if duration_str in ["N/A", "unknown", "Ongoing"]:
        return duration_str
    if ":" in str(duration_str):
        try:
            if "day" in str(duration_str):
                parts = str(duration_str).split(", ")
                days_part = parts[0]
                time_part = parts[1] if len(parts) > 1 else "0:00:00"
                days = int(days_part.split()[0])
            else:
                days = 0
                time_part = str(duration_str)
            time_components = time_part.split(":")
            if len(time_components) >= 3:
                hours = int(time_components[0]) + (days * 24)
                minutes = int(time_components[1])
                seconds = int(float(time_components[2]))
                if hours > 0:
                    return f"{hours}h {minutes}m {seconds}s"
                elif minutes > 0:
                    return f"{minutes}m {seconds}s"
                else:
                    return f"{seconds}s"
        except Exception:
            pass
    return str(duration_str)


def format_timestamp(value):
    """Format an ISO timestamp as 'YYYY-MM-DD HH:MM:SS', or its first 19 characters if it does not parse."""
    try:
        return parse_iso(value).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)[:19]


def session_sort_key(session):
    """Sort key for the sessions table: the start time, falling back to the tmux creation time."""
    sort_key = str(session.get("start_time") or "")
    if not sort_key and session.get("created"):
        try:
            sort_key = datetime.fromtimestamp(float(session["created"])).isoformat()
        except Exception:
            pass
    return sort_key


def session_row_times(session):
    """Return the time columns of a sessions table row.

    Returns a dict with the effective start_time/end_time values and the display strings
    "started", "finished", "job_duration" and "session_duration".
    """
    job_status = session.get("job_status", "") or session.get("status", "")
    created_time = session.get("created")
    start_time = session.get("start_time")
    end_time = session.get("end_time")
    if not start_time and created_time:
        start_time = datetime.fromtimestamp(float(created_time)).isoformat()

    started = format_timestamp(start_time) if start_time else "Unknown"
    if end_time:
        finished = format_timestamp(end_time)
    else:
        finished = "Running" if job_status == "running" else "N/A"

    # Job duration: script execution time, falling back to the recorded elapsed fields
    job_duration = "N/A"
    if start_time and end_time:
        try:
            elapsed_seconds = int((parse_iso(end_time) - parse_iso(start_time)).total_seconds())
            if elapsed_seconds >= 0:
                job_duration = format_seconds(elapsed_seconds)
        except Exception:
            pass
    if job_duration == "N/A":
        job_duration = session.get("job_elapsed", session.get("elapsed", "N/A"))

    # Session duration: total time, up to now for sessions that have not ended
    session_duration = "N/A"
    if start_time:
        try:
            start_dt = parse_iso(start_time)
            if end_time:
                elapsed_seconds = int((parse_iso(end_time) - start_dt).total_seconds())
            else:
                elapsed_seconds = seconds_since(start_dt)
            session_duration = format_seconds(elapsed_seconds)
        except Exception:
            session_duration = "N/A"

    return {
        "start_time": start_time,
        "end_time": end_time,
        "started": started,
        "finished": finished,
        "job_duration": format_duration(job_duration),
        "session_duration": format_duration(session_duration),
    }


def summarize_jobs(jobs):
    """Summarise the jobs of one session as {"status", "exit_code", "command"}.

    The overall status is "running" if any job runs, else "failed" if any failed, else
    "finished" if all finished, else "queued". The exit code is the last one recorded.
    """
    jobs.sort(key=lambda j: j.get("job_id", ""))
    statuses = [j.get("status", "") for j in jobs]
    if "running" in statuses:
        overall = "running"
    elif "failed" in statuses:
        overall = "failed"
    elif all(st == "finished" for st in statuses):
        overall = "finished"
    else:
        overall = "queued"
    exit_code = None
    for job in jobs:
        if job.get("status") in ("finished", "failed"):
            code = job.get("exit_code") or ""
            if not code:
                match = re.search(r"code:?\s*(-?\d+)", job.get("error_message") or "")
                code = match.group(1) if match else ""
            if code:
                exit_code = code
    return {"status": overall, "exit_code": exit_code, "command": jobs[0].get("command", "")}


def classify_session(session_name, session, tmux_active, job_info):
    """Return (category, label, color) for a session row.

    category is one of "running", "finished", "failed" or "scheduled".
    """
    info = job_info.get(session.get("session_id", ""), {}) if job_info else {}
    status_field = (session.get("status", "") or "").lower()
    job_status_field = (session.get("job_status", "") or info.get("status", "") or "").lower()
    fields = (status_field, job_status_field)

    if "finished" in fields:
        category = "finished"
    elif "failed" in fields:
        category = "failed"
    elif "scheduled" in fields:
        category = "scheduled"
    else:
        category = "running"

    # If tmux is not active, the session cannot still be running.
    if category == "running" and not tmux_active and "running" in fields:
        category = "finished" if session.get("end_time") else "failed"
        if category == "failed":
            return category, "❌ Failed (tmux closed)", "#F44336"

    if category == "finished":
        return category, "✅ Finished", "#4CAF50"
    if category == "failed":
        code = info.get("exit_code")
        label = f"❌ Failed · exit {code}" if code not in (None, "", "0") else "❌ Failed"
        return category, label, "#F44336"
    if category == "scheduled":
        return category, "📅 Scheduled", "#9C27B0"
    return category, "🟡 Running", "#FF9800"


def parse_atq_output(stdout):
    """Parse `atq` output into (job_id, date_time, user) tuples."""
    entries = []
    for line in stdout.splitlines():
        if line.strip():
            # atq output: job_id date time queue user, e.g. "5 Mon Jul 14 07:59:00 2025 a user"
            parts = line.strip().split()
            if len(parts) >= 5:
                date_time = " ".join(parts[1:6]) if len(parts) >= 6 else " ".join(parts[1:5])
                entries.append((parts[0], date_time, parts[-1]))
    return entries


def extract_at_command(stdout):
    """Pick the job's command out of `at -c` output (the last non-boilerplate line), truncated to 60 chars."""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("cd ") and "export" not in line:
            if len(line) > 60:
                return line[:57] + "..."
            return line
    return "Unknown command"


def format_scheduled_datetime(date_time):
    """Turn an atq date like 'Mon Jul 14 07:59:00 2025' into ISO format, or return it unchanged."""
    try:
        return datetime.strptime(date_time, "%a %b %d %H:%M:%S %Y").isoformat()
    except Exception:
        return date_time
