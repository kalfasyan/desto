<p align="center">
  <img src="images/logo.png" alt="desto Logo" title="desto Logo" width="300" style="border:2px solid #ccc; border-radius:6px;"/>  
</p>  


**desto** lets you run and manage your bash and Python scripts in the background (inside `tmux` sessions) through a simple web dashboard. Launch scripts, monitor their and your system's status, view live logs, and control sessions—all from your browser.  

[![PyPI version](https://badge.fury.io/py/desto.svg)](https://badge.fury.io/py/desto) ![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-blueviolet) ![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat) [![Tests](https://github.com/kalfasyan/desto/actions/workflows/ci.yml/badge.svg)](https://github.com/kalfasyan/desto/actions/workflows/ci.yml)

---

The key features are:  

- **One-click session control:** Start, monitor, and stop `tmux` sessions from your browser.
- **🐚 Bash & 🐍 Python support:** Run both bash (`.sh`) and Python (`.py`) scripts seamlessly.
- **Live system stats:** See real-time CPU, memory, and disk usage at a glance.
- **Script management:** Use your existing scripts, write new ones, edit, save, or delete them directly in the dashboard.
- **Script chaining:** Queue multiple scripts to run sequentially in a single session.
- **Scheduling:** Schedule scripts or script chains to launch at a specific date and time.
- **Live log viewer:** Watch script output in real time and view logs for each session.
- **Persistent storage:** Scripts and logs are saved in dedicated folders for easy access.
- **🖥️ Command-line interface:** Manage sessions, view logs, and control scripts from the terminal with our modern CLI. [Learn more →](src/desto/cli/README.md)
  
  
  
<strong>🎬 Demo</strong>

<img src="images/desto_demo.gif" alt="Desto Demo" title="Desto in Action" width="700" style="border:2px solid #ccc; border-radius:6px; margin-bottom:24px;"/>

## ✨ `desto` Overview

<div align="left">

<details>
<summary><strong>👀 Dashboard Overview</strong></summary>

<img src="images/dashboard.png" alt="Dashboard Screenshot" title="Desto Dashboard" width="700" style="border:2px solid #ccc; border-radius:6px; margin-bottom:24px;"/>

</details>  
      
<details>
<summary><strong>🚀 Launch your scripts as `tmux` sessions</strong></summary>

When you start `desto`, it creates `desto_scripts/` and `desto_logs/` folders in your current directory. Want to use your own locations? Just change these in the settings, or set the `DESTO_SCRIPTS_DIR` and `DESTO_LOGS_DIR` environment variables.

Your scripts show up automatically—no setup needed. Both `.sh` (bash) and `.py` (Python) scripts are supported with automatic detection and appropriate execution. Ready to launch? Just:

1. Name your `tmux` session
2. Select one of your scripts
3. (OPTIONAL) edit and save your changes
4. Click "Launch"! 🎬

<img src="images/launch_script.png" alt="Custom Template" title="Launch Script" width="300" style="border:2px solid #ccc; border-radius:6px;"/>
</details>

<details>
<summary><strong>🟢 Keep Alive</strong></summary>

🟢 **Keep Alive**: Want your session to stay open after your script finishes? Just toggle the switch. This adds `tail -f /dev/null` at the end, so you can keep the session active and continue viewing logs, even after your script completes.
</details>

<details>
<summary><strong>✍️ Write new scripts and save them</strong></summary>

If you want to compose a new script, you can do it right here, or simply just paste the output of your favorite LLM :) Choose between bash and Python templates with syntax highlighting and smart defaults.

<img src="images/write_new_script.png" alt="Custom Template" title="Write New" width="300" style="border:2px solid #ccc; border-radius:6px;"/>

</details>
  
<details>
<summary><strong>⚙️ Change settings</strong></summary>

More settings to be added! 

<img src="images/settings.png" alt="Custom Template" title="Change Settings" width="300" style="border:2px solid #ccc; border-radius:6px;"/>
</details>
  
<details>
<summary><strong>📜 View your script's logs</strong></summary>

<img src="images/view_logs.png" alt="Custom Template" title="View Logs" width="300" style="border:2px solid #ccc; border-radius:6px;"/>

</details>

</div>  

## ⚡ Quick Start with Docker 🐳  

The fastest way to ship `desto` is by using Docker Compose 🚢  

You only need Docker and Docker Compose installed on your machine. If you don't have them yet, you can find installation instructions on the [Docker website](https://docs.docker.com/get-docker/) and [Docker Compose documentation](https://docs.docker.com/compose/install/) (or follow your favorite LLM's instructions 😉).  

