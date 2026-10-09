#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 non trovato. Installa Python 3.10 o successivo." >&2
  exit 1
fi
python3 app.py
