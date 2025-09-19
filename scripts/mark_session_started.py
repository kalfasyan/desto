#!/usr/bin/env python3
"""Helper script to mark session started in Redis.
This is called from within tmux sessions when sessions start.
"""

import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from src.desto.redis.client import DestoRedisClient
    from src.desto.redis.desto_manager import DestoManager

    if len(sys.argv) != 3:
        print("Usage: mark_session_started.py <session_name> <command>", file=sys.stderr)
        sys.exit(1)

    session_name = sys.argv[1]
    command = sys.argv[2]

    # Try to mark session as started in Redis
    client = DestoRedisClient()
    if client.is_connected():
        manager = DestoManager(client)
        # Note: Session should already be created by TmuxManager
        # This script is mainly for backward compatibility
        print(f"Session '{session_name}' tracking is handled by TmuxManager")
    else:
        print("Redis not available, skipping session tracking", file=sys.stderr)

except ImportError as e:
    print(f"Could not import Redis modules: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Error marking session started: {e}", file=sys.stderr)
    sys.exit(1)
