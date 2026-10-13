## Environment Variables

desto can be configured using environment variables. These override the default values in the `UISettings` dataclass (`src/desto/app/config.py`).

### Redis

| Variable | Default | Description |
|---|---|---|
| `REDIS_HOST` | `localhost` | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `REDIS_DB` | `0` | Redis database number |
| `REDIS_ENABLED` | `true` | Enable/disable Redis |
| `REDIS_CONNECTION_TIMEOUT` | `5` | Connection timeout in seconds |
| `REDIS_RETRY_ATTEMPTS` | `3` | Number of connection retry attempts |
| `REDIS_SESSION_HISTORY_DAYS` | `7` | Days to keep session history in Redis |

### SQLite (Long-Term Persistence)

| Variable | Default | Description |
|---|---|---|
| `SQLITE_ENABLED` | `false` | Enable the SQLite store for long-term persistence. Accepts `true`, `1`, `yes`, or `on`. |
| `SQLITE_DB_PATH` | `desto_data/desto.db` | Path to the SQLite database file |

See [SQLite Long-Term Persistence](../user-guide/sqlite-persistence.md) for details.

### Application

| Variable | Default | Description |
|---|---|---|
| `DESTO_SCRIPTS_DIR` | `desto_scripts/` | Directory for script files |
| `DESTO_LOGS_DIR` | `desto_logs/` | Directory for log files |
| `DESTO_PUSHBULLET_API_KEY` | *(unset)* | Pushbullet API key for push notifications |

### Dashboard and Login

| Variable | Default | Description |
|---|---|---|
| `DESTO_HOST` | `127.0.0.1` | Interface the web dashboard listens on. Use `0.0.0.0` to accept connections from other machines (the Docker image sets this). An empty value falls back to `127.0.0.1`. |
| `DESTO_PORT` | `8809` | Port the web dashboard listens on. |
| `DESTO_PASSWORD` | *(unset)* | When set to a non-empty value, every page requires this password to log in. Unset means no login. |
| `DESTO_STORAGE_SECRET` | *(random on each start)* | Secret that signs the browser session cookie. Set a fixed value to keep logins valid across restarts. |

When the dashboard is reachable from the network and `DESTO_PASSWORD` is not set, desto logs a warning at startup.

## Project configuration (`pyproject.toml`)

This project uses `pyproject.toml` for metadata and build configuration. Key sections:

- **[project]**: package metadata, dependencies, and scripts.
- **[project.optional-dependencies]**: extras groups, including `docs` which contains MkDocs and theme packages.
- **[build-system]**: `hatchling` is used as the build backend.

See the repository root `pyproject.toml` for the full configuration.
