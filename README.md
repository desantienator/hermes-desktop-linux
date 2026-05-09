# Hermes Desktop Linux

Native Linux desktop companion for Hermes Agent over SSH.

This is the Linux port of `dodo-reach/hermes-desktop`: same core model, no browser wrapper, no gateway dependency, no remote daemon. It connects to a Hermes host over SSH, runs remote Python probes, and presents the real remote state in a native Qt desktop window.

## Current features

- PySide6/Qt native Linux UI with a Hermes-style dark sidebar and split-pane workspace
- Connection profile storage under `~/.config/hermes-desktop-linux/connections.json`
- Localhost mode for running against this machine without SSH
- SSH mode using your existing `ssh` config, keys, aliases, and host trust
- Overview: remote host, user, Python, Hermes home, Hermes binary discovery
- Sessions: discover likely session/transcript files and preview content
- Kanban: inspect upstream `~/.hermes/kanban.db` boards/tasks/tables
- Files: browse remote Hermes files, open/edit/save text files with confirmation
- Usage: session file count, total bytes, recent files
- Skills: discover `SKILL.md` files and preview content
- Cron: calls `hermes cron list --json` where available
- Terminal: launches your installed Linux terminal emulator into SSH

## Install on Arch Linux

```bash
sudo pacman -Syu
sudo pacman -S --needed git python pyside6 openssh mesa libglvnd

git clone https://github.com/desantienator/hermes-desktop-linux.git
cd hermes-desktop-linux
python -m hermes_desktop_linux
```

Optional editable install:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
hermes-desktop-linux
```

## Install on Debian/Ubuntu

```bash
sudo apt update
sudo apt install -y git python3 python3-pip openssh-client

git clone https://github.com/desantienator/hermes-desktop-linux.git
cd hermes-desktop-linux
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
hermes-desktop-linux
```

## Profiles

Use **Edit profile** in the app.

Local Hermes:

```text
local,localhost,adrian,22,~/.hermes,
```

SSH alias from `~/.ssh/config`:

```text
bob,bob-server,adrian,22,~/.hermes,bob-server
```

Before using a remote profile, make sure SSH works in a normal terminal:

```bash
ssh bob-server
```

## Tests

Core tests avoid Qt so they can run headless:

```bash
./scripts/test.sh
```

## Safety

Remote file saves require confirmation. Writes are limited to the configured `HERMES_HOME`, capped at 10MB, and saved atomically through a temp file.

## Known gaps

The UI is now a real Qt desktop app and the read-oriented features work through the backend. Full parity still needs the heavier mutation surfaces from the macOS app: Kanban task creation/update/dispatch, cron create/edit/pause/resume/delete, in-app chat turns, and an embedded PTY terminal widget.
