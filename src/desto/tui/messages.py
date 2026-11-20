"""Messages panes post so other panes can refresh, without knowing about each other."""

from textual.message import Message


class SessionsChanged(Message):
    """A session was launched, scheduled or removed."""


class FavoritesChanged(Message):
    """A favorite was added, changed or removed."""
