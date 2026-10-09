#!/bin/bash
# Avvia Ultimo Metro su Linux:  ./run_linux.sh
cd "$(dirname "$0")" || exit 1
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then echo "Serve Python 3.9 o piu' recente."; exit 1; fi
exec "$PY" app.py "$@"
