"""Desto CLI package for command-line interface functionality."""

from .._version import __version__
from .main import app
from .session_manager import CLISessionManager

__all__ = ["app", "CLISessionManager", "__version__"]
