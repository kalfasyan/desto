"""UI-independent core of desto, shared by the web dashboard, the terminal UI and the CLI.

- service.DestoService: tmux sessions, Redis tracking, scheduling, favorites and clean-up
- scripts: listing scripts and building the commands that run them
- formatting: pure helpers that turn raw session/job data into table rows
- log_tailer, system_stats: following log files and reading CPU/memory/disk usage
"""
