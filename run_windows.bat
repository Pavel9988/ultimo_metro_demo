@echo off
setlocal
cd /d "%~dp0"
title Ultimo Metro
set "PY="
for %%C in ("py -3" "python" "python3") do (
  if not defined PY (
    %%~C -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul && set "PY=%%~C"
  )
)
if not defined PY (
  echo.
  echo  Python 3.9 o piu' recente non trovato.
  echo  Installalo da https://www.python.org/downloads/  ^(spunta "Add python.exe to PATH"^)
  echo  poi fai doppio clic su questo file.
  echo.
  start "" https://www.python.org/downloads/
  pause
  exit /b 1
)
%PY% app.py
echo.
echo  Il server si e' fermato. Se vedi un errore qui sopra, copialo e mandamelo.
pause
