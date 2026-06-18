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

## Project configuration (`pyproject.toml`)

This project uses `pyproject.toml` for metadata and build configuration. Key sections:

- **[project]**: package metadata, dependencies, and scripts.
- **[project.optional-dependencies]**: extras groups, including `docs` which contains MkDocs and theme packages.
- **[build-system]**: `hatchling` is used as the build backend.

See the repository root `pyproject.toml` for the full configuration.
