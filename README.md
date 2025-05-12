# desto

**desto** is a modern, intuitive dashboard for managing and monitoring your `tmux` sessions. It provides a user-friendly web interface to start, view, and kill `tmux` sessions, monitor system stats, run custom or predefined scripts, and view live logs—all from your browser.

---

## Features

- **Session Management**: Start, view, and kill `tmux` sessions with a single click.
- **System Monitoring**: Real-time CPU, memory, and disk usage stats in the sidebar.
- **Recipes & Custom Scripts**: Run predefined "recipes" (like recursive pattern search) or write your own bash scripts directly in the browser.
- **Keep Alive Option**: Optionally keep sessions running after your script finishes.
- **Live Log Viewer**: View live logs for each session in a scrollable, syntax-highlighted interface.
- **Responsive UI**: Clean, modern interface built with [NiceGUI](https://nicegui.io/).
- **Persistent Logs & Scripts**: All logs and scripts are stored in dedicated folders for easy access and reproducibility.

---
## Dashboard


<div align="left">

**Dashboard Overview**

<img src="images/dashboard.png" alt="Dashboard Screenshot" title="Desto Dashboard" width="700" style="border:2px solid #ccc; border-radius:6px; margin-bottom:24px;"/>


**Execute Custom or Pre-defined Recipes**

<img src="images/custom_recipe.png" alt="Custom Recipe" title="Custom Recipe" width="300" style="border:2px solid #ccc; border-radius:6px;"/>

</div>

---

## Quick Start

1. **Install `tmux`**  
   <details>
   <summary>Instructions for different package managers</summary>

   - **Debian/Ubuntu**  
     ```bash
     sudo apt install tmux
     ```
   - **Almalinux/Fedora**  
     ```bash
     sudo dnf install tmux
     ```
   - **Arch Linux**  
     ```bash
     sudo pacman -S tmux
     ```
   </details>

2. **Install `desto`**  
   <details>
   <summary>Installation Steps</summary>

   - With [uv](https://github.com/astral-sh/uv):
     ```bash
     uv add desto
     ```
   - With pip:
     ```bash
     pip install desto
     # or
     uv pip install desto
     ```
   </details>

3. **Run the Application**  
   ```bash
   desto
   ```

4. **Open in your browser**  
   After starting, visit [http://localhost:8088](http://localhost:8088) (or the address shown in your terminal).

---

## Usage Examples

- **Start a Custom Session**  
  - Enter a session name, a path to a script and any arguments the script requires.
  - Click **Run in Session** to launch it in tmux.
  - The session appears in the dashboard; view logs or kill it anytime.

- **Use a Recipe or Custom Script**  
  - Switch to the **Recipes** tab.
  - Select a predefined recipe or "Custom Recipe" to write your own bash script.
  - Fill in any required arguments, set a session name, and optionally enable "Keep Alive".
  - Click **Execute Recipe** to run it in a new tmux session.

- **Monitor System Stats**  
  - Sidebar displays live CPU, memory, disk, and tmux server resource usage.

- **View Logs**  
  - Click **View Log** next to any session to see its latest output.

---

## File Structure

- **desto_logs/**: All session logs are stored here.
- **desto_scripts/**: Scripts run via recipes or custom scripts are saved here.

---

## Requirements

- Python 3.11+
- [tmux](https://github.com/tmux/tmux)
- [NiceGUI](https://nicegui.io/)

---

## License

MIT License

---

**desto** makes handling tmux sessions approachable for everyone—no terminal gymnastics required!
