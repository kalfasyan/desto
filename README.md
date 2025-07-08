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
  
# ⚡ Quick Start

### 🐳 Quick Start with Docker  

The easiest way to get started with desto is using Docker Compose:

```bash
# Clone the repository
git clone https://github.com/kalfasyan/desto.git
cd desto

# Set up example scripts
make docker-setup-examples

# Start desto with Docker Compose
docker-compose up -d
```

**🌐 Access the dashboard at: http://localhost:8088**
  
**Other Docker options:**
```bash
# Using Docker directly
docker build -t desto:latest .
docker run -d -p 8088:8088 \
  -v $(PWD)/desto_scripts:/app/scripts \
  -v $(PWD)/desto_logs:/app/logs \
  --name desto-dashboard \
  desto:latest
```

---

# ✨ `desto` Overview

<div align="left">

<details>
<summary><strong>👀 Dashboard Overview</strong></summary>

<img src="images/dashboard.png" alt="Dashboard Screenshot" title="Desto Dashboard" width="700" style="border:2px solid #ccc; border-radius:6px; margin-bottom:24px;"/>

</details>  
      
**🚀 Launch your scripts as `tmux` sessions**    
When you start `desto`, it creates `desto_scripts/` and `desto_logs/` folders in your current directory. Want to use your own locations? Just change these in the settings, or set the `DESTO_SCRIPTS_DIR` and `DESTO_LOGS_DIR` environment variables.

Your scripts show up automatically—no setup needed. Both `.sh` (bash) and `.py` (Python) scripts are supported with automatic detection and appropriate execution. Ready to launch? Just:

1. Name your `tmux` session
2. Select one of your scripts
3. (OPTIONAL) edit and save your changes
4. Click "Launch"! 🎬

<img src="images/launch_script.png" alt="Custom Template" title="Launch Script" width="300" style="border:2px solid #ccc; border-radius:6px;"/>
  
🟢 **Keep Alive**: Want your session to stay open after your script finishes? Just toggle the switch. This adds `tail -f /dev/null` at the end, so you can keep the session active and continue viewing logs, even after your script completes.

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

---   

# 🛠️ Installation  


## 🐳 Docker Installation (only dashboard)

Docker lets you run desto without installing anything on your computer. It provides a consistent environment across all platforms, making it the easiest way to get started. With docker-compose, you can set up everything in one command, including example scripts and persistent storage for your scripts and logs. You can make changes to the YAML configuration (`docker-compose.yml`) to customize the setup, such as changing ports or directories.  

### Using `docker-compose`

Here are the steps to quickly set up and run **desto** using Docker (as mentioned above):

```bash
git clone https://github.com/kalfasyan/desto.git
cd desto
make docker-setup-examples
docker-compose up -d
```

Then open [http://localhost:8088](http://localhost:8088) in your browser.


#### To Use Your Own Scripts & Logs 

The easiest and most flexible way to use your own scripts and logs is to edit the `docker-compose.yml` file and mount your local directories:

```yaml
services:
  desto:
    build: .
    ports:
      - "8088:8088"
    volumes:
      - ./desto_scripts:/app/scripts  # Your scripts directory
      - ./desto_logs:/app/logs        # Your logs directory
    environment:
      - DESTO_SCRIPTS_DIR=/app/scripts
      - DESTO_LOGS_DIR=/app/logs
```

Place your scripts in `desto_scripts/` and logs will be saved in `desto_logs/`.

Make sure your bash scripts are executable:
```bash
chmod +x desto_scripts/*.sh
```


### Docker Management

```bash
# View logs
docker-compose logs -f desto

# Stop the service
docker-compose down

# Restart the service
docker-compose restart desto

# Rebuild after changes
docker-compose build --no-cache
docker-compose up -d
```


### Docker Examples

The repository includes example scripts in `desto_scripts/` for testing the Docker setup:

- `demo-script.sh` - Basic bash script demo
- `demo-script.py` - Python script demo
- `long-running-demo.sh` - Long-running process demo

These examples are automatically set up in `desto_scripts/` when you run:
```bash
make docker-setup-examples
```

This creates the `desto_scripts/` directory with the example scripts ready to use.



## 🔧 Traditional Installation

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

## 🖥️ Command Line Interface

In addition to the web dashboard, **desto** includes a powerful CLI for managing tmux sessions from the terminal. Perfect for automation, scripting, or when you prefer the command line.

### Installation as a uv Tool

```bash
# Install desto CLI globally
uv tool install desto

# Or install from source
cd /path/to/desto
uv tool install . --force
```

This installs two executables:
- `desto` - Web dashboard  
- `desto-cli` - Command-line interface

### Quick CLI Usage

```bash
# Check system status
desto-cli doctor

# Session Management
desto-cli sessions list

# Start a new session
desto-cli sessions start "my-task" "python my_script.py"

# View session logs
desto-cli sessions logs "my-task"

# Kill a session
desto-cli sessions kill "my-task"

# Script Management
desto-cli scripts list                     # List all scripts
desto-cli scripts create "my_script" --type python  # Create new script
desto-cli scripts edit "my_script"         # Edit script in $EDITOR  
desto-cli scripts run "my_script"          # Run script in tmux session
desto-cli scripts run "my_script" --direct # Run script directly
```

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
