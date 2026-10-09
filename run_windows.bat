@echo off
setlocal
cd /d "%~dp0"
echo.
echo ================================================
echo             ULTIMO METRO - DEMO
echo ================================================
echo.
where py >nul 2>nul
if %errorlevel%==0 goto use_py
where python >nul 2>nul
if %errorlevel%==0 goto use_python
echo Python non trovato. Installa Python 3.10 o successivo da https://www.python.org/downloads/
echo Durante l'installazione seleziona Add Python to PATH.
pause
goto end
:use_py
start "Ultimo Metro Browser" cmd /c "timeout /t 2 >nul & start http://127.0.0.1:5000"
py -3 app.py
goto end
:use_python
start "Ultimo Metro Browser" cmd /c "timeout /t 2 >nul & start http://127.0.0.1:5000"
python app.py
goto end
:end
endlocal
