from loguru import logger
import psutil
from nicegui import ui
from pathlib import Path
import os
from desto.app.templates import TEMPLATES


class SystemStatsPanel:
    def __init__(self, ui_settings):
        self.ui_settings = ui_settings
        self.cpu_percent = None
        self.cpu_bar = None
        self.memory_percent = None
        self.memory_bar = None
        self.memory_available = None
        self.memory_used = None
        self.disk_percent = None
        self.disk_bar = None
        self.disk_free = None
        self.disk_used = None
        self.tmux_cpu = None
        self.tmux_mem = None

    def build(self):
        with ui.column():
            ui.label("System Stats").style(
                f"font-size: {self.ui_settings['labels']['title_font_size']}; "
                f"font-weight: {self.ui_settings['labels']['title_font_weight']}; "
                "margin-bottom: 10px;"
            )
            ui.label("CPU Usage").style(
                f"font-weight: {self.ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;"
            )
            with ui.row().style("align-items: center"):
                ui.icon("memory", size="1.2rem")
                self.cpu_percent = ui.label("0%").style(
                    f"font-size: {self.ui_settings['labels']['subtitle_font_size']}; margin-left: 5px;"
                )
            self.cpu_bar = ui.linear_progress(
                value=0, size=self.ui_settings["progress_bar"]["size"], show_value=False
            )
            ui.label("Memory Usage").style(
                f"font-weight: {self.ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;"
            )
            with ui.row().style("align-items: center"):
                ui.icon("developer_board", size="1.2rem")
                self.memory_percent = ui.label("0%").style(
                    f"font-size: {self.ui_settings['labels']['subtitle_font_size']}; margin-left: 5px;"
                )
            self.memory_bar = ui.linear_progress(
                value=0, size=self.ui_settings["progress_bar"]["size"], show_value=False
            )
            self.memory_used = ui.label("0 GB Used").style(
                f"font-size: {self.ui_settings['labels']['info_font_size']}; color: {self.ui_settings['labels']['info_color']};"
            )
            self.memory_available = ui.label("0 GB Available").style(
                f"font-size: {self.ui_settings['labels']['info_font_size']}; color: {self.ui_settings['labels']['info_color']};"
            )
            ui.label("Disk Usage").style(
                f"font-weight: {self.ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;"
            )
            with ui.row().style("align-items: center"):
                ui.icon("storage", size="1.2rem")
                self.disk_percent = ui.label("0%").style(
                    f"font-size: {self.ui_settings['labels']['subtitle_font_size']}; margin-left: 5px;"
                )
            self.disk_bar = ui.linear_progress(
                value=0, size=self.ui_settings["progress_bar"]["size"], show_value=False
            )
            self.disk_used = ui.label("0 GB Used").style(
                f"font-size: {self.ui_settings['labels']['info_font_size']}; color: {self.ui_settings['labels']['info_color']};"
            )
            self.disk_free = ui.label("0 GB Free").style(
                f"font-size: {self.ui_settings['labels']['info_font_size']}; color: {self.ui_settings['labels']['info_color']};"
            )
            self.tmux_cpu = ui.label("tmux CPU: N/A").style(
                f"font-size: {self.ui_settings['labels']['info_font_size']}; color: #888; margin-top: 20px;"
            )
            self.tmux_mem = ui.label("tmux MEM: N/A").style(
                f"font-size: {self.ui_settings['labels']['info_font_size']}; color: #888;"
            )


