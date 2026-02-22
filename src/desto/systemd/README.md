# Desto Systemd Templates

This directory contains systemd service templates for `desto`.

- `desto.service.template`: Template for user-level service (installed in `~/.config/systemd/user/`).
- `desto-system.service.template`: Template for system-level service (installed in `/etc/systemd/system/`).

These templates are used by the `desto-cli service install` command to generate and install the appropriate service files for your system.
