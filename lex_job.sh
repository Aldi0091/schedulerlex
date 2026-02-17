#!/usr/bin/env bash
set -euo pipefail

# Always run from this script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "== Lexoffice Scheduler =="
echo "Workdir: $SCRIPT_DIR"
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo

# ---- settings (can be overridden by env vars) ----
VENV_DIR="${VENV_DIR:-venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PIP_INSTALL_ALWAYS="${PIP_INSTALL_ALWAYS:-0}"   # 0 = only first time, 1 = pip install each run
PURGE_AFTER="${PURGE_AFTER:-1}"                 # 1 = run purge.py, 0 = skip purge
SEND_EMAIL_AFTER="${SEND_EMAIL_AFTER:-1}"       # 1 = run send_email.py, 0 = skip send_email
# -----------------------------------------------

# Basic checks
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR: python3 not found"; exit 1; }

if [[ ! -f ".env" ]]; then
  echo "ERROR: .env not found in $SCRIPT_DIR"
  echo "Create .env with LEXOFFICE_TOKEN and (optionally) MAIL_ADDRESS/MAIL_APP_PASSWORD/EMAIL_TO"
  exit 1
fi

# Create venv if missing
if [[ ! -d "$VENV_DIR" ]]; then
  echo "[venv] creating venv at: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  echo "[venv] exists: $VENV_DIR"
fi

# Activate venv
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

echo "[venv] python: $(python --version)"
echo "[venv] pip: $(pip --version | head -n 1)"
echo

# Install deps (first time only, unless forced)
NEED_INSTALL=0
if [[ "$PIP_INSTALL_ALWAYS" == "1" ]]; then
  NEED_INSTALL=1
elif [[ ! -f "$VENV_DIR/.deps_installed" ]]; then
  NEED_INSTALL=1
fi

if [[ "$NEED_INSTALL" == "1" ]]; then
  echo "[deps] installing requirements.txt"
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  touch "$VENV_DIR/.deps_installed"
else
  echo "[deps] already installed (set PIP_INSTALL_ALWAYS=1 to force reinstall)"
fi

echo
echo "== Running jobs =="

run_step () {
  local name="$1"
  shift
  echo
  echo "---- $name ----"
  echo "+ $*"
  "$@"
  echo "---- $name DONE ----"
}

# Create dirs (safe)
mkdir -p csv logs email

# Run CSV scripts
run_step "CSV A" python csv_a.py
run_step "CSV B" python csv_b.py
run_step "CSV C" python csv_c.py

# Send email
if [[ "$SEND_EMAIL_AFTER" == "1" ]]; then
  run_step "SEND EMAIL" python send_email.py
else
  echo
  echo "[skip] send_email.py (SEND_EMAIL_AFTER=0)"
fi

# Purge
if [[ "$PURGE_AFTER" == "1" ]]; then
  run_step "PURGE" python purge.py
else
  echo
  echo "[skip] purge.py (PURGE_AFTER=0)"
fi

echo
echo "== All done =="
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
