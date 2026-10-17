# Scheduling

desto can launch a script, or a chain of scripts, at a later date and time, either once or on repeat. Scheduling uses the system's [`at`](https://en.wikipedia.org/wiki/At_(command)) daemon, so it must be installed and running (see [Installation](../getting-started/installation.md)). Scheduled runs fire even when the dashboard is closed.

## Schedule a script

1. In **Script Execution**, enter a session name and pick a script (or queue several with the chain button).
2. Click the schedule button (clock icon) and pick the date and time of the first run.
3. Leave **Repeat** on *Does not repeat* for a one-off run, or choose an interval such as every **2** *day(s)*.
4. Click **Schedule**.

The next queued run appears in the **Scheduled Jobs** table. For recurring schedules the status shows the interval, for example `scheduled · every 2 days`.

## How recurring schedules run

- Each run starts its own session named `<session name>-<YYYYMMDD>-<HHMM>`, for example `backup-20261018-0630`. Each run therefore has its own log, history entry, exit code, and (if configured) Pushbullet notification.
- Runs stay aligned to the first run's time. If the machine was off when a run was due, that run is skipped and the schedule continues with the next one.
- If the previous run is still going when the next one is due, the new run is skipped so runs never overlap.
- Only the next run is queued with `at` at any time; it queues the one after it when it fires.

## Cancel a schedule

Click **Cancel** on the job's row in the **Scheduled Jobs** table. For a recurring schedule this stops all future runs; a run that is already in progress keeps running. **Kill all sessions** also stops all recurring schedules.

!!! note
    Recurring schedules are stored in Redis. If Redis data is lost, the next queued run does nothing and the schedule ends.
