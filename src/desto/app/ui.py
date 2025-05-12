from loguru import logger
import psutil
from nicegui import ui
from desto.app.config import config as ui_settings
from pathlib import Path
import asyncio
import os


class UserInterfaceManager:
    def __init__(self, ui, ui_settings, tmux_manager):
        self.ui_settings = ui_settings
        self.ui = ui
        self.tmux_manager = tmux_manager

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
        self.log_display = None
        self.log_messages = []
        self.log_display = None
        self.tmux_cpu = None
        self.tmux_mem = None

    def build_ui(self):
        # --- UI Definition ---
        with (
            ui.header(elevated=True)
            .style(
                f"background-color: {ui_settings['header']['background_color']}; "
                f"color: {ui_settings['header']['color']};"
            )
            .classes(replace="row items-center")
        ):
            ui.button(on_click=lambda: left_drawer.toggle(), icon="menu").props(
                "flat color=white"
            )
            ui.label("desto").style(
                f"font-size: {ui_settings['header']['font_size']}; font-weight: bold;"
            )

        with ui.left_drawer().style(
            f"width: {ui_settings['sidebar']['width']}; "
            f"padding: {ui_settings['sidebar']['padding']}; "
            f"background-color: {ui_settings['sidebar']['background_color']}; "
            f"border-radius: {ui_settings['sidebar']['border_radius']}; "
            "display: flex; flex-direction: column;"
        ) as left_drawer:
            with ui.column():
                ui.label("System Stats").style(
                    f"font-size: {ui_settings['labels']['title_font_size']}; "
                    f"font-weight: {ui_settings['labels']['title_font_weight']}; "
                    "margin-bottom: 10px;"
                )

                ui.label("CPU Usage").style(
                    f"font-weight: {ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;"
                )
                with ui.row().style("align-items: center"):
                    ui.icon("memory", size="1.2rem")
                    self.cpu_percent = ui.label("0%").style(
                        f"font-size: {ui_settings['labels']['subtitle_font_size']}; margin-left: 5px;"
                    )
                self.cpu_bar = ui.linear_progress(
                    value=0, size=ui_settings["progress_bar"]["size"]
                )

                ui.label("Memory Usage").style(
                    f"font-weight: {ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;"
                )
                with ui.row().style("align-items: center"):
                    ui.icon("memory", size="1.2rem")
                    self.memory_percent = ui.label("0%").style(
                        f"font-size: {ui_settings['labels']['subtitle_font_size']}; margin-left: 5px;"
                    )
                self.memory_bar = ui.linear_progress(
                    value=0, size=ui_settings["progress_bar"]["size"]
                )
                self.memory_used = ui.label("0 GB Used").style(
                    f"font-size: {ui_settings['labels']['info_font_size']}; color: {ui_settings['labels']['info_color']};"
                )
                self.memory_available = ui.label("0 GB Available").style(
                    f"font-size: {ui_settings['labels']['info_font_size']}; color: {ui_settings['labels']['info_color']};"
                )

                ui.label("Disk Usage (Root)").style(
                    f"font-weight: {ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;"
                )
                with ui.row().style("align-items: center"):
                    ui.icon("hard_drive", size="1.2rem")
                    self.disk_percent = ui.label("0%").style(
                        f"font-size: {ui_settings['labels']['subtitle_font_size']}; margin-left: 5px;"
                    )
                self.disk_bar = ui.linear_progress(
                    value=0, size=ui_settings["progress_bar"]["size"]
                )
                self.disk_used = ui.label("0 GB Used").style(
                    f"font-size: {ui_settings['labels']['info_font_size']}; color: {ui_settings['labels']['info_color']};"
                )
                self.disk_free = ui.label("0 GB Free").style(
                    f"font-size: {ui_settings['labels']['info_font_size']}; color: {ui_settings['labels']['info_color']};"
                )

                # --- Add tmux stats at the bottom ---
                self.tmux_cpu = ui.label("tmux CPU: N/A").style(
                    f"font-size: {ui_settings['labels']['info_font_size']}; color: #888; margin-top: 20px;"
                )
                self.tmux_mem = ui.label("tmux MEM: N/A").style(
                    f"font-size: {ui_settings['labels']['info_font_size']}; color: #888;"
                )

        # Main Content Area with Tabs
        with ui.column().style("flex-grow: 1; padding: 20px; gap: 20px;"):
            # Tabs definition
            with ui.tabs().classes("w-full") as tabs:
                new_tab = ui.tab("New")
                recipes_tab = ui.tab("Recipes")
            with ui.tab_panels(tabs, value=new_tab).classes("w-full"):
                with ui.tab_panel(new_tab):
                    with ui.card().style(
                        "background-color: #fff; color: #000; padding: 20px; border-radius: 8px; width: 100%;"
                    ):
                        ui.label("Start Session").style(
                            "font-size: 1.5em; font-weight: bold; margin-bottom: 20px; text-align: center;"
                        )
                        session_name_input = ui.input(label="Session Name").style(
                            "width: 100%;"
                        )
                        script_path_input = ui.input(
                            label="Script path",
                            value="/home/kalfasy/repos/desto/scripts/find_files.sh",
                        ).style("width: 100%;")
                        arguments_input = ui.input(
                            label="Arguments",
                            value=".",
                        ).style("width: 100%;")
                        keep_alive_switch_new = ui.switch("Keep Alive").style(
                            "margin-top: 10px;"
                        )
                        ui.button(
                            "Run in Session",
                            on_click=lambda: self.run_session_with_keep_alive(
                                session_name_input.value,
                                script_path_input.value,
                                arguments_input.value,
                                keep_alive_switch_new.value,
                            ),
                        )
                with ui.tab_panel(recipes_tab):
                    with ui.card().style(
                        "background-color: #fff; color: #000; padding: 20px; border-radius: 8px; width: 100%;"
                    ):
                        ui.label("Recipes").style(
                            "font-size: 1.5em; font-weight: bold; margin-bottom: 20px; text-align: center;"
                        )

                        recipes = [
                            {
                                "title": "Custom Recipe",
                                "script_name": "custom.sh",
                                "code": "#!/bin/bash\n",
                                "args_label": "Arguments (optional)",
                                "placeholder": "",
                                "default_session_name": "custom_recipe",
                                "custom": True,
                            },
                            {
                                "title": "Recursive Pattern Search",
                                "script_name": "search_pattern.sh",
                                "code": """#!/bin/bash
# Usage: ./search_pattern.sh <directory> <pattern>
dir="$1"
pattern="$2"
grep -rnw "$dir" -e "$pattern"
""",
                                "args_label": "Directory and Pattern (e.g. /home/user mypattern)",
                                "placeholder": "/path/to/dir pattern",
                                "default_session_name": "rec_patt_search",
                                "custom": False,
                            },
                        ]

                        selected_index = 0

                        # --- Custom Recipe textarea state ---
                        custom_code = {"value": recipes[0]["code"]}

                        def on_recipe_change(e):
                            nonlocal selected_index
                            selected_index = e.value
                            if recipes[selected_index].get("custom"):
                                # Show editable textarea for custom recipe
                                custom_code["value"] = (
                                    custom_code["value"] or "#!/bin/bash\n"
                                )
                                code_display.visible = False
                                custom_code_display.visible = True
                                custom_code_display.value = custom_code["value"]
                                args_input.label = recipes[selected_index]["args_label"]
                                args_input.placeholder = recipes[selected_index][
                                    "placeholder"
                                ]
                                args_input.visible = bool(
                                    recipes[selected_index]["args_label"]
                                )
                            else:
                                code_display.value = recipes[selected_index]["code"]
                                code_display.visible = True
                                custom_code_display.visible = False
                                args_input.label = recipes[selected_index]["args_label"]
                                args_input.placeholder = recipes[selected_index][
                                    "placeholder"
                                ]
                                args_input.visible = bool(
                                    recipes[selected_index]["args_label"]
                                )
                            args_input.value = ""
                            recipe_session_name_input.value = recipes[selected_index][
                                "default_session_name"
                            ]
                            keep_alive_switch_recipe.value = False

                        # Radio group for recipe selection
                        recipe_options = {
                            i: recipe["title"] for i, recipe in enumerate(recipes)
                        }
                        radio = ui.radio(
                            recipe_options,
                            value=selected_index,
                            on_change=on_recipe_change,
                        )
                        radio.props("inline")

                        # Readonly code display for predefined recipe
                        code_display = (
                            ui.textarea(recipes[selected_index]["code"])
                            .style(
                                "width: 100%; font-family: monospace; background: #f5f5f5; color: #222; border-radius: 6px;"
                            )
                            .props("readonly autogrow")
                        )

                        # Editable textarea for custom recipe, hidden by default
                        custom_code_display = (
                            ui.textarea(
                                value=custom_code["value"],
                                label="Custom Bash Script",
                                placeholder="Write your bash script here...",
                                on_change=lambda e: custom_code.update(
                                    {"value": e.value}
                                ),
                            )
                            .style(
                                "width: 100%; font-family: monospace; background: #f5f5f5; color: #222; border-radius: 6px;"
                            )
                            .props("autogrow")
                            .bind_visibility_from(radio, "value", lambda v: v == 1)
                        )
                        custom_code_display.visible = False  # Hide initially

                        args_input = (
                            ui.input(
                                label=recipes[selected_index]["args_label"],
                                placeholder=recipes[selected_index]["placeholder"],
                            ).style("width: 100%;")
                            if recipes[selected_index]["args_label"]
                            else ui.input(visible=False)
                        )

                        recipe_session_name_input = ui.input(
                            label="Session Name",
                            value=recipes[selected_index]["default_session_name"],
                        ).style("width: 100%; margin-top: 10px;")

                        keep_alive_switch_recipe = ui.switch("Keep Alive").style(
                            "margin-top: 10px;"
                        )

                        def execute_recipe():
                            idx = radio.value
                            recipe = recipes[idx]
                            if recipe.get("custom"):
                                script_code = (
                                    custom_code_display.value or "#!/bin/bash\n"
                                )
                            else:
                                script_code = recipe["code"]
                            args = args_input.value.strip()
                            session_name = (
                                recipe_session_name_input.value.strip()
                                or recipe["default_session_name"]
                            )
                            script_path = self.tmux_manager.get_script_file(
                                recipe["script_name"]
                            )
                            with script_path.open("w") as f:
                                f.write(script_code)
                            os.chmod(script_path, 0o755)
                            # Add keep alive if needed
                            if keep_alive_switch_recipe.value:
                                with script_path.open("a") as f:
                                    f.write("\n# Keeps the session alive\n")
                                    f.write("tail -f /dev/null\n")
                            self.tmux_manager.start_tmux_session(
                                session_name,
                                f"{script_path} {args}",
                                logger,
                            )
                            ui.notification(
                                f"Recipe '{recipe['title']}' executed.", type="positive"
                            )

                        ui.button(
                            "Execute Recipe",
                            on_click=execute_recipe,
                        ).props("color=primary")

            # Log Messages Card with Show/Hide Switch (shared for both tabs)
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

            # Bind the visibility of the log card to the switch
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
        """
        Updates the provided log_messages list with the latest log message.
        Keeps only the last 'number_of_lines' messages.
        """
        self.log_messages.append(message)

        if len(self.log_messages) > number_of_lines:
            self.log_messages.pop(0)

    def refresh_log_display(self, log_display, log_messages):
        """
        Refreshes the log display with the latest log messages.
        """
        log_display.value = "\n".join(log_messages)

    # --- Sidebar Update Function ---
    def update_ui_system_info(self):
        """
        Updates the system information displayed in the sidebar.
        """
        self.cpu_percent.text = f"{psutil.cpu_percent()}%"
        self.cpu_bar.value = psutil.cpu_percent() / 100

        self.memory = psutil.virtual_memory()
        self.memory_percent.text = f"{self.memory.percent}%"
        self.memory_bar.value = self.memory.percent / 100
        self.memory_available.text = (
            f"{round(self.memory.available / (1024**3), 2)} GB Available"
        )
        self.memory_used.text = f"{round(self.memory.used / (1024**3), 2)} GB Used"

        self.disk = psutil.disk_usage("/")
        self.disk_percent.text = f"{self.disk.percent}%"
        self.disk_bar.value = self.disk.percent / 100
        self.disk_free.text = f"{round(self.disk.free / (1024**3), 2)} GB Free"
        self.disk_used.text = f"{round(self.disk.used / (1024**3), 2)} GB Used"

        # --- tmux server stats ---
        tmux_cpu = "N/A"
        tmux_mem = "N/A"
        try:
            # Find the tmux server process (ppid == 1 or lowest ppid)
            tmux_procs = [
                p
                for p in psutil.process_iter(
                    ["name", "ppid", "cpu_percent", "memory_info", "cmdline"]
                )
                if p.info["name"] == "tmux" or "tmux" in p.info["name"]
            ]
            if tmux_procs:
                # Try to find the one with ppid == 1 (the server)
                server_proc = next((p for p in tmux_procs if p.info["ppid"] == 1), None)
                if not server_proc:
                    # Fallback: tmux process with the lowest ppid
                    server_proc = min(tmux_procs, key=lambda p: p.info["ppid"])
                tmux_cpu = f"{server_proc.cpu_percent(interval=0.1):.1f}%"
                mem_mb = server_proc.memory_info().rss / (1024 * 1024)
                tmux_mem = f"{mem_mb:.1f} MB"
            else:
                # Calculate total CPU and memory usage of all tmux processes
                total_cpu = sum(p.cpu_percent(interval=0.1) for p in tmux_procs)
                total_mem = sum(p.memory_info().rss for p in tmux_procs)
                tmux_cpu = f"{total_cpu:.1f}%"
                tmux_mem = f"{total_mem / (1024 * 1024):.1f} MB"
        except Exception as e:
            tmux_cpu = "N/A"
            tmux_mem = "N/A"

        self.tmux_cpu.text = f"tmux CPU: {tmux_cpu}"
        self.tmux_mem.text = f"tmux MEM: {tmux_mem}"

    async def run_session_with_keep_alive(
        self, session_name, script_path, arguments, keep_alive
    ):
        """
        Runs a tmux session with an optional 'keep alive' functionality.
        If keep_alive is True, appends 'tail -f /dev/null' to the script if not present.
        If keep_alive is False, removes 'tail -f /dev/null' and its comment if present.
        Checks that the script is a bash script before running.
        Shows notifications for errors.
        """
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
                # Remove both the comment and tail line if present
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
