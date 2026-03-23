#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="c:/python314/python.exe"
VENV_DIR=".venv"
ACTIVATE_SCRIPT="$VENV_DIR/Scripts/activate"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: Python not found at $PYTHON_BIN"
  echo "Edit start_counter.sh and set PYTHON_BIN to your Python path."
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating virtual environment in $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$ACTIVATE_SCRIPT"

echo "Installing dependencies"
python -m pip install -r requirements.txt

if [[ ! -f "data/hell_targets.json" ]]; then
  echo "Generating bundled hell target data"
  python scripts/generate_hell_targets.py
fi

echo "Starting TZ Counter"
python -m tz_counter
