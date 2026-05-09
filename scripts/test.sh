#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m compileall -q hermes_desktop_linux tests
python3 -m unittest discover -s tests -v