class SettingsPanel:
    def __init__(self, tmux_manager, ui_manager=None):
        self.tmux_manager = tmux_manager
        self.ui_manager = ui_manager
        self.scripts_dir_input = None
        self.logs_dir_input = None

    def build(self):
        ui.label("Settings").style(
            "font-size: 1.5em; font-weight: bold; margin-bottom: 20px; text-align: center;"
        )
        self.scripts_dir_input = ui.input(
            label="Scripts Directory",
            value=str(self.tmux_manager.SCRIPTS_DIR),
        ).style("width: 100%; margin-bottom: 10px;")
        self.logs_dir_input = ui.input(
            label="Logs Directory",
            value=str(self.tmux_manager.LOG_DIR),
        ).style("width: 100%; margin-bottom: 10px;")
        ui.button("Save", on_click=self.save_settings).style(
            "width: 100%; margin-top: 10px;"
        )

    def save_settings(self):
        scripts_dir = Path(self.scripts_dir_input.value).expanduser()
        logs_dir = Path(self.logs_dir_input.value).expanduser()
        valid = True
        if not scripts_dir.is_dir():
            ui.notification("Invalid scripts directory.", type="warning")
            self.scripts_dir_input.value = str(self.tmux_manager.SCRIPTS_DIR)
            valid = False
        if not logs_dir.is_dir():
            ui.notification("Invalid logs directory.", type="warning")
            self.logs_dir_input.value = str(self.tmux_manager.LOG_DIR)
            valid = False
        if valid:
            self.tmux_manager.SCRIPTS_DIR = scripts_dir
            self.tmux_manager.LOG_DIR = logs_dir
            ui.notification("Directories updated.", type="positive")
            if self.ui_manager:
                self.ui_manager.refresh_script_list()


class TemplatePanel:
    def __init__(self, tmux_manager, ui_manager=None):
        self.tmux_manager = tmux_manager
        self.ui_manager = ui_manager
        self.selected_key = next(iter(TEMPLATES))  # Default to first template
        self.user_templates = {}
        self.template_options = {
            key: template["title"] for key, template in TEMPLATES.items()
        }
        self.select = None
        self.code_display = None
        self.args_input = None
        self.template_session_name_input = None
        self.keep_alive_switch_template = None

    def on_template_change(self, e):
        self.selected_key = e.value
        template = TEMPLATES[self.selected_key]
        self.code_display.value = template["code"]
        self.code_display.visible = True
        if self.args_input:
            self.args_input.label = template["args_label"]
            self.args_input.placeholder = template["placeholder"]
            self.args_input.visible = bool(template["args_label"])
            self.args_input.value = ""
        if self.template_session_name_input:
            self.template_session_name_input.value = template["default_session_name"]
        if self.keep_alive_switch_template:
            self.keep_alive_switch_template.value = False

    def build(self):
        ui.label("Templates").style(
            "font-size: 1.5em; font-weight: bold; margin-bottom: 20px; text-align: center;"
        )
        options = list(self.template_options.keys())
        valid_keys = options

        if not valid_keys:
            self.selected_key = None
        elif self.selected_key not in valid_keys:
            self.selected_key = valid_keys[0]

        self.select = ui.select(
            options=options,
            label="Template",
            value=self.selected_key,
            on_change=self.on_template_change,
        ).style("width: 100%; margin-bottom: 10px;")

        if self.selected_key is None:
            ui.label("No templates available.").style("color: #888; margin-top: 20px;")
            return

        with ui.row().style("width: 100%; align-items: flex-start;"):
            self.code_display = (
                ui.codemirror(
                    TEMPLATES[self.selected_key]["code"],
                    language="bash",
                    theme="vscodeLight",
                    line_wrapping=True,
                    highlight_whitespace=True,
                    indent="    ",
                    on_change=None,  # Read-only
                )
                .style("width: 100%; margin-top: 10px;")
                .classes("h-48")
            )
            self.code_display.props("readonly")
            ui.select(self.code_display.supported_themes, label="Theme").classes(
                "w-32"
            ).bind_value(self.code_display, "theme")


