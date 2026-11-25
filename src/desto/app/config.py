import os
from dataclasses import asdict, dataclass, field


@dataclass
class UISettings:
    @dataclass
    class CPUCores:
        max_columns: int = 4  # Number of columns to display cores in

    @dataclass
    class ScriptSettings:
        supported_extensions: list = field(default_factory=lambda: [".sh", ".py"])
        python_executable: str = "python3"
        show_script_type_icons: bool = True

    @dataclass
    class RedisSettings:
        host: str = "localhost"
        port: int = 6379  # Default Redis port
        db: int = 0
        enabled: bool = True  # Allow disabling Redis completely
        connection_timeout: int = 5  # seconds
        retry_attempts: int = 3
        session_history_days: int = 7  # Number of days to keep session history

    @dataclass
    class SQLiteSettings:
        enabled: bool = False  # Disabled by default, opt-in for long-term persistence
        db_path: str = ""  # Defaults to desto_data/desto.db if empty

    @dataclass
    class MetricsSettings:
        enabled: bool = True  # Sample CPU, memory and IO of every tmux session
        interval: float = 5.0  # Seconds between samples

    cpu_cores: CPUCores = field(default_factory=CPUCores)
    script_settings: ScriptSettings = field(default_factory=ScriptSettings)
    redis: RedisSettings = field(default_factory=RedisSettings)
    sqlite: SQLiteSettings = field(default_factory=SQLiteSettings)
    metrics: MetricsSettings = field(default_factory=MetricsSettings)

    def __post_init__(self):
        """Override settings with environment variables if available."""
        # Redis configuration from environment variables
        self.redis.host = os.getenv("REDIS_HOST", self.redis.host)
        self.redis.port = int(os.getenv("REDIS_PORT", self.redis.port))
        self.redis.db = int(os.getenv("REDIS_DB", self.redis.db))
        self.redis.enabled = os.getenv("REDIS_ENABLED", "true").lower() in ("true", "1", "yes", "on")
        self.redis.connection_timeout = int(os.getenv("REDIS_CONNECTION_TIMEOUT", self.redis.connection_timeout))
        self.redis.retry_attempts = int(os.getenv("REDIS_RETRY_ATTEMPTS", self.redis.retry_attempts))
        self.redis.session_history_days = int(os.getenv("REDIS_SESSION_HISTORY_DAYS", self.redis.session_history_days))

        # SQLite configuration from environment variables
        self.sqlite.enabled = os.getenv("SQLITE_ENABLED", "false").lower() in ("true", "1", "yes", "on")
        self.sqlite.db_path = os.getenv("SQLITE_DB_PATH", self.sqlite.db_path)

        # Session metrics sampling
        self.metrics.enabled = os.getenv("DESTO_METRICS_ENABLED", "true").lower() in ("true", "1", "yes", "on")
        self.metrics.interval = float(os.getenv("DESTO_METRICS_INTERVAL", self.metrics.interval))


config = asdict(UISettings())
