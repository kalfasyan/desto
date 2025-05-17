# desto

[![PyPI version](https://badge.fury.io/py/desto.svg)](https://badge.fury.io/py/desto) [![Tests](https://github.com/kalfasyan/desto/actions/workflows/ci.yml/badge.svg)](https://github.com/kalfasyan/desto/actions/workflows/ci.yml) ![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-blueviolet) ![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat) 

**desto** is a modern, intuitive dashboard for managing and monitoring your `tmux` sessions. It provides a user-friendly web interface to start, view, and kill `tmux` sessions, monitor system stats, run custom or predefined scripts, and view live logs—all from your browser.

---

## Features

- **Session Management**: Start, view, and kill `tmux` sessions with a single click.
- **System Monitoring**: Real-time CPU, memory, and disk usage stats in the sidebar.
- **Templates & Custom Scripts**: View predefined templates (like recursive pattern search) or write your own bash scripts directly in the browser.
- **Keep Alive Option**: Optionally keep sessions running after your script finishes.
- **Live Log Viewer**: View live logs for each session in a scrollable, syntax-highlighted interface.
- **Responsive UI**: Clean, modern interface built with [NiceGUI](https://nicegui.io/).
- **Persistent Logs & Scripts**: All logs and scripts are stored in dedicated folders for easy access and reproducibility.

---

## TODO

- [ ] Explore possibility to pause processes running inside a session
- [ ] Make it more intuitive to export/import custom templates/scripts
- [ ] Add dark mode/theme toggle for the dashboard UI
- [ ] Implement notifications for session completion or errors

---

## Functionality

<div align="left">

**Dashboard Overview**

<img src="images/dashboard.png" alt="Dashboard Screenshot" title="Desto Dashboard" width="700" style="border:2px solid #ccc; border-radius:6px; margin-bottom:24px;"/>

**Write new scripts and save them**

<img src="images/new_script.png" alt="Custom Template" title="Custom Template" width="300" style="border:2px solid #ccc; border-radius:6px;"/>
  

**Check some pre-defined templates**  
  
*(soon users will be able to save their own)*  
<img src="images/example_template.png" alt="Custom Template" title="Custom Template" width="300" style="border:2px solid #ccc; border-radius:6px;"/>
   

**Change settings**  
  
<img src="images/settings.png" alt="Custom Template" title="Custom Template" width="300" style="border:2px solid #ccc; border-radius:6px;"/>
  

**View your script's logs**  
  
<img src="images/view_logs.png" alt="Custom Template" title="Custom Template" width="300" style="border:2px solid #ccc; border-radius:6px;"/>

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


## Requirements

- Python 3.11+
- [tmux](https://github.com/tmux/tmux)
- [NiceGUI](https://nicegui.io/)

---

## License

MIT License

---

**desto** makes handling tmux sessions approachable for everyone—no terminal gymnastics required!
