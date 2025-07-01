from unittest.mock import MagicMock

from desto.app.ui import UserInterfaceManager


def test_ui_manager_instantiates():
    mock_ui = MagicMock()
    mock_settings = {
        "header": {"background_color": "#fff", "color": "#000", "font_size": "1em"},
        "sidebar": {
            "width": "200px",
            "padding": "10px",
            "background_color": "#eee",
            "border_radius": "8px",
        },
        "labels": {
            "title_font_size": "1em",
            "title_font_weight": "bold",
            "subtitle_font_weight": "normal",
            "subtitle_font_size": "1em",
            "info_font_size": "1em",
            "info_color": "#888",
        },
        "progress_bar": {"size": "1em"},
    }
    mock_tmux = MagicMock()
    ui_manager = UserInterfaceManager(mock_ui, mock_settings, mock_tmux)
    assert isinstance(ui_manager, UserInterfaceManager)
