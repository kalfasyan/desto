import os
from dataclasses import asdict, dataclass, field


@dataclass
class UISettings:
    @dataclass
    class Header:
        background_color: str = "#2196F3"
        color: str = "#FFFFFF"
        font_size: str = "1.8em"

    @dataclass
    class Sidebar:
        width: str = "180px"  # was 280px
        padding: str = "4px"  # was 10px
        background_color: str = "#F0F0F0"
        border_radius: str = "6px"
        gap: str = "8px"

    @dataclass
    class Labels:
        title_font_size: str = "1.7em"
        title_font_weight: str = "bold"
        subtitle_font_size: str = "1.5em"
        subtitle_font_weight: str = "500"
        info_font_size: str = "1.1em"
        info_color: str = "#666"
        margin_top: str = "8px"
        margin_bottom: str = "4px"

    @dataclass
    class ProgressBar:
        size: str = "sm"

    @dataclass
    class CPUCores:
        max_columns: int = 4  # Number of columns to display cores in
        show_percentage: bool = True
        bar_height: str = "6px"
        core_label_size: str = "0.9em"

    @dataclass
    class Separator:
        margin_top: str = "12px"
        margin_bottom: str = "8px"

    @dataclass
    class ScriptSettings:
        supported_extensions: list = field(default_factory=lambda: [".sh", ".py"])
        default_script_type: str = "bash"
        python_executable: str = "python3"
        show_script_type_icons: bool = True

    @dataclass
    class MainContent:
        font_size: str = "1.8em"
        font_weight: str = "600"
        subtitle_font_size: str = "1em"
        subtitle_color: str = "#444"
        margin_top: str = "16px"
        margin_bottom: str = "12px"

    @dataclass
    class RedisSettings:
        host: str = "localhost"
        port: int = 6379  # Default Redis port
        db: int = 0
        enabled: bool = True  # Allow disabling Redis completely
        connection_timeout: int = 5  # seconds
        retry_attempts: int = 3
        session_history_days: int = 7  # Number of days to keep session history

    header: Header = field(default_factory=Header)
    sidebar: Sidebar = field(default_factory=Sidebar)
    labels: Labels = field(default_factory=Labels)
    progress_bar: ProgressBar = field(default_factory=ProgressBar)
    cpu_cores: CPUCores = field(default_factory=CPUCores)
    separator: Separator = field(default_factory=Separator)
    script_settings: ScriptSettings = field(default_factory=ScriptSettings)
    main_content: MainContent = field(default_factory=MainContent)
    redis: RedisSettings = field(default_factory=RedisSettings)

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


config = asdict(UISettings())
