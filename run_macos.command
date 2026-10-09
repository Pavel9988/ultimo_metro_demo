#!/bin/bash
# Doppio clic per avviare Ultimo Metro su macOS (equivalente di run_windows.bat).
cd "$(dirname "$0")" || exit 1
clear
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo
  echo " Python 3.9 o piu' recente non trovato."
  echo " Installalo da https://www.python.org/downloads/macos/"
  echo " (oppure da Terminale: xcode-select --install) e rifai doppio clic su questo file."
  echo
  open "https://www.python.org/downloads/macos/" 2>/dev/null
  read -n 1 -s -r -p " Premi un tasto per chiudere..."
  exit 1
fi
echo " Nota: se macOS chiede 'Vuoi consentire le connessioni in entrata?' scegli CONSENTI,"
echo " altrimenti gli amici non riescono ad aprire la pagina."
"$PY" app.py
echo
read -n 1 -s -r -p " Il server si e' fermato. Premi un tasto per chiudere..."
