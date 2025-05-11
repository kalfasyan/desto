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

2. **Install `desto`**:
    <details>
    <summary>Installation Steps</summary>

    - Navigate to the `scripts` directory:
      ```bash
      cd desto/scripts
      ```

    - Make the installation script executable:
      ```bash
      chmod +x install.sh
      ```

    - Run the installation script:
      ```bash
      ./install.sh
      ```

    </details>

3. **Run the Application**:  
Simply type `desto` in your terminal from any directory to start the application.

4. **View on the browser**:  
You will see the message:  
    >NiceGUI ready to go on http://localhost:8088, and http://192.168.0.114:8088
    Opening in existing browser session.

## Dashboard
![Dashboard Screenshot](images/dashboard.png "Desto Dashboard")
