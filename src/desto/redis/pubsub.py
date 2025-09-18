import json
import threading
from datetime import datetime
from typing import Any, Callable, Dict

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

    def subscribe_to_specific_session(self, session_name: str, callback: Callable[[Dict], None]):
        """Subscribe to specific session updates."""
        channel = f"desto:session:{session_name}"
        self.pubsub.subscribe(channel)
        self.listeners[channel] = callback

    def publish_session_update(self, session_name: str, data: Dict[str, Any]):
        """Publish session update."""
        update_data = {"session_name": session_name, "timestamp": datetime.now().isoformat(), **data}

        # General updates channel
        self.redis.redis.publish("desto:session_updates", json.dumps(update_data))

        # Specific session channel
        self.redis.redis.publish(f"desto:session:{session_name}", json.dumps(update_data))

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

    def stop_listening(self):
        """Stop listening to pub/sub."""
        if self.listening_thread:
            self.pubsub.unsubscribe()
            self.listening_thread = None
