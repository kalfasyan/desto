# desto

[![PyPI version](https://badge.fury.io/py/desto.svg)](https://badge.fury.io/py/desto) ![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-blueviolet) ![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat) [![Tests](https://github.com/kalfasyan/desto/actions/workflows/ci.yml/badge.svg)](https://github.com/kalfasyan/desto/actions/workflows/ci.yml)

**desto** lets you run and manage your bash scripts in `tmux` sessions through a simple web dashboard. Launch scripts, monitor their and your system's status, view live logs, and control sessions—all from your browser.

---

## Features

🚀 **Session Management**: Start, view, and kill `tmux` sessions with a single click.

📊 **System Monitoring**: Real-time CPU, memory, and disk usage stats in the sidebar.

📝 **Templates & Custom Scripts**: View predefined templates (like recursive pattern search) or write your own bash scripts directly in the browser.

🔄 **Keep Alive Option**: Optionally keep sessions running after your script finishes.

📜 **Live Log Viewer**: View live logs for each session in a scrollable, syntax-highlighted interface.

💎 **Responsive UI**: Clean, modern interface built with [NiceGUI](https://nicegui.io/).

💾 **Persistent Logs & Scripts**: All logs and scripts are stored in dedicated folders for easy access and reproducibility.


## Requirements

- Python 3.11+
- [tmux](https://github.com/tmux/tmux)  
  
Check [`pyproject.toml`](pyproject.toml)


## Installation

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


## Functionality

<div align="left">

**Dashboard Overview**

<img src="images/dashboard.png" alt="Dashboard Screenshot" title="Desto Dashboard" width="700" style="border:2px solid #ccc; border-radius:6px; margin-bottom:24px;"/>
  
---
**Launch your scripts as `tmux` sessions**  
    
1. Set a `tmux` session name
2. Select one of your scripts
3. (OPTIONAL) edit and save your changes
4. Click "Launch"!

<img src="images/launch_script.png" alt="Custom Template" title="Launch Script" width="300" style="border:2px solid #ccc; border-radius:6px;"/>

---
**Write new scripts and save them**
  
If you want to compose a new script, you can do it right here, or simply just paste the output of your favorite LLM :)
  
<img src="images/write_new_script.png" alt="Custom Template" title="Write New" width="300" style="border:2px solid #ccc; border-radius:6px;"/>
  
---
**Change settings**  
  
More settings to be added! 
  
<img src="images/settings.png" alt="Custom Template" title="Change Settings" width="300" style="border:2px solid #ccc; border-radius:6px;"/>
  
---
**View your script's logs**  
  
<img src="images/view_logs.png" alt="Custom Template" title="View Logs" width="300" style="border:2px solid #ccc; border-radius:6px;"/>

</div>

---

## License

Shield: [![CC BY 4.0][cc-by-shield]][cc-by]

This work is licensed under a
[Creative Commons Attribution 4.0 International License][cc-by].

[![CC BY 4.0][cc-by-image]][cc-by]

[cc-by]: http://creativecommons.org/licenses/by/4.0/
[cc-by-image]: https://i.creativecommons.org/l/by/4.0/88x31.png
[cc-by-shield]: https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg

---

## TODO

- [ ] Explore possibility to pause processes running inside a session
- [ ] Add dark mode/theme toggle for the dashboard UI

---

**desto** makes handling tmux sessions approachable for everyone—no terminal gymnastics required!
