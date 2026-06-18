# SQLite Long-Term Persistence

By default, desto uses [Redis](https://redis.io/) for session tracking with keys that auto-expire after 7 days. This is great for real-time state management, but means your session history is lost after a week.

The **SQLite store** is an optional feature that keeps your session, job, and favorites history indefinitely—no extra services or configuration required. It uses Python's built-in `sqlite3` module, so there are no additional dependencies to install.

## How It Works

SQLite works **alongside** Redis, not as a replacement:

| Concern | Redis | SQLite |
|---|---|---|
| Real-time session state | ✅ | — |
| Pub/sub notifications | ✅ | — |
| Short-term cache (7 days) | ✅ | — |
| Long-term history | ❌ (keys expire) | ✅ |
| Survives restarts | ❌ | ✅ |

When enabled, desto automatically archives session and job state to SQLite on lifecycle transitions (create, finish, fail). You don't need to change how you use desto—the archiving happens in the background.

## Enabling SQLite

SQLite persistence is **disabled by default**. To enable it, set the `SQLITE_ENABLED` environment variable.

### With Docker Compose

In your `docker-compose.yml`, set the environment variable:

```yaml
environment:
  - SQLITE_ENABLED=true
  - SQLITE_DB_PATH=/app/desto_data/desto.db  # optional, this is the default
```

The included `docker-compose.yml` already has a `desto_data` volume configured for persistence.

### Without Docker

```bash
export SQLITE_ENABLED=true
desto
```

Or inline:

```bash
SQLITE_ENABLED=true desto
```

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `SQLITE_ENABLED` | `false` | Enable or disable the SQLite store. Accepts `true`, `1`, `yes`, or `on`. |
| `SQLITE_DB_PATH` | `desto_data/desto.db` | Path to the SQLite database file. Parent directories are created automatically. |

These can also be configured in the `SQLiteSettings` dataclass in `src/desto/app/config.py`.

## What Gets Stored

The SQLite store persists:

- **Sessions** — name, status, script, start/end times, command, and metadata
- **Jobs** — scheduled job details, status, and execution history
- **Favorites** — saved favorite commands with usage counts

## Storage Location

By default, the database file is created at `desto_data/desto.db` relative to your working directory. In Docker, this maps to `/app/desto_data/desto.db` inside the container, backed by a named volume for persistence.

You can change the location with the `SQLITE_DB_PATH` environment variable:

```bash
export SQLITE_DB_PATH=/path/to/my/desto.db
```

## Technical Details

- **Thread-safe**: Uses thread-local connections, safe for concurrent access from multiple request handlers.
- **WAL mode**: Uses SQLite's Write-Ahead Logging for better concurrent read/write performance.
- **No-op when disabled**: When `SQLITE_ENABLED` is not set (or set to `false`), all store operations are no-ops with zero overhead.
- **No extra dependencies**: Uses Python's built-in `sqlite3` module.

## Why SQLite Over PostgreSQL?

SQLite was chosen for desto because it:

- Requires **zero configuration** — no database server to set up or manage
- Needs **no additional Docker service** — no extra container in your compose stack
- Uses **single-file storage** — easy to back up, move, or inspect
- Is **ideal for single-node deployments** like desto
- Has **no network overhead** — direct file access is faster for local use

For most desto users, SQLite provides all the durability benefits of a SQL database without any operational complexity.
