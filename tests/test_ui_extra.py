from unittest.mock import MagicMock, patch

from desto.app.ui import UserInterfaceManager


def make_ui_manager(tmp_path):
    mock_ui = MagicMock()
    mock_settings = {}
    mock_tmux = MagicMock()
    mock_tmux.SCRIPTS_DIR = tmp_path
    mock_tmux.LOG_DIR = tmp_path
    return UserInterfaceManager(mock_ui, mock_settings, mock_tmux)


def test_refresh_script_list_empty(tmp_path):
    ui_manager = make_ui_manager(tmp_path)
    ui_manager.script_path_select = MagicMock()
    ui_manager.refresh_script_list()
    assert ui_manager.script_path_select.value == "No scripts found"


def test_update_script_preview_missing(tmp_path):
    ui_manager = make_ui_manager(tmp_path)
    ui_manager.script_path_select = MagicMock()
    ui_manager.script_preview_editor = MagicMock()

    class E:
        args = "notfound.sh"

    ui_manager.update_script_preview(E())
    assert ui_manager.script_preview_editor.value.startswith("# Script not found")


def test_chain_current_script(tmp_path):
    ui_manager = make_ui_manager(tmp_path)
    ui_manager.script_path_select = MagicMock()
    ui_manager.script_path_select.value = "myscript.sh"
    ui_manager.arguments_input = MagicMock()
    ui_manager.arguments_input.value = "foo"
    (tmp_path / "myscript.sh").write_text("echo hi")
    ui_manager.tmux_manager.SCRIPTS_DIR = tmp_path
    ui_manager.chain_queue = []
    ui_manager.refresh_chain_queue_display = MagicMock()
    with patch("desto.app.ui.ui.notification") as mock_note:
        ui_manager.chain_current_script()
        assert len(ui_manager.chain_queue) == 1
        mock_note.assert_called()


def test_get_log_info_block(tmp_path):
    ui_manager = make_ui_manager(tmp_path)
    info = ui_manager.get_log_info_block(tmp_path / "myscript.sh", "sess")
    assert "# Script: myscript.sh" in info


def test_refresh_chain_queue_display_empty(tmp_path):
    ui_manager = make_ui_manager(tmp_path)
    ui_manager.chain_queue_display = MagicMock()
    ui_manager.chain_queue = []
    with patch("desto.app.ui.logger"):
        ui_manager.refresh_chain_queue_display()
