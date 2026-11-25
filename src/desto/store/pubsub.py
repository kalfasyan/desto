import json
import threading
from typing import Callable, Dict

from .client import DestoRedisClient


class SessionPubSub:
    def __init__(self, redis_client: DestoRedisClient):
        self.redis = redis_client
        self.pubsub = self.redis.redis.pubsub()
        self.listeners = {}
        self.listening_thread = None

    def subscribe_to_session_updates(self, callback: Callable[[Dict], None]):
        """Subscribe to all session updates for dashboard."""
        self.pubsub.subscribe("desto:session_updates")
        self.listeners["session_updates"] = callback

        if not self.listening_thread:
            self.listening_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.listening_thread.start()

    def _listen_loop(self):
        """Background thread to listen for Redis pub/sub messages."""
        for message in self.pubsub.listen():
            if message["type"] == "message":
                channel = message["channel"]
                if channel in self.listeners:
                    try:
                        data = json.loads(message["data"])
                        self.listeners[channel](data)
                    except json.JSONDecodeError:
                        pass  # Skip invalid JSON
