<p align="center">
  <img src="images/logo.png" alt="desto Logo" title="desto Logo" width="300" style="border:2px solid #ccc; border-radius:6px;"/>  
</p>  


**desto** lets you run and manage your bash and Python scripts in the background (inside `tmux` sessions) through a simple web dashboard. Launch scripts, monitor their and your system's status, view live logs, and control sessions—all from your browser.  

[![PyPI version](https://badge.fury.io/py/desto.svg)](https://badge.fury.io/py/desto) [![PyPI Downloads](https://static.pepy.tech/personalized-badge/desto?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/desto) ![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-blueviolet) ![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat) [![Tests](https://github.com/kalfasyan/desto/actions/workflows/ci.yml/badge.svg)](https://github.com/kalfasyan/desto/actions/workflows/ci.yml) [![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit) [![gitleaks](https://img.shields.io/badge/protected%20by-gitleaks-blue)](https://github.com/gitleaks/gitleaks-action) 

---

The key features are:  

- **One-click session control:** Launch, monitor, and stop `tmux` sessions from your browser.
- **🐚 Bash & 🐍 Python support:** Run both bash (`.sh`) and Python (`.py`) scripts seamlessly.
- **Script management:** Use your existing scripts, write new ones, edit, save, or delete them directly in the dashboard.
- **⭐ Favorite commands:** Save, organize, and quickly run your frequently used commands with usage tracking and search.
- **Live log viewer:** Watch script output in real time and view logs for each session.
- **Live system stats:** See real-time CPU, memory, and disk usage at a glance.
- **Scheduling:** Schedule scripts or script chains to launch at a specific date and time.
- **Script chaining:** Queue multiple scripts to run sequentially in a single session.
- **Session history:** [Redis](https://github.com/redis/redis-py) integration for persistent session tracking and history. [See what is Redis →](https://redis.io/about/)
- **Scheduled job control:** Manage scheduled jobs with a dedicated table—cancel any scheduled job with a click.
- **Session & log cleanup:** Clear session history and delete logs for all or selected sessions.
- **Notifications:** Optional Pushbullet notifications for job/session finishes — set the `DESTO_PUSHBULLET_API_KEY` environment variable or add the key in Settings to receive desktop/mobile pushes when jobs complete.
- **Persistent script & log storage:** Scripts and logs are saved in dedicated folders for easy access.
- **🖥️ Command-line interface:** Manage sessions, view logs, and control scripts from the terminal with our modern CLI. [Learn more →](user-guide/cli.md)
  
  
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
