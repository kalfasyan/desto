import os

import redis
from loguru import logger


class DestoRedisClient:
    def __init__(self, config=None):
        if config is None:
            # Default config if none provided, with environment variable support
            config = {
                "host": os.getenv("REDIS_HOST", "localhost"),
                "port": int(os.getenv("REDIS_PORT", "6379")),
                "db": int(os.getenv("REDIS_DB", "0")),
                "connection_timeout": int(os.getenv("REDIS_CONNECTION_TIMEOUT", "5")),
                "retry_attempts": int(os.getenv("REDIS_RETRY_ATTEMPTS", "3")),
                "enabled": os.getenv("REDIS_ENABLED", "true").lower() in ("true", "1", "yes", "on"),
            }

        self.config = config
        self.redis = None
        self.session_prefix = "desto:session:"
        self.status_prefix = "desto:status:"

        # Only initialize Redis if enabled
        if self.config.get("enabled", True):
            self._initialize_redis()

    def _initialize_redis(self):
        """Initialize Redis connection with error handling."""
        try:
            self.redis = redis.Redis(
                host=self.config["host"],
                port=self.config["port"],
                db=self.config["db"],
                socket_timeout=self.config.get("connection_timeout", 5),
                decode_responses=True,
            )
            # Test connection
            self.redis.ping()
            logger.info(f"Redis connected successfully at {self.config['host']}:{self.config['port']}")
        except redis.ConnectionError as e:
            logger.error(f"Redis connection failed: {e}")
            logger.error(f"Attempted to connect to {self.config['host']}:{self.config['port']}")
            logger.warning("Redis features will be disabled. Application will use file-based tracking.")
            self.redis = None
        except Exception as e:
            logger.error(f"Redis initialization error: {e}")
            self.redis = None

    def is_connected(self) -> bool:
        """Check if Redis is available."""
        if not self.redis:
            return False
        try:
            self.redis.ping()
            return True
        except redis.ConnectionError:
            return False
        except Exception:
            return False

    def get_session_key(self, session_name: str) -> str:
        return f"{self.session_prefix}{session_name}"

    def get_status_key(self, session_name: str) -> str:
        return f"{self.status_prefix}{session_name}"
