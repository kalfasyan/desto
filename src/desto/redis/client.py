import redis


class DestoRedisClient:
    def __init__(self, config=None):
        if config is None:
            # Default config if none provided
            config = {
                "host": "localhost",
                "port": 6379,
                "db": 0,
                "connection_timeout": 5,
                "retry_attempts": 3,
                "enabled": True,
            }

        self.config = config
        self.redis = None
        self.session_prefix = "desto:session:"
        self.status_prefix = "desto:status:"

        # Only initialize Redis if enabled
        if self.config.get("enabled", True):
            self._initialize_redis()

    def _initialize_redis(self):
        """Initialize Redis connection with error handling"""
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
        except Exception as e:
            print(f"Redis connection failed: {e}")
            self.redis = None

    def is_connected(self) -> bool:
        """Check if Redis is available"""
        if not self.redis:
            return False
        try:
            self.redis.ping()
            return True
        except redis.ConnectionError:
            return False

    def get_session_key(self, session_name: str) -> str:
        return f"{self.session_prefix}{session_name}"

    def get_status_key(self, session_name: str) -> str:
        return f"{self.status_prefix}{session_name}"
