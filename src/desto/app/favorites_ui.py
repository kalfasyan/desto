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

        # Clear the container
        self.favorites_container.clear()

        # Get favorites
        search_query = self.search_input.value if self.search_input.value else ""
        if search_query:
            favorites = self.desto_manager.favorites_manager.search_favorites(search_query)
        else:
            favorites = self.desto_manager.favorites_manager.list_favorites(sort_by="use_count")

        if not favorites:
            with self.favorites_container:
                ui.label("No favorites saved yet").style("color: #999; font-style: italic;")
            return

        # Display favorites
        for favorite in favorites:
            with self.favorites_container:
                with ui.card().style("width: 100%; margin-bottom: 10px; padding: 10px;"):
                    with ui.row().style("width: 100%; justify-content: space-between; align-items: start;"):
                        with ui.column().style("flex: 1;"):
                            ui.label(favorite.name).style("font-weight: bold; font-size: 1.1em; margin-bottom: 5px;")
                            ui.label(favorite.command).style("color: #666; font-family: monospace; font-size: 0.9em; word-break: break-all; padding: 5px; background-color: #f5f5f5; border-radius: 3px;")
                            with ui.row().style("margin-top: 8px; font-size: 0.85em; color: #999;"):
                                ui.label(f"Used {favorite.use_count} times")
                                if favorite.last_used_at:
                                    ui.label(f"Last used: {favorite.last_used_at.strftime('%Y-%m-%d %H:%M')}")

                        with ui.column().style("align-items: end;"):
                            with ui.row().style("gap: 5px;"):
                                # Run button
                                ui.button(
                                    icon="play_arrow",
                                    on_click=lambda fav_id=favorite.favorite_id, fav_name=favorite.name, cmd=favorite.command: self._run_favorite(fav_id, fav_name, cmd),
                                ).props("size=sm").style("color: #4CAF50;")

                                # Edit button
                                ui.button(
                                    icon="edit",
                                    on_click=lambda fav_id=favorite.favorite_id: self._edit_favorite(fav_id),
                                ).props("size=sm").style("color: #2196F3;")

                                # Delete button
                                ui.button(
                                    icon="delete",
                                    on_click=lambda fav_id=favorite.favorite_id, fav_name=favorite.name: self._delete_favorite(fav_id, fav_name),
                                ).props("size=sm").style("color: #f44336;")

    def _run_favorite(self, favorite_id: str, favorite_name: str, command: str):
        """Run a favorite command in a new session."""
        session_name = f"fav-{favorite_name}"

        # Increment usage
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

        # Create edit dialog
        with ui.dialog() as dialog:
            with ui.card().style("min-width: 400px;"):
                ui.label("Edit Favorite").style("font-weight: bold; font-size: 1.2em; margin-bottom: 15px;")

                name_input = ui.input(label="Name", value=favorite.name)
                command_input = ui.textarea(label="Command", value=favorite.command).style("min-height: 100px;")

                with ui.row().style("justify-content: end; gap: 10px; margin-top: 15px;"):
                    ui.button(
                        "Cancel",
                        on_click=lambda: dialog.close(),
                        color="gray",
                    )
                    ui.button(
                        "Save",
                        on_click=lambda: self._save_favorite_edit(favorite_id, name_input, command_input, dialog),
                        color="primary",
                    )

        dialog.open()

    def _save_favorite_edit(self, favorite_id: str, name_input, command_input, dialog):
        """Save changes to a favorite."""
        new_name = name_input.value.strip()
        new_command = command_input.value.strip()

        if not new_name or not new_command:
            ui.notification("Name and command cannot be empty", type="warning")
            return

        result = self.desto_manager.favorites_manager.update_favorite(favorite_id, name=new_name, command=new_command)

        if result:
            ui.notification(f"Updated favorite: {new_name}", type="positive")
            dialog.close()
            self.refresh_favorites_list()
        else:
            ui.notification("Failed to update favorite (name may already exist)", type="negative")

    def _delete_favorite(self, favorite_id: str, favorite_name: str):
        """Delete a favorite with confirmation."""
        with ui.dialog() as confirm_dialog:
            with ui.card().style("min-width: 300px;"):
                ui.label(f"Delete '{favorite_name}'?").style("font-weight: bold; margin-bottom: 15px;")
                ui.label("This action cannot be undone.").style("color: #999; margin-bottom: 15px;")

                with ui.row().style("justify-content: end; gap: 10px;"):
                    ui.button(
                        "Cancel",
                        on_click=lambda: confirm_dialog.close(),
                        color="gray",
                    )
                    ui.button(
                        "Delete",
                        on_click=lambda: self._confirm_delete(favorite_id, favorite_name, confirm_dialog),
                        color="negative",
                    )

        confirm_dialog.open()

    def _confirm_delete(self, favorite_id: str, favorite_name: str, dialog):
        """Confirm deletion of a favorite."""
        result = self.desto_manager.favorites_manager.delete_favorite(favorite_id)

        if result:
            ui.notification(f"Deleted favorite: {favorite_name}", type="positive")
            dialog.close()
            self.refresh_favorites_list()
        else:
            ui.notification("Failed to delete favorite", type="negative")

    def _save_as_favorite(self, session_name_input, command_input):
        """Save the current command as a favorite."""
        if not command_input.value.strip():
            ui.notification("Command cannot be empty", type="warning")
            return

        with ui.dialog() as dialog:
            with ui.card().style("min-width: 400px;"):
                ui.label("Save as Favorite").style("font-weight: bold; font-size: 1.2em; margin-bottom: 15px;")
                ui.label("Enter a name for this favorite:").style("margin-bottom: 10px;")

                name_input = ui.input(label="Favorite Name", value=session_name_input.value if session_name_input.value else "")

                with ui.row().style("justify-content: end; gap: 10px; margin-top: 15px;"):
                    ui.button(
                        "Cancel",
                        on_click=lambda: dialog.close(),
                        color="gray",
                    )
                    ui.button(
                        "Save",
                        on_click=lambda: self._save_new_favorite(name_input, command_input, dialog),
                        color="primary",
                    )

        dialog.open()

    def _save_new_favorite(self, name_input, command_input, dialog):
        """Create a new favorite."""
        name = name_input.value.strip()
        command = command_input.value.strip()

        if not name or not command:
            ui.notification("Name and command cannot be empty", type="warning")
            return

        result = self.desto_manager.favorites_manager.add_favorite(name, command)

        if result:
            ui.notification(f"Saved favorite: {name}", type="positive")
            dialog.close()
            self.refresh_favorites_list()
        else:
            ui.notification("Failed to save favorite (name may already exist)", type="negative")

    def build(self):
        """Build the favorites tab UI."""
        with ui.card().style("background-color: #fff; color: #000; padding: 20px; border-radius: 8px; width: 100%; margin-left: 0; margin-right: 0;"):
            ui.label("Favorite Commands").style("font-weight: bold; font-size: 1.3em; margin-bottom: 15px;")

            # Search box
            self.search_input = (
                ui.input(
                    label="Search",
                    placeholder="Filter by name or command...",
                )
                .on("keyup", lambda: self.refresh_favorites_list())
                .style("width: 100%; margin-bottom: 15px;")
            )

            # Favorites list
            self.favorites_container = ui.column().style("width: 100%; gap: 0;")
            self.refresh_favorites_list()