class NewScriptPanel:
    def __init__(self, tmux_manager, ui_manager=None):
        self.tmux_manager = tmux_manager
        self.ui_manager = ui_manager
        self.custom_code = {"value": "#!/bin/bash\n"}
        self.custom_template_name_input = None

    def build(self):
        ui.label("New Script").style(
            "font-size: 1.5em; font-weight: bold; margin-bottom: 20px; text-align: center;"
        )
        code_editor = (
            ui.codemirror(
                self.custom_code["value"],
                language="bash",
                theme="vscodeLight",
                on_change=lambda e: self.custom_code.update({"value": e.value}),
            )
            .style(
                "width: 100%; font-family: monospace; background: #f5f5f5; color: #222; border-radius: 6px;"
            )
            .classes("h-48")
        )
        ui.select(code_editor.supported_themes, label="Theme").classes(
            "w-32"
        ).bind_value(code_editor, "theme")
        self.custom_template_name_input = ui.input(
            label="Save Template As... (max 15 chars)",
            placeholder="MyScript",
            validation={"Too long!": lambda value: len(value) <= 15},
        ).style("width: 100%; margin-bottom: 8px;")
        ui.button(
            "Save",
            on_click=self.save_custom_template,
        ).style("width: 28%; margin-bottom: 8px;")

    def save_custom_template(self):
        name = self.custom_template_name_input.value.strip()
        if not name or len(name) > 15:
            ui.notification("Please enter a name up to 15 characters.", type="warning")
            return
        safe_name = name.strip().replace(" ", "_")[:15]
        code = self.custom_code["value"]
        if not code.startswith("#!"):
            code = "#!/bin/bash\n" + code
        template = {
            "title": name,
            "script_name": f"{safe_name}.sh",
            "code": code,
            "args_label": "Arguments (optional)",
            "placeholder": "",
            "default_session_name": safe_name,
            "custom": False,
        }
        TEMPLATES[safe_name] = template

        # Save the script to the scripts directory
        script_path = self.tmux_manager.get_script_file(f"{safe_name}.sh")
        try:
            with script_path.open("w") as f:
                f.write(code)
            os.chmod(script_path, 0o755)
            msg = f"Script '{name}' saved to {script_path}."
            logger.info(msg)
            ui.notification(msg, type="positive")
        except Exception as e:
            msg = f"Failed to save script: {e}"
            logger.error(msg)
            ui.notification(msg, type="warning")

        # Update Templates tab UI
        if self.ui_manager and hasattr(self.ui_manager, "template_panel"):
            panel = self.ui_manager.template_panel
            panel.template_options[safe_name] = name
            panel.build()  # Rebuilds the template panel with correct options

        if self.ui_manager:
            self.ui_manager.refresh_script_list()

        ui.notification(
            f"Template '{name}' saved and available in Templates.", type="positive"
        )


class LogPanel:
    def __init__(self):
        self.log_display = None
        self.log_messages = []

    def build(self):
        show_logs = ui.switch("Show Logs", value=True).style("margin-bottom: 10px;")
        log_card = ui.card().style(
            "background-color: #fff; color: #000; padding: 20px; border-radius: 8px; width: 100%;"
        )
        with log_card:
            ui.label("Log Messages").style(
                "font-size: 1.5em; font-weight: bold; margin-bottom: 20px; text-align: center;"
            )
            self.log_display = (
                ui.textarea("")
                .style(
                    "width: 600px; height: 100%; background-color: #fff; color: #000; border: 1px solid #ccc; font-family: monospace;"
                )
                .props("readonly")
            )

        def toggle_log_card_visibility(value):
            if value:
                log_card.style("opacity: 1; pointer-events: auto;")
            else:
                log_card.style("opacity: 0; pointer-events: none;")

        show_logs.on(
            "update:model-value", lambda e: toggle_log_card_visibility(e.args[0])
        )
        log_card.visible = show_logs.value

    def update_log_messages(self, message, number_of_lines=20):
        self.log_messages.append(message)

        if len(self.log_messages) > number_of_lines:
            self.log_messages.pop(0)

    def refresh_log_display(self):
        self.log_display.value = "\n".join(self.log_messages)


