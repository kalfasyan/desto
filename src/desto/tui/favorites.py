"""The Favorites tab: saved commands to run again, edit, delete or search."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Input

from desto.core.service import DestoService
from desto.tui.messages import SessionsChanged
from desto.tui.modals import ConfirmScreen, FormScreen


def _required(values: dict) -> str | None:
    return None if values["name"] and values["command"] else "Name and command are required."


class FavoritesPane(Vertical):
    BINDINGS = [
        Binding("n", "new", "New"),
        Binding("e", "edit", "Edit"),
        Binding("d", "delete", "Delete"),
        Binding("D", "delete_all", "Delete all"),
        Binding("slash", "search", "Search"),
    ]

    def __init__(self, service: DestoService, **kwargs) -> None:
        super().__init__(**kwargs)
        self.service = service
        self.favorites = []

    @property
    def manager(self):
        return self.service.desto_manager.favorites_manager

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search favorites…  (enter on a row runs it)", id="favorites-search")
        yield DataTable(id="favorites-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        self.query_one(DataTable).add_columns("Name", "Command", "Uses", "Last used")
        self.reload()

    def reload(self) -> None:
        self.favorites = self.service.list_favorites(self.query_one("#favorites-search", Input).value.strip())
        table = self.query_one(DataTable)
        table.clear()
        for fav in self.favorites:
            last_used = fav.last_used_at.strftime("%Y-%m-%d %H:%M") if fav.last_used_at else "never"
            table.add_row(fav.name, fav.command, str(fav.use_count), last_used, key=fav.favorite_id)

    def on_input_changed(self, event: Input.Changed) -> None:
        self.reload()

    def selected(self):
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return None
        return self.favorites[table.cursor_row] if table.cursor_row < len(self.favorites) else None

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        favorite = self.selected()
        if favorite and self.service.run_favorite(favorite.favorite_id, favorite.name, favorite.command):
            self.reload()
            self.post_message(SessionsChanged())

    def action_search(self) -> None:
        self.query_one("#favorites-search", Input).focus()

    def action_new(self) -> None:
        def done(values: dict | None) -> None:
            if values:
                if self.manager.add_favorite(values["name"], values["command"]):
                    self.notify(f"Saved: {values['name']}")
                    self.reload()
                else:
                    self.notify("Failed to save (name may exist)", severity="error")

        self.app.push_screen(FormScreen("New favorite", [("name", "Name", ""), ("command", "Command", "")], validate=_required), done)

    def action_edit(self) -> None:
        favorite = self.selected()
        if not favorite:
            return

        def done(values: dict | None) -> None:
            if values:
                if self.manager.update_favorite(favorite.favorite_id, name=values["name"], command=values["command"]):
                    self.notify(f"Updated: {values['name']}")
                    self.reload()
                else:
                    self.notify("Failed to update", severity="error")

        fields = [("name", "Name", favorite.name), ("command", "Command", favorite.command)]
        self.app.push_screen(FormScreen("Edit favorite", fields, "Save changes", validate=_required), done)

    def action_delete(self) -> None:
        favorite = self.selected()
        if not favorite:
            return

        def done(confirmed: bool | None) -> None:
            if confirmed and self.manager.delete_favorite(favorite.favorite_id):
                self.notify(f"Deleted: {favorite.name}")
                self.reload()

        self.app.push_screen(ConfirmScreen("Delete favorite", f"Delete '{favorite.name}'? This cannot be undone.", "Delete"), done)

    def action_delete_all(self) -> None:
        count = len(self.manager.list_favorites())
        if not count:
            self.notify("No favorites to clear")
            return

        def done(values: dict | None) -> None:
            if values:
                self.notify(f"Deleted {self.service.clear_all_favorites()} favorite(s)")
                self.reload()

        message = f'This permanently deletes all {count} favorite(s). Type "DELETE" to confirm.'
        self.app.push_screen(
            FormScreen("Delete ALL favorites", [("confirm", message, "")], "Delete all", validate=lambda v: None if v["confirm"] == "DELETE" else 'Type "DELETE" to confirm.'),
            done,
        )
