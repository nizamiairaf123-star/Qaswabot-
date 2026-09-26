#!/usr/bin/env bash
# scripts/freeze_requirements.sh
#
# WHY THIS EXISTS (Section 5 audit finding, FIX-D):
# requirements.txt lists packages with NO version pins. That means every
# fresh `pip install -r requirements.txt` pulls whatever the latest
# available version is *on that day* — with no guarantee it matches what
# was actually tested. For a live-money trading bot depending on fragile
# broker (dhanhq) and market-data (yfinance) APIs, this is a real
# reproducibility risk: a routine reinstall months from now could silently
# pull a breaking version change.
#
# This audit could NOT safely guess exact version numbers to pin, since
# doing so without actually testing the combination could pin BROKEN
# versions together — worse than no pin at all.
#
# WHAT TO DO INSTEAD (run this once, after you have a working install):
#
#   1. Deploy normally: ./deploy.sh (creates .venv, installs requirements.txt)
#   2. Run the bot in paper mode for a few days and confirm everything works.
#   3. Run this script: bash scripts/freeze_requirements.sh
#      It writes requirements-lock.txt with the EXACT versions that are
#      actually working on your VPS right now.
#   4. Commit requirements-lock.txt to your own copy of the project.
#   5. From then on, deploy.sh should install from requirements-lock.txt
#      instead of requirements.txt, so every future install reproduces
#      this exact known-good environment.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "ERROR: $VENV_DIR not found. Run deploy.sh first to create a working install." >&2
  exit 1
fi

"$VENV_DIR/bin/python" -m pip freeze > "$ROOT_DIR/requirements-lock.txt"
echo "Wrote $ROOT_DIR/requirements-lock.txt with your current, working package versions."
echo "Review it, commit it, and switch deploy.sh to install from it going forward."
