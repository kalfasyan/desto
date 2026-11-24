# Session Usage

desto records how much CPU, memory and disk each session uses, for every tmux session on the machine, including ones desto did not start.

## What is recorded

Every 5 seconds, desto finds each tmux session's panes, walks the process tree under them and adds up:

| Figure | Notes |
|---|---|
| CPU % | Percent of one core, so a job using four cores shows about 400%. |
| Memory | Resident memory (RSS) of all processes. Memory shared between forked workers is counted once per process. |
| Processes and threads | How many processes and threads the session runs. |
| CPU time | User plus system time, including child processes that already finished. |
| Disk read and written | Bytes read from and written to disk (Linux only). |

Processes that detach from their session (for example with `nohup ... &` followed by `setsid`, or a daemon that double-forks) leave the tree and are not counted. Memory spikes shorter than the sampling interval can be missed.

## Where to see it

- **Web dashboard:** the *CPU · Memory* column shows current usage of running sessions, and CPU time and peak memory of ended ones. Click it to chart CPU and memory over the session's whole run.
- **Terminal UI:** the *CPU* and *Memory* columns, and `u` on a session for its usage over time.
- **CLI:** `desto-cli sessions usage` lists every session's figures.
- **Session history:** with [SQLite persistence](sqlite-persistence.md) on, a session's peak memory, CPU time, peak process count and disk totals are saved when it ends and shown in its details.

## How long history is kept

Long sessions keep their whole run at decreasing detail, so memory use stays bounded:

| Resolution | Covers |
|---|---|
| Every sample (5 s) | The last hour |
| 1 minute averages and peaks | The last 24 hours |
| 15 minute averages and peaks | The last 30 days |

Usage data expires from Redis after `REDIS_SESSION_HISTORY_DAYS` (7 by default) without new samples. A session that runs for weeks uses at most about 1 MB of Redis.

## When it runs

The web dashboard and the terminal UI record usage while they run. If you only use the CLI, run:

```bash
desto-cli monitor
```

Only one recorder writes at a time, so running the dashboard, the TUI and `desto-cli monitor` together is fine. Sampling 200 processes takes about 30 ms of CPU per sample.

To turn recording off, set `DESTO_METRICS_ENABLED=false`. To sample less often, set `DESTO_METRICS_INTERVAL`, for example to `15`.
