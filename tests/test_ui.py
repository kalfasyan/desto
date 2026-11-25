from unittest.mock import MagicMock

from desto.app.ui import UserInterfaceManager


def test_ui_manager_instantiates():
    mock_ui = MagicMock()
    mock_settings = {}
    mock_tmux = MagicMock()
    ui_manager = UserInterfaceManager(mock_ui, mock_settings, mock_tmux)
    assert isinstance(ui_manager, UserInterfaceManager)