class UserInterfaceManager:
    def __init__(self, ui, ui_settings, tmux_manager):
        self.ui_settings = ui_settings
        self.ui = ui
        self.tmux_manager = tmux_manager
        self.stats_panel = SystemStatsPanel(ui_settings)
        self.template_panel = TemplatePanel(tmux_manager, self)
        self.new_script_panel = NewScriptPanel(tmux_manager, self)
        self.log_panel = LogPanel()
        self.script_path_select = None  # Reference to the script select component

    def refresh_script_list(self):
        script_files = [
            f.name for f in self.tmux_manager.SCRIPTS_DIR.glob("*.sh") if f.is_file()
        ]
        if self.script_path_select:
            self.script_path_select.options = (
                script_files if script_files else ["No scripts found"]
            )
            if script_files:
                self.script_path_select.value = script_files[0]
            else:
                self.script_path_select.value = "No scripts found"
                msg = f"No script files found in {self.tmux_manager.SCRIPTS_DIR}. Select a different directory or add scripts."
                logger.warning(msg)
                ui.notification(msg, type="warning")

    def build_ui(self):
        with (
            ui.header(elevated=True)
            .style(
                f"background-color: {self.ui_settings['header']['background_color']}; "
                f"color: {self.ui_settings['header']['color']};"
            )
            .classes(replace="row items-center justify-between")
        ):
            ui.button(on_click=lambda: left_drawer.toggle(), icon="menu").props(
                "flat color=white"
            )
            ui.label("desto").style(
                f"font-size: {self.ui_settings['header']['font_size']}; font-weight: bold;"
            )
            ui.icon("preview", size="2.1rem").style("margin-left: 20px;")
            ui.button(on_click=lambda: right_drawer.toggle(), icon="settings").props(
                "flat color=white"
            ).style("margin-left: auto;")
        with ui.left_drawer().style(
            f"width: {self.ui_settings['sidebar']['width']}; "
            f"padding: {self.ui_settings['sidebar']['padding']}; "
            f"background-color: {self.ui_settings['sidebar']['background_color']}; "
            f"border-radius: {self.ui_settings['sidebar']['border_radius']}; "
            "display: flex; flex-direction: column;"
        ) as left_drawer:
            self.stats_panel.build()

        with ui.right_drawer(top_corner=False, bottom_corner=True, value=False).style(
            f"width: {self.ui_settings['sidebar']['width']}; "
            f"padding: {self.ui_settings['sidebar']['padding']}; "
            f"background-color: {self.ui_settings['sidebar']['background_color']}; "
            f"border-radius: {self.ui_settings['sidebar']['border_radius']}; "
            "display: flex; flex-direction: column;"
        ) as right_drawer:
            self.settings_panel = SettingsPanel(self.tmux_manager, self)
            self.settings_panel.build()

        with ui.column().style("flex-grow: 1; padding: 20px; gap: 20px;"):
            with ui.tabs().classes("w-full") as tabs:
                scripts_tab = ui.tab("Scripts", icon="rocket_launch")
                new_script_tab = ui.tab("New Script", icon="add")
                templates_tab = ui.tab("Templates", icon="menu_book")

            with ui.tab_panels(tabs, value=scripts_tab).classes("w-full"):
                with ui.tab_panel(scripts_tab):
                    with ui.card().style(
                        "background-color: #fff; color: #000; padding: 20px; border-radius: 8px; width: 100%;"
                    ):
                        ui.label("Launch Script").style(
                            "font-size: 1.5em; font-weight: bold; margin-bottom: 20px; text-align: center;"
                        )
                        session_name_input = ui.input(label="Session Name").style(
                            "width: 100%; color: #75a8db;"
                        )
                        script_files = [
                            f.name
                            for f in self.tmux_manager.SCRIPTS_DIR.glob("*.sh")
                            if f.is_file()
                        ]
                        self.script_path_select = ui.select(
                            options=script_files
                            if script_files
                            else ["No scripts found"],
                            label="Script",
                            value=script_files[0]
                            if script_files
                            else "No scripts found",
                        ).style("width: 100%;")
                        arguments_input = ui.input(
                            label="Arguments",
                            value=".",
                        ).style("width: 100%;")

                        # Add these lines after self.script_path_select is created
                        script_preview_content = ""
                        if (
                            script_files
                            and (
                                self.tmux_manager.SCRIPTS_DIR / script_files[0]
                            ).is_file()
                        ):
                            with open(
                                self.tmux_manager.SCRIPTS_DIR / script_files[0], "r"
                            ) as f:
                                script_preview_content = f.read()

                        self.script_preview_editor = (
                            ui.codemirror(
                                script_preview_content,
                                language="bash",
                                theme="vscodeLight",
                                line_wrapping=True,
                                highlight_whitespace=True,
                                indent="    ",
                                on_change=None,  # Read-only
                            )
                            .style("width: 100%; margin-top: 10px;")
                            .classes("h-48")
                        )
                        self.script_preview_editor.props("readonly")

                        ui.select(
                            self.script_preview_editor.supported_themes, label="Theme"
                        ).classes("w-32").bind_value(
                            self.script_preview_editor, "theme"
                        )

                        keep_alive_switch_new = ui.switch("Keep Alive").style(
                            "margin-top: 10px;"
                        )
                        with ui.row().style(
                            "width: 100%; gap: 10px; margin-top: 10px;"
                        ):
                            ui.button(
                                "Launch",
                                on_click=lambda: self.run_session_with_keep_alive(
                                    session_name_input.value,
                                    str(
                                        self.tmux_manager.SCRIPTS_DIR
                                        / self.script_path_select.value
                                    ),
                                    arguments_input.value,
                                    keep_alive_switch_new.value,
                                ),
                            )
                            ui.button(
                                "DELETE",
                                color="red",
                                on_click=lambda: self.confirm_delete_script(),
                            )

                        self.script_path_select.on(
                            "update:model-value", self.update_script_preview
                        )
                with ui.tab_panel(new_script_tab):
                    with ui.card().style(
                        "background-color: #fff; color: #000; padding: 20px; border-radius: 8px; width: 100%;"
                    ):
                        self.new_script_panel.build()
                with ui.tab_panel(templates_tab):
                    with ui.card().style(
                        "background-color: #fff; color: #000; padding: 20px; border-radius: 8px; width: 100%;"
                    ):
                        self.template_panel.build()
            self.log_panel.build()

    def update_log_messages(self, message, number_of_lines=20):
        self.log_panel.update_log_messages(message, number_of_lines)

    def refresh_log_display(self):
        self.log_panel.refresh_log_display()

    def update_ui_system_info(self):
        self.stats_panel.cpu_percent.text = f"{psutil.cpu_percent()}%"
        self.stats_panel.cpu_bar.value = psutil.cpu_percent() / 100
        memory = psutil.virtual_memory()
        self.stats_panel.memory_percent.text = f"{memory.percent}%"
        self.stats_panel.memory_bar.value = memory.percent / 100
        self.stats_panel.memory_available.text = (
            f"{round(memory.available / (1024**3), 2)} GB Available"
        )
        self.stats_panel.memory_used.text = (
            f"{round(memory.used / (1024**3), 2)} GB Used"
        )
        disk = psutil.disk_usage("/")
        self.stats_panel.disk_percent.text = f"{disk.percent}%"
        self.stats_panel.disk_bar.value = disk.percent / 100
        self.stats_panel.disk_free.text = f"{round(disk.free / (1024**3), 2)} GB Free"
        self.stats_panel.disk_used.text = f"{round(disk.used / (1024**3), 2)} GB Used"
        # --- tmux server stats ---
        tmux_cpu = "N/A"
        tmux_mem = "N/A"
        try:
            tmux_procs = [
                p
                for p in psutil.process_iter(
                    ["name", "ppid", "cpu_percent", "memory_info", "cmdline"]
                )
                if p.info["name"] == "tmux" or "tmux" in p.info["name"]
            ]
            if tmux_procs:
                server_proc = next((p for p in tmux_procs if p.info["ppid"] == 1), None)
                if not server_proc:
                    server_proc = min(tmux_procs, key=lambda p: p.info["ppid"])
                tmux_cpu = f"{server_proc.cpu_percent(interval=0.1):.1f}%"
                mem_mb = server_proc.memory_info().rss / (1024 * 1024)
                tmux_mem = f"{mem_mb:.1f} MB"
            else:
                total_cpu = sum(p.cpu_percent(interval=0.1) for p in tmux_procs)
                total_mem = sum(p.memory_info().rss for p in tmux_procs)
                tmux_cpu = f"{total_cpu:.1f}%"
                tmux_mem = f"{total_mem / (1024 * 1024):.1f} MB"
        except Exception:
            tmux_cpu = "N/A"
            tmux_mem = "N/A"
        self.stats_panel.tmux_cpu.text = f"tmux CPU: {tmux_cpu}"
        self.stats_panel.tmux_mem.text = f"tmux MEM: {tmux_mem}"

    async def run_session_with_keep_alive(
        self, session_name, script_path, arguments, keep_alive
    ):
        script_path_obj = Path(script_path)
        if not script_path_obj.is_file():
            msg = f"Script path does not exist: {script_path}"
            logger.warning(msg)
            ui.notification(msg, type="negative")
            return
        try:
            with script_path_obj.open("r") as script_file:
                script_lines = script_file.readlines()
                if (
                    not script_lines
                    or not script_lines[0].startswith("#!")
                    or "bash" not in script_lines[0]
                ):
                    msg = f"Script is not a bash script: {script_path}"
                    logger.warning(msg)
                    ui.notification(msg, type="negative")
                    return
            tail_line = "tail -f /dev/null\n"
            comment_line = "# Keeps the session alive\n"
            if keep_alive:
                if tail_line not in script_lines:
                    with script_path_obj.open("a") as script_file:
                        script_file.write("\n" + comment_line)
                        script_file.write(tail_line)
            else:
                new_lines = []
                skip_next = False
                for line in script_lines:
                    if line == comment_line:
                        skip_next = True
                        continue
                    if skip_next and line == tail_line:
                        skip_next = False
                        continue
                    if line == tail_line:
                        continue
                    new_lines.append(line)
                with script_path_obj.open("w") as script_file:
                    script_file.writelines(new_lines)
            self.tmux_manager.start_tmux_session(
                session_name,
                f"{script_path} {arguments}".strip(),
                logger,
            )
        except PermissionError:
            msg = f"Permission denied: Unable to modify the script at {script_path} to add or remove 'keep alive' functionality."
            logger.warning(msg)
            ui.notification(msg, type="negative")

    def update_script_preview(self, e):
        selected = e.args
        script_files = [
            f.name for f in self.tmux_manager.SCRIPTS_DIR.glob("*.sh") if f.is_file()
        ]
        # If selected is a list/tuple, get the first element
        if isinstance(selected, (list, tuple)):
            selected = selected[0]
        # If selected is a dict (option object), get the value
        if isinstance(selected, dict):
            selected = selected.get("value", "")
        # If selected is an int, treat it as an index
        if isinstance(selected, int):
            if 0 <= selected < len(script_files):
                selected = script_files[selected]
            else:
                selected = ""
        # Now selected should be a string (filename)
        script_path = self.tmux_manager.SCRIPTS_DIR / selected
        if script_path.is_file():
            with open(script_path, "r") as f:
                self.script_preview_editor.value = f.read()
        else:
            self.script_preview_editor.value = "# Script not found."

    def confirm_delete_script(self):
        selected_script = self.script_path_select.value
        if not selected_script or selected_script == "No scripts found":
            msg = "No script selected to delete."
            logger.warning(msg)
            ui.notification(msg, type="warning")
            return

        dialog = None  # Will hold the dialog instance

        def do_delete():
            script_path = self.tmux_manager.SCRIPTS_DIR / selected_script
            try:
                logger.info(f"Attempting to delete script: {script_path}")
                script_path.unlink()
                msg = f"Deleted script: {selected_script}"
                logger.info(msg)
                ui.notification(msg, type="positive")
                self.refresh_script_list()
                self.update_script_preview(
                    type("E", (), {"args": self.script_path_select.value})()
                )
            except Exception as e:
                msg = f"Failed to delete: {e}"
                logger.error(msg)
                ui.notification(msg, type="negative")
            dialog.close()

        with ui.dialog() as dialog, ui.card():
            ui.label(f"Are you sure you want to delete '{selected_script}'?")
            with ui.row():
                ui.button("Cancel", on_click=dialog.close)
                ui.button("Delete", color="red", on_click=do_delete)
        logger.debug(f"Opened delete confirmation dialog for: {selected_script}")
        ui.notification(
            f"Delete confirmation opened for '{selected_script}'", type="info"
        )
        dialog.open()
