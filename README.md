<p align="center">
  <img src="images/logo.png" alt="desto Logo" title="Write New" width="300" style="border:2px solid #ccc; border-radius:6px;"/>  
</p>  


**desto** lets you run and manage your bash scripts in the background (inside `tmux` sessions) through a simple web dashboard. Launch scripts, monitor their and your system's status, view live logs, and control sessions—all from your browser.  

[![PyPI version](https://badge.fury.io/py/desto.svg)](https://badge.fury.io/py/desto) ![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-blueviolet) ![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat) [![Tests](https://github.com/kalfasyan/desto/actions/workflows/ci.yml/badge.svg)](https://github.com/kalfasyan/desto/actions/workflows/ci.yml)

---

The key features are:  

- **One-click session control:** Start, monitor, and stop `tmux` sessions from your browser.
- **Live system stats:** See real-time CPU, memory, and disk usage at a glance.
- **Script management:** Use your existing scripts, write new ones, edit, save, or delete them directly in the dashboard.
- **Script chaining:** Queue multiple scripts to run sequentially in a single session.
- **Scheduling:** Schedule scripts or script chains to launch at a specific date and time.
- **Live log viewer:** Watch script output in real time and view logs for each session.
- **Persistent storage:** Scripts and logs are saved in dedicated folders for easy access.

  
## ⚡ Quick Start


  
<div align="left">

<strong>👀 Dashboard Overview</strong>

<img src="images/dashboard.png" alt="Dashboard Screenshot" title="Desto Dashboard" width="700" style="border:2px solid #ccc; border-radius:6px; margin-bottom:24px;"/>

  
---
**🚀 Launch your scripts as `tmux` sessions**  
  
When you start `desto`, it creates `desto_scripts/` and `desto_logs/` folders in your current directory. Want to use your own locations? Just change these in the settings, or set the `DESTO_SCRIPTS_DIR` and `DESTO_LOGS_DIR` environment variables.

Your scripts show up automatically—no setup needed. Ready to launch? Just:

1. Name your `tmux` session
2. Select one of your scripts
3. (OPTIONAL) edit and save your changes
4. Click "Launch"! 🎬

<img src="images/launch_script.png" alt="Custom Template" title="Launch Script" width="300" style="border:2px solid #ccc; border-radius:6px;"/>
  
🟢 **Keep Alive**: Want your session to stay open after your script finishes? Just toggle the switch. This adds `tail -f /dev/null` at the end, so you can keep the session active and continue viewing logs, even after your script completes.

---
<details>
<summary><strong>✍️ Write new scripts and save them</strong></summary>

If you want to compose a new script, you can do it right here, or simply just paste the output of your favorite LLM :)

<img src="images/write_new_script.png" alt="Custom Template" title="Write New" width="300" style="border:2px solid #ccc; border-radius:6px;"/>

</details>
  
---
<details>
<summary><strong>⚙️ Change settings</strong></summary>

More settings to be added! 

<img src="images/settings.png" alt="Custom Template" title="Change Settings" width="300" style="border:2px solid #ccc; border-radius:6px;"/>
</details>
  
---
<details>
<summary><strong>📜 View your script's logs</strong></summary>

<img src="images/view_logs.png" alt="Custom Template" title="View Logs" width="300" style="border:2px solid #ccc; border-radius:6px;"/>

</details>

</div>


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

    - With [uv](https://github.com/astral-sh/uv), simply run:
      ```bash
      uv add desto
      ```
      This will install desto in your project ✅
      Or if you don't have a project yet, you can set up everything with [`uv`](https://docs.astral.sh/uv/getting-started/installation/):

      1. [Install `uv`](https://docs.astral.sh/uv/getting-started/installation/) by following the instructions on the official site.
      2. Create and set up your project:

          ```bash
          mkdir myproject && cd myproject
          uv init
          uv venv
          source .venv/bin/activate
          uv add desto
          ```
          Done!
    - With pip:
      ```bash
      pip install desto
      ```
    </details>

3. **Run the Application**  
   ```bash
   desto
   ```

4. **Open in your browser**  
   After starting, visit [http://localhost:8088](http://localhost:8088) (or the address shown in your terminal).


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
