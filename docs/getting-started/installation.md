# Installation

There are three ways to install `desto`. Pick one:

- **[One-line installer](#one-line-installer)**: the quickest way on Linux and macOS.
- **[Docker Compose](#docker-compose)**: everything, Redis included, in containers.
- **[Manually with `uv` or `pip`](#manual-install-with-uv-or-pip)**: full control over each piece.

Whichever you choose, the dashboard runs at [http://localhost:8809](http://localhost:8809).

## One-line installer

```bash
curl -LsSf https://raw.githubusercontent.com/kalfasyan/desto/main/install.sh | sh
```

Then start the dashboard with `desto`, or the terminal UI with `desto-tui`.

The [script](https://github.com/kalfasyan/desto/blob/main/install.sh) is short, so feel free to read it first. It:

1. Installs `tmux`, `at` and Redis with your package manager (apt, dnf, pacman or Homebrew), skipping any you already have. It uses `sudo` when you are not root. On Arch it installs Valkey, the drop-in Redis replacement Arch ships.
2. Starts Redis and `atd`, and enables them on boot.
3. Installs [`uv`](https://docs.astral.sh/uv/) if it is missing.
4. Runs `uv tool install desto`, which puts `desto`, `desto-tui` and `desto-cli` on your `PATH`.

If you already run Redis somewhere else (for example in Docker), skip steps 1 and 2:

```bash
curl -LsSf https://raw.githubusercontent.com/kalfasyan/desto/main/install.sh | DESTO_SKIP_PACKAGES=1 sh
```

Run the same command again to upgrade desto. Check that everything is in place with `desto-cli doctor`.

## Docker Compose

You only need [Docker](https://docs.docker.com/get-docker/).

```bash
git clone https://github.com/kalfasyan/desto.git && cd desto
docker compose up -d
```

Scripts in `desto_scripts/` and logs in `desto_logs/` inside the clone are shared with the container.

desto is installed inside the container, not on your machine, so `desto-tui` and `desto-cli` run there too:

```bash
docker compose exec dashboard uv run desto-tui
docker compose exec dashboard uv run desto-cli sessions list
```

Handy commands:

```bash
docker compose logs -f           # follow the logs
docker compose up -d --build     # rebuild after pulling changes
docker compose down              # stop and remove the containers
```

## Manual install with `uv` or `pip`

### Requirements

- Python 3.11+
- [tmux](https://github.com/tmux/tmux)
- A running [Redis](https://redis.io/docs/latest/operate/oss_and_stack/install/) server. desto stores its session state there and will not start without it.
- [at](https://en.wikipedia.org/wiki/At_(command)), only needed for scheduling.

```bash
# Debian/Ubuntu
sudo apt install tmux at redis-server

# Fedora/AlmaLinux
sudo dnf install tmux at redis
sudo systemctl enable --now redis atd

# Arch Linux (Arch ships Valkey, a drop-in Redis replacement)
sudo pacman -S tmux at valkey
sudo systemctl enable --now valkey atd

# macOS
brew install tmux redis
brew services start redis
```

By default desto connects to Redis on `localhost:6379`. Set `REDIS_HOST` and `REDIS_PORT` to use another server.

### Install desto

As a global tool with [uv](https://docs.astral.sh/uv/getting-started/installation/) (recommended):

```bash
uv tool install desto
```

This installs `desto` (web dashboard), `desto-tui` (terminal UI) and `desto-cli` (command line).

Or add it to an existing `uv` project:

```bash
uv add desto
```

Or with pip:

```bash
pip install desto
```

To install from a local clone instead, run `uv tool install . --force` in the repository.

### Run it

```bash
desto
```

desto creates `desto_scripts/` and `desto_logs/` in the current directory.

## Uninstall

### One-line installer or `uv tool install`

```bash
desto-cli service uninstall   # only if you set up the systemd service
uv tool uninstall desto
```

`tmux`, `at`, Redis and `uv` stay installed, since other tools may use them. Remove them with your package manager if you don't need them, for example `sudo apt remove tmux at redis-server`. Your `desto_scripts/` and `desto_logs/` folders stay where you ran desto.

If you installed with `pip`, run `pip uninstall desto` instead.

### Docker Compose

From inside the `desto` folder:

```bash
docker compose down -v --rmi all   # containers, network, volumes and images
cd .. && sudo rm -rf desto         # the clone, including desto_scripts/ and desto_logs/
```

`sudo` is needed because the container writes its logs as root. Copy out any scripts you want to keep first.