Start `desto` in just a few steps: 

1. **Clone the repository and go to it's main directory**
    ```bash
    git clone https://github.com/kalfasyan/desto.git && cd desto
    ```

2. **Start the application with Docker Compose**
    ```bash
    docker compose up -d
    ```

✅ **Done!** 🎉  

You’re all set—your desto dashboard is now running at:  
🌐 [http://localhost:8809](http://localhost:8809)


<details>
<summary><strong>🚀 Essential Docker & Docker Compose Commands</strong></summary>

```bash
# Start the app in background (Docker Compose)
docker compose up -d
```

```bash
# View logs (Docker Compose)
docker compose logs -f
```

```bash
# Stop and remove services (Docker Compose)
docker compose down
```

```bash
# Rebuild and start (Docker Compose)
docker compose up -d --build
```

```bash
# Run the container directly (plain Docker)
docker run -d -p 8809:8809 \
  -v $PWD/desto_scripts:/app/desto_scripts \
  -v $PWD/desto_logs:/app/desto_logs \
  --name desto-dashboard \
  desto:latest
```

```bash
# View logs (plain Docker)
docker logs -f desto-dashboard
```

```bash
# Stop and remove the container (plain Docker)
docker stop desto-dashboard && docker rm desto-dashboard
```
</details>

## 🖥️ CLI & 📊 Dashboard Installation with `uv` or `pip`  

If you are not familiar with `uv`, you may visit [uv's official website](https://docs.astral.sh/uv/getting-started/installation/) for more information.

`uv` is a super-fast Python package manager and virtual environment tool, written in Rust. It helps you manage dependencies, create isolated environments, and install packages much faster than traditional tools like pip.  

### Requirements

- Python 3.11+
- [tmux](https://github.com/tmux/tmux)
- [at](https://en.wikipedia.org/wiki/At_(command)) (for scheduling features)
  
Check [`pyproject.toml`](pyproject.toml)

### Installation Steps

1. **Install `tmux` and `at`**  
   <details>
   <summary>Instructions for different package managers</summary>

   - **Debian/Ubuntu**  
     ```bash
     sudo apt install tmux at
     ```
   - **Almalinux/Fedora**  
     ```bash
     sudo dnf install tmux at
     ```
   - **Arch Linux**  
     ```bash
     sudo pacman -S tmux at
     ```
   
   **Note:** The `at` package is required for scheduling features. If you don't plan to use script scheduling, you can skip installing `at`.
   </details>

2. **Install `desto`**  
   <details>
   <summary>Installation Steps</summary>

    - (Recommended) With [uv](https://github.com/astral-sh/uv), simply run:
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
   After starting, visit [http://localhost:8809](http://localhost:8809) (or the address shown in your terminal).

### Global `desto` Installation as a `uv` Tool (includes CLI)

```bash
# Install desto CLI globally
uv tool install desto

# Or install from source
cd /path/to/desto
uv tool install . --force
```

This installs two executables:
- `desto` - Web dashboard  
- `desto-cli` - Command-line interface (work in progress)

<details>
<summary><strong>Quick CLI Usage</strong></summary>


```bash
# Check system status
desto-cli doctor
```

```bash
# List all sessions
desto-cli sessions list
```

```bash
# Start a new session
desto-cli sessions start "my-task" "python my_script.py"
```

```bash
# View session logs
desto-cli sessions logs "my-task"
```

```bash
# Kill a session
desto-cli sessions kill "my-task"
```

```bash
# List all scripts
desto-cli scripts list
```

```bash
# Create new script
desto-cli scripts create "my_script" --type python
```

```bash
# Edit script in $EDITOR
desto-cli scripts edit "my_script"
```

```bash
# Run script in tmux session
desto-cli scripts run "my_script"
```

```bash
# Run script directly
desto-cli scripts run "my_script" --direct
```

</details>

**📖 [Full CLI Documentation →](src/desto/cli/README.md)**

The CLI provides the same functionality as the web interface but optimized for terminal use, including rich formatting, real-time log viewing, and comprehensive session management.


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

**desto** makes handling tmux sessions and running scripts approachable for everyone—no terminal gymnastics required!
