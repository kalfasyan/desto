"""The Scripts tab: pick, edit, create and delete scripts, then launch, chain, schedule or save them as favorites."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from desto.core import scripts
from desto.core.service import DestoService
from desto.tui.messages import FavoritesChanged, SessionsChanged
from desto.tui.modals import ConfirmScreen, FormScreen, ScheduleScreen

LANGUAGES = {"python": "python", "bash": "bash"}


def _name_error(values: dict) -> str | None:
    return None if scripts.is_valid_name(values["name"].replace(" ", "_")) else f"Use 1-{scripts.MAX_NAME_LENGTH} letters, digits, '_' or '-'."


class ScriptsPane(Horizontal):
    BINDINGS = [
        Binding("ctrl+r", "launch", "Launch"),
        Binding("ctrl+t", "schedule", "Schedule"),
        Binding("ctrl+b", "add_to_chain", "Add to chain"),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+n", "new_script", "New script"),
    ]

    def __init__(self, service: DestoService, **kwargs) -> None:
        super().__init__(**kwargs)
        self.service = service
        self.current: str | None = None  # file name of the script in the editor
        self.dirty = False
        self.chain: list[tuple[str, str]] = []  # (script path, arguments)
        self._saved_text = ""  # editor text as last loaded or saved

    def compose(self) -> ComposeResult:
        with Vertical(id="script-list-col"):
            yield Label("Scripts", classes="section-title")
            yield OptionList(id="script-list")
            with Horizontal(classes="buttons"):
                yield Button("New", id="new-script")
                yield Button("Delete", id="delete-script", variant="error")
        with Vertical(id="script-editor-col"):
            with Horizontal(classes="form-row"):
                with Vertical():
                    yield Label("Session name", classes="field-label")
                    yield Input(placeholder="e.g. build-task", id="session-name")
                with Vertical():
                    yield Label("Arguments", classes="field-label")
                    yield Input(".", id="arguments")
            yield TextArea.code_editor("", id="editor", soft_wrap=True)
            with Horizontal(classes="buttons"):
                yield Button("▶ Launch", id="launch", variant="success")
                yield Button("Schedule…", id="schedule", variant="primary")
                yield Button("+ Chain", id="add-to-chain")
                yield Button("★ Favorite", id="favorite", variant="warning")
                yield Button("Save", id="save")
                yield Button("Save as…", id="save-as")
            with Horizontal(id="chain-row"):
                yield Static("", id="chain")
                yield Button("Clear chain", id="clear-chain")

    def on_mount(self) -> None:
        self.reload_scripts()
        self.show_chain()

    # --- Script list and editor -----------------------------------------------------

    def reload_scripts(self, select: str | None = None) -> None:
        """Re-read the scripts directory and select `select` (or keep the current script)."""
        names = scripts.list_scripts(self.service.SCRIPTS_DIR)
        option_list = self.query_one("#script-list", OptionList)
        option_list.clear_options()
        option_list.add_options([Option(f"{scripts.script_icon(scripts.script_type(n))} {n}", id=n) for n in names])
        target = select if select in names else self.current if self.current in names else (names[0] if names else None)
        if target:
            option_list.highlighted = names.index(target)
            self.open_script(target)
        else:
            self.current = None
            self._load_editor("", None)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id != self.current:
            self.open_script(event.option.id)

    def open_script(self, name: str) -> None:
        if self.dirty and self.current:
            self.notify(f"Unsaved changes to {self.current} were discarded.", severity="warning")
        self.current = name
        path = self.service.get_script_file(name)
        self._load_editor(path.read_text() if path.is_file() else "", LANGUAGES.get(scripts.script_type(name)))
        session_input = self.query_one("#session-name", Input)
        if not session_input.value:
            session_input.value = Path(name).stem[: scripts.MAX_NAME_LENGTH]

    def _load_editor(self, text: str, language: str | None) -> None:
        editor = self.query_one("#editor", TextArea)
        editor.language = language
        editor.load_text(text)
        self._saved_text = text
        self.dirty = False

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        # load_text() posts Changed too, so compare with the saved text rather than flagging every event
        self.dirty = event.text_area.text != self._saved_text

    # --- Buttons --------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "launch": self.action_launch,
            "schedule": self.action_schedule,
            "add-to-chain": self.action_add_to_chain,
            "favorite": self.action_favorite,
            "save": self.action_save,
            "save-as": self.action_save_as,
            "new-script": self.action_new_script,
            "delete-script": self.action_delete_script,
            "clear-chain": self.action_clear_chain,
        }
        actions[event.button.id]()

    def _session_name(self) -> str:
        return self.query_one("#session-name", Input).value.strip()

    def _arguments(self) -> str:
        return self.query_one("#arguments", Input).value

    def _selected_path(self) -> Path | None:
        if not self.current:
            self.notify("Select a script first.", severity="warning")
            return None
        return self.service.get_script_file(self.current)

    def _launch_plan(self):
        """(command, script paths, description) for the chain if there is one, else for the selected script."""
        python = self.service.python_executable
        if self.chain:
            return scripts.chain_command(self.chain, python), [p for p, _ in self.chain], f"chain of {len(self.chain)} scripts"
        path = self._selected_path()
        if path is None:
            return None
        return scripts.launch_command(path, self._arguments(), python), [path], path.name

    def action_launch(self) -> None:
        if self.dirty:
            self.notify("Please save changes before launching.", severity="warning")
            return
        name = self._session_name()
        if not name:
            self.notify("Please enter a session name.", severity="warning")
            return
        plan = self._launch_plan()
        if plan and self.service.start_tmux_session(name, plan[0]):
            self.action_clear_chain(quiet=True)
            self.post_message(SessionsChanged())

    def action_schedule(self) -> None:
        plan = self._launch_plan()
        if not plan:
            return
        command, paths, what = plan

        def schedule(when, interval_minutes):
            return self.service.schedule_launch(self._session_name(), command, paths, self._arguments(), when, interval_minutes)

        def done(scheduled: bool | None) -> None:
            if scheduled:
                self.action_clear_chain(quiet=True)
                self.post_message(SessionsChanged())

        self.app.push_screen(ScheduleScreen(what, schedule), done)

    def action_add_to_chain(self) -> None:
        path = self._selected_path()
        if path:
            self.chain.append((str(path), self._arguments()))
            self.notify(f"Added {path.name} to the chain.")
            self.show_chain()

    def action_clear_chain(self, quiet: bool = False) -> None:
        if self.chain and not quiet:
            self.notify(f"Cleared {len(self.chain)} item(s) from the chain.")
        self.chain.clear()
        self.show_chain()

    def show_chain(self) -> None:
        self.query_one("#chain-row").display = bool(self.chain)
        steps = "  →  ".join(f"[b]{i}[/] {Path(p).name} [dim]{args}[/]" for i, (p, args) in enumerate(self.chain, 1))
        self.query_one("#chain", Static).update(f"Chain: {steps}   [dim](launch runs them in order; ctrl+b adds the selected script)[/]")

    def action_favorite(self) -> None:
        path = self._selected_path()
        if not path:
            return
        command = scripts.build_execution_command(path, self._arguments(), self.service.python_executable)

        def done(values: dict | None) -> None:
            if not values:
                return
            if self.service.desto_manager.favorites_manager.add_favorite(values["name"], values["command"]):
                self.notify(f"Saved favorite: {values['name']}")
                self.post_message(FavoritesChanged())
            else:
                self.notify("Failed to save (name may exist)", severity="error")

        fields = [("name", "Favorite name", self._session_name() or path.stem), ("command", "Command", command)]
        self.app.push_screen(FormScreen("Save as favorite", fields, validate=lambda v: None if v["name"] and v["command"] else "Name and command are required."), done)

    def action_save(self) -> None:
        path = self._selected_path()
        if not path:
            return
        self._saved_text = self.query_one("#editor", TextArea).text
        path.write_text(self._saved_text)
        path.chmod(0o755)
        self.dirty = False
        self.notify(f"Saved changes to {path.name}")

    def action_save_as(self) -> None:
        kind = scripts.script_type(self.current or "") if self.current else "bash"
        self._create_script("Save as new script", self.query_one("#editor", TextArea).text, "bash" if kind == "unknown" else kind)

    def action_new_script(self) -> None:
        def done(values: dict | None) -> None:
            if values:
                kind = "python" if values["type"].lower().startswith("p") else "bash"
                self._write_new(values["name"], scripts.TEMPLATES[kind], kind)

        fields = [("name", f"Script name (max {scripts.MAX_NAME_LENGTH} characters)", ""), ("type", "Type: bash or python", "bash")]
        self.app.push_screen(FormScreen("New script", fields, "Create", validate=_name_error), done)

    def _create_script(self, title: str, code: str, kind: str) -> None:
        def done(values: dict | None) -> None:
            if values:
                self._write_new(values["name"], code, kind)

        self.app.push_screen(FormScreen(title, [("name", f"Script name (max {scripts.MAX_NAME_LENGTH} characters)", "")], validate=_name_error), done)

    def _write_new(self, name: str, code: str, kind: str) -> None:
        target = self.service.get_script_file(f"{name.replace(' ', '_')}{scripts.EXTENSIONS[kind]}")
        if target.exists():
            self.notify(f"{target.name} already exists.", severity="error")
            return
        path = scripts.create_script(self.service.SCRIPTS_DIR, name, code, kind)
        self.dirty = False
        self.reload_scripts(select=path.name)
        self.notify(f"Created {path.name}")

    def action_delete_script(self) -> None:
        path = self._selected_path()
        if not path:
            return

        def done(confirmed: bool | None) -> None:
            if confirmed:
                path.unlink(missing_ok=True)
                self.dirty = False
                self.current = None
                self.reload_scripts()
                self.notify(f"Deleted script: {path.name}")

        self.app.push_screen(ConfirmScreen("Delete script", f"Delete '{path.name}'? This cannot be undone.", "Delete"), done)
