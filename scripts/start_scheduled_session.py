#!/usr/bin/env python3
"""Backward-compatible shim for sessions and ``at`` jobs created by older desto versions.

Use ``python -m desto.hooks.start_scheduled_session`` instead.
"""

import sys
from pathlib import Path

# Allow running from a source checkout without desto installed
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from desto.hooks.start_scheduled_session import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
