#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON_BIN was not found. Install Python 3.10+ and rerun." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c "import PyQt6" >/dev/null 2>&1; then
  echo "ERROR: PyQt6 is missing for $PYTHON_BIN." >&2
  echo "On Ubuntu 22.04, install it with: sudo apt install python3-pyqt6" >&2
  echo "Alternatively: python3 -m pip install -r requirements.txt" >&2
  exit 1
fi

exec "$PYTHON_BIN" -u "$SCRIPT_DIR/edith_gcs_qt.py" "$@"
