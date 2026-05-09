# Hermes Desktop Linux

Native Linux desktop companion for Hermes Agent over SSH.

This is a practical Linux port of `dodo-reach/hermes-desktop`: same core idea, no browser wrapper, no gateway dependency, no remote daemon. It connects to a Hermes host over SSH, runs small remote Python probes, and presents the real remote state in one native desktop window.

## Current features

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

## Run

Requires Tkinter on Linux:

```bash
sudo apt install python3-tk
cd /home/adrian/projects/hermes-desktop-linux
python3 -m hermes_desktop_linux.app
```

On systems where Tkinter is already bundled with Python, just run the module.

For packaging later:

```bash
python3 -m pip install build
python3 -m build
```

## Notes

The macOS app uses SwiftUI and SwiftTerm. This Linux port uses Python + Tk from the standard library so it runs on a normal Linux desktop without dragging in half of KDE or Qt as cargo cult ballast. The terminal is external for v0.1; embedding a real xterm-compatible widget is the right v0.2 job.

## Safety

Remote file saves require confirmation. Everything else is read-only except whatever you do in the launched terminal.
