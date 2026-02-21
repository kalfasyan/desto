"""Favorites UI section for the dashboard."""

from loguru import logger
from nicegui import ui


class FavoritesTab:
    """Tab for managing and running favorite commands."""

    def __init__(self, ui_manager, desto_manager):
        self.ui_manager = ui_manager
        self.desto_manager = desto_manager
        self.favorites_container = None
        self.search_input = None
        self.favorite_name_input = None
        self.favorite_command_input = None

    def refresh_favorites_list(self):
        """Refresh the list of favorite commands."""
        if not self.desto_manager or not hasattr(self.desto_manager, "favorites_manager"):
            ui.notification("Favorites manager not available", type="warning")
            logger.warning("Favorites manager not available")
            return

        self.favorites_container.clear()

        search_query = self.search_input.value if self.search_input.value else ""
        if search_query:
            favorites = self.desto_manager.favorites_manager.search_favorites(search_query)
        else:
            favorites = self.desto_manager.favorites_manager.list_favorites(sort_by="use_count")

        if not favorites:
            with self.favorites_container:
                ui.label("No favorites saved yet").classes("text-slate-400 italic py-8 text-center w-full")
            return

        with self.favorites_container:
            with ui.grid(columns="repeat(auto-fill, minmax(300px, 1fr))").classes("w-full gap-4"):
                for favorite in favorites:
                    with ui.card().classes("modern-card p-6 bg-white dark:bg-slate-900 rounded-xl shadow-sm border border-slate-100 dark:border-slate-800"):
                        with ui.column().classes("w-full gap-3"):
                            with ui.row().classes("w-full justify-between items-start"):
                                ui.label(favorite.name).classes("text-lg font-bold text-slate-900 dark:text-white")
                                with ui.row().classes("gap-1"):
                                    ui.button(icon="play_arrow", on_click=lambda f=favorite: self._run_favorite(f.favorite_id, f.name, f.command)).props("flat round color=positive dense")
                                    ui.button(icon="edit", on_click=lambda f=favorite: self._edit_favorite(f.favorite_id)).props("flat round color=primary dense")
                                    ui.button(icon="delete", on_click=lambda f=favorite: self._delete_favorite(f.favorite_id, f.name)).props("flat round color=negative dense")

                            ui.label(favorite.command).classes("font-mono text-xs p-3 rounded-lg bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-400 break-all w-full")

                            with ui.row().classes("w-full justify-between items-center mt-2"):
                                with ui.row().classes("items-center gap-1 text-[10px] text-slate-400 uppercase tracking-wider"):
                                    ui.icon("trending_up", size="12px")
                                    ui.label(f"{favorite.use_count} uses")

                                if favorite.last_used_at:
                                    ui.label(f"Used {favorite.last_used_at.strftime('%m/%d %H:%M')}").classes("text-[10px] text-slate-400")

    def _run_favorite(self, favorite_id: str, favorite_name: str, command: str):
        """Run a favorite command in a new session."""
        session_name = f"fav-{favorite_name}"
        self.desto_manager.favorites_manager.increment_usage(favorite_id)
        try:
            self.ui_manager.tmux_manager.start_tmux_session(session_name, command, logger)
            ui.notification(f"Started session: {session_name}", type="positive")
            self.refresh_favorites_list()
        except Exception as e:
            logger.error(f"Failed to run favorite command: {e}")
            ui.notification(f"Failed to run favorite: {e}", type="negative")

    def _edit_favorite(self, favorite_id: str):
        """Open a dialog to edit a favorite."""
        favorite = self.desto_manager.favorites_manager.get_favorite(favorite_id)
        if not favorite:
            ui.notification("Favorite not found", type="warning")
            return

        with ui.dialog() as dialog:
            with ui.card().classes("p-6 w-96"):
                ui.label("Edit Favorite").classes("text-xl font-bold mb-4")
                name_input = ui.input(label="Name", value=favorite.name).classes("w-full")
                command_input = ui.textarea(label="Command", value=favorite.command).classes("w-full h-32")

                with ui.row().classes("w-full justify-end gap-2 mt-6"):
                    ui.button("Cancel", on_click=dialog.close).props("flat color=slate-500")
                    ui.button("Save Changes", on_click=lambda: self._save_favorite_edit(favorite_id, name_input, command_input, dialog)).props("unelevated color=primary")

        dialog.open()

    def _save_favorite_edit(self, favorite_id: str, name_input, command_input, dialog):
        """Save changes to a favorite."""
        new_name = name_input.value.strip()
        new_command = command_input.value.strip()
        if not new_name or not new_command:
            ui.notification("Name and command required", type="warning")
            return
        result = self.desto_manager.favorites_manager.update_favorite(favorite_id, name=new_name, command=new_command)
        if result:
            ui.notification(f"Updated: {new_name}", type="positive")
            dialog.close()
            self.refresh_favorites_list()
        else:
            ui.notification("Failed to update", type="negative")

    def _delete_favorite(self, favorite_id: str, favorite_name: str):
        """Delete a favorite with confirmation."""
        with ui.dialog() as confirm_dialog:
            with ui.card().classes("p-6"):
                ui.label(f"Delete '{favorite_name}'?").classes("text-lg font-bold mb-2")
                ui.label("This action cannot be undone.").classes("text-slate-500 mb-6")
                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancel", on_click=confirm_dialog.close).props("flat color=slate-500")
                    ui.button("Delete Permanent", on_click=lambda: self._confirm_delete(favorite_id, favorite_name, confirm_dialog)).props("unelevated color=negative")
        confirm_dialog.open()

    def _confirm_delete(self, favorite_id: str, favorite_name: str, dialog):
        """Confirm deletion of a favorite."""
        result = self.desto_manager.favorites_manager.delete_favorite(favorite_id)
        if result:
            ui.notification(f"Deleted: {favorite_name}", type="positive")
            dialog.close()
            self.refresh_favorites_list()
        else:
            ui.notification("Failed to delete", type="negative")

    def _save_as_favorite(self, session_name_input, command_input):
        """Save the current command as a favorite."""
        if not command_input.value.strip():
            ui.notification("Command cannot be empty", type="warning")
            return
        with ui.dialog() as dialog:
            with ui.card().classes("p-6 w-96"):
                ui.label("Save as Favorite").classes("text-xl font-bold mb-4")
                name_input = ui.input(label="Favorite Name", value=session_name_input.value if session_name_input.value else "").classes("w-full")
                with ui.row().classes("w-full justify-end gap-2 mt-6"):
                    ui.button("Cancel", on_click=dialog.close).props("flat color=slate-500")
                    ui.button("Save Favorite", on_click=lambda: self._save_new_favorite(name_input, command_input, dialog)).props("unelevated color=primary")
        dialog.open()

    def _save_new_favorite(self, name_input, command_input, dialog):
        """Create a new favorite."""
        name = name_input.value.strip()
        command = command_input.value.strip()
        if not name or not command:
            ui.notification("Name and command required", type="warning")
            return
        result = self.desto_manager.favorites_manager.add_favorite(name, command)
        if result:
            ui.notification(f"Saved: {name}", type="positive")
            dialog.close()
            self.refresh_favorites_list()
        else:
            ui.notification("Failed to save (name may exist)", type="negative")

    def build(self):
        """Build the favorites tab UI."""
        with ui.card().classes("modern-card w-full p-6 bg-white dark:bg-slate-900 rounded-xl shadow-sm"):
            with ui.row().classes("w-full justify-between items-center mb-6"):
                ui.label("Favorite Commands").classes("text-lg font-bold text-slate-900 dark:text-white")
                self.search_input = ui.input(placeholder="Search favorites...").on("keyup", lambda: self.refresh_favorites_list()).props("dense outlined rounded").classes("w-64")
            self.favorites_container = ui.column().classes("w-full")
            self.refresh_favorites_list()
