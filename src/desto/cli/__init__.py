"""Desto CLI package for command-line interface functionality."""

from .main import app
from .session_manager import CLISessionManager
from .._version import __version__

__all__ = ["app", "CLISessionManager", "__version__"]
