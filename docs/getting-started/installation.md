# Installation

Pick one way to install. Each one has its matching uninstall right below it.

| Method | Best for |
|---|---|
| [One-line installer](#one-line-installer) | The quickest start on Linux or macOS |
| [Docker Compose](#docker-compose) | Keeping everything, Redis included, in containers |
| [`uv` or `pip`](#uv-or-pip) | Setting up `tmux` and Redis yourself |
| [From source](#from-source) | Trying the latest code or contributing |

Once installed, start the web dashboard with `desto` and open [http://localhost:8809](http://localhost:8809), or start the terminal UI with `desto-tui`.

## One-line installer

**Install**

```bash
curl -LsSf https://raw.githubusercontent.com/kalfasyan/desto/main/install.sh | sh
```

The [script](https://github.com/kalfasyan/desto) (`install.sh` in the repository) installs `tmux`, `at` and Redis with your package manager (apt, dnf, pacman or Homebrew, using `sudo`), starts Redis, installs [`uv`](https://docs.astral.sh/uv/) if needed, and runs `uv tool install desto`. Run it again to upgrade.

Already running Redis elsewhere, for example in Docker? End the command with `| DESTO_SKIP_PACKAGES=1 sh` to install only desto.

**Uninstall**

```bash
uv tool uninstall desto
```

## Docker Compose

You only need [Docker](https://docs.docker.com/get-docker/).

**Install**

```bash
git clone https://github.com/kalfasyan/desto.git && cd desto
docker compose up -d
```

Your scripts go in `desto_scripts/` and logs land in `desto_logs/`, both inside the `desto` folder. desto runs inside the container, so run the terminal UI and CLI there too:

```bash
docker compose exec dashboard uv run desto-tui
docker compose exec dashboard uv run desto-cli sessions list
```

To upgrade, run `git pull && docker compose up -d --build`.

**Uninstall**

From inside the `desto` folder. This deletes your scripts and logs too, so copy out anything you want to keep first.

```bash
docker compose down -v --rmi all   # containers, network, volumes and images
cd .. && sudo rm -rf desto         # the folder (sudo, because the container writes logs as root)
```

## `uv` or `pip`

**Requirements:** Python 3.11+, `tmux`, a running Redis server (desto won't start without it), and `at` for scheduling.

```bash
# Debian/Ubuntu
sudo apt install tmux at redis-server

# Fedora/AlmaLinux
sudo dnf install tmux at redis && sudo systemctl enable --now redis atd

# Arch Linux (Valkey is Arch's drop-in Redis replacement)
sudo pacman -S tmux at valkey && sudo systemctl enable --now valkey atd

# macOS
brew install tmux redis && brew services start redis
```

desto looks for Redis on `localhost:6379`. Set `REDIS_HOST` and `REDIS_PORT` to use another server.

**Install**

```bash
uv tool install desto    # or: pip install desto
```

To upgrade, run `uv tool upgrade desto` (or `pip install -U desto`).

**Uninstall**

```bash
uv tool uninstall desto  # or: pip uninstall desto
```

## From source

Needs the same requirements as [`uv` or `pip`](#uv-or-pip).

**Install**

```bash
git clone https://github.com/kalfasyan/desto.git && cd desto
uv tool install .
```

Or install the latest `main` without cloning: `uv tool install git+https://github.com/kalfasyan/desto`.

**Uninstall**

```bash
uv tool uninstall desto
cd .. && rm -rf desto
```

## What uninstalling leaves behind

- **`tmux`, `at`, Redis and `uv`** stay installed, since other tools may use them. Remove them with your package manager if you don't need them, for example `sudo apt remove tmux at redis-server`.
- **Your scripts and logs** in `desto_scripts/` and `desto_logs/` stay in the folder where you ran desto.
- **The systemd service**, if you set one up, needs removing before you uninstall: `desto-cli service uninstall`.
