#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "ERROR: .env is missing. Copy .env.example to .env and configure credentials first." >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"

# Section 5 audit finding (FIX-E): SYSTEM_BLUEPRINT.md documents Python 3.12
# as required, but nothing here ever checked it — enforce it now.
PY_VER="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
PY_MAJOR="${PY_VER%%.*}"
PY_MINOR="${PY_VER##*.}"
if [[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 12 ) ]]; then
  echo "ERROR: Python 3.12+ is required (SYSTEM_BLUEPRINT.md). Found $PYTHON_BIN -> $PY_VER." >&2
  echo "Install Python 3.12 or set PYTHON_BIN to point at a 3.12+ interpreter." >&2
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
INSTALL_REQUIREMENTS="requirements.txt"
if [[ -f requirements-lock.txt ]]; then
  INSTALL_REQUIREMENTS="requirements-lock.txt"
  echo "Using pinned dependency lock: $INSTALL_REQUIREMENTS"
else
  echo "WARNING: requirements-lock.txt not present; using unpinned requirements.txt" >&2
fi

"$VENV_DIR/bin/python" -m pip install -r "$INSTALL_REQUIREMENTS"
"$VENV_DIR/bin/python" -m py_compile ./*.py

echo "Deployment bootstrap complete."
echo "Start manually with: ./start_bot.sh"
