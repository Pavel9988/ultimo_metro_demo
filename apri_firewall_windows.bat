@echo off
setlocal
cd /d "%~dp0"
title Ultimo Metro - apri il firewall
net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo  Serve eseguire questo file come amministratore:
  echo  clic destro sul file ^> "Esegui come amministratore".
  echo.
  pause
  exit /b 1
)
echo.
echo  Apro la porta 8765 ^(TCP, in entrata^) cosi' gli amici sulla tua stessa rete
echo  possono aprire Ultimo Metro. Per richiuderla: chiudi_firewall_windows.bat
echo.
netsh advfirewall firewall delete rule name="Ultimo Metro (porta 8765)" >nul 2>&1
netsh advfirewall firewall add rule name="Ultimo Metro (porta 8765)" dir=in action=allow protocol=TCP localport=8765 profile=any
echo.
pause
