#!/bin/sh
# desto installer: https://github.com/kalfasyan/desto
#
#   curl -LsSf https://raw.githubusercontent.com/kalfasyan/desto/main/install.sh | sh
#
# What it does, in order:
#   1. Installs tmux, at and Redis with your package manager (apt, dnf, pacman or Homebrew),
#      skipping any that are already installed. This step uses sudo when you are not root.
#   2. Starts Redis (and atd) and enables them on boot.
#   3. Installs uv (https://docs.astral.sh/uv/) if it is missing.
#   4. Installs desto with `uv tool install`, which gives you `desto`, `desto-tui` and `desto-cli`.
#
# Set DESTO_SKIP_PACKAGES=1 to skip steps 1 and 2 (for example, if you run Redis in Docker).
# Read before you run: this script is short on purpose.

set -eu

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
has() { command -v "$1" >/dev/null 2>&1; }

# Run a command as root: directly if we already are, otherwise through sudo.
as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif has sudo; then
        sudo "$@"
    else
        die "need root to run '$*' and sudo is not installed"
    fi
}

# Print the packages that still need installing, using this package manager's names.
missing_packages() {
    redis_pkg=$1
    has tmux || printf 'tmux '
    has at || printf 'at '
    has redis-server || has valkey-server || printf '%s ' "$redis_pkg"
}

# Enable and start the first of the given systemd services that exists.
start_service() {
    if ! has systemctl || [ ! -d /run/systemd/system ]; then
        warn "systemd is not running here, so start $1 yourself"
        return 0
    fi
    for svc in "$@"; do
        if systemctl cat "$svc.service" >/dev/null 2>&1; then
            as_root systemctl enable --now "$svc" && return 0
        fi
    done
    warn "could not find a systemd service for: $*"
}

install_packages() {
    if has apt-get; then
        pkgs=$(missing_packages redis-server)
        if [ -n "$pkgs" ]; then
            say "Installing ${pkgs% } with apt"
            as_root apt-get update
            # shellcheck disable=SC2086 # word splitting is intended
            as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y $pkgs
        fi
    elif has dnf; then
        pkgs=$(missing_packages redis)
        if [ -n "$pkgs" ]; then
            say "Installing ${pkgs% } with dnf"
            # shellcheck disable=SC2086
            as_root dnf install -y $pkgs
        fi
    elif has pacman; then
        pkgs=$(missing_packages valkey)  # Arch replaced Redis with Valkey, a drop-in replacement
        if [ -n "$pkgs" ]; then
            say "Installing ${pkgs% } with pacman"
            # shellcheck disable=SC2086
            as_root pacman -S --needed --noconfirm $pkgs
        fi
    elif has brew; then
        # macOS ships `at`, but its job runner is off by default, so scheduling needs extra setup there.
        pkgs=$(has tmux || printf 'tmux '; has redis-server || printf 'redis')
        if [ -n "$pkgs" ]; then
            say "Installing ${pkgs% } with Homebrew"
            # shellcheck disable=SC2086
            brew install $pkgs
        fi
        say "Starting Redis"
        brew services start redis
        return 0
    else
        warn "no supported package manager found (apt, dnf, pacman or brew)."
        warn "Install tmux, at and Redis yourself, then make sure Redis is running."
        return 0
    fi

    say "Starting Redis and atd"
    start_service redis-server redis valkey
    start_service atd
}

install_desto() {
    if ! has uv; then
        has curl || die "curl is needed to install uv"
        say "Installing uv"
        curl -LsSf https://astral.sh/uv/install.sh | sh
        PATH="$HOME/.local/bin:$PATH"
        has uv || die "uv was installed but is not on PATH; open a new terminal and run this script again"
    fi

    say "Installing desto"
    uv tool install --upgrade --refresh-package desto desto  # ignore a stale cached index
}

main() {
    if [ "${DESTO_SKIP_PACKAGES:-0}" = 1 ]; then
        say "Skipping system packages (DESTO_SKIP_PACKAGES=1)"
    else
        install_packages
    fi
    install_desto

    printf '\n'
    say "desto is installed."
    if has desto; then
        echo "    Run 'desto' and open http://localhost:8809."
        if has desto-tui; then echo "    Run 'desto-tui' for the terminal UI."; fi
        echo "    Run 'desto-cli doctor' to check tmux and Redis."
    else
        echo "    Open a new terminal (or run 'uv tool update-shell') so 'desto' is on your PATH,"
        echo "    then run 'desto' and open http://localhost:8809."
    fi
}

# Everything runs from here, so a partially downloaded script does nothing.
main "$@"
