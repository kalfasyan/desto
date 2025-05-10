# desto

desto is a simple and intuitive dashboard for managing and monitoring `tmux` sessions. It provides a user-friendly interface to start, view, and kill `tmux` sessions, as well as monitor system stats and view session logs.

## Features

- **Session Management**: Start, view, and kill `tmux` sessions with ease.
- **System Monitoring**: Real-time CPU, memory, and disk usage stats.
- **Log Viewer**: View live session logs in a clean, scrollable interface.

## Installation

1. **Install `tmux`**:
   <details>
   <summary>Instructions for different package managers</summary>

   - For Debian/Ubuntu:
     ```bash
     sudo apt install tmux
     ```

   - For Almalinux/Fedora:
     ```bash
     sudo dnf install tmux
     ```

   - For Arch Linux:
     ```bash
     sudo pacman -S tmux
     ```

   </details>

2. **Sync Dependencies**:
   ```bash
   uv sync  
   uv pip install -e .```

3. **Run the Application**:  
`python src/desto/app/ui.py`

4. **View on the browser**:  
You will see the message:  
    >NiceGUI ready to go on http://localhost:8080, and http://192.168.0.114:8080
    Opening in existing browser session.

## Dashboard
![Dashboard Screenshot](images/dashboard.png "Desto Dashboard")