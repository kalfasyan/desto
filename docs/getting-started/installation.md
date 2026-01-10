# Installation

`desto` can be installed using Docker, `uv`, or `pip`.

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

### Requirements

- Python 3.11+
- [tmux](https://github.com/tmux/tmux)
- [at](https://en.wikipedia.org/wiki/At_(command)) (for scheduling features)

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

🎉 **Done!**  
Open your browser and visit: [http://localhost:8809](http://localhost:8809) 🚀

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
- `desto-cli` - Command-line interface
