@echo off
setlocal
echo Starting TANUQ UI (server runs in a minimized window)...
start "TANUQ UI" /min cmd /c ""%~dp0python.exe" -m tanuq ui %*"
timeout /t 2 /nobreak >nul
echo.
echo If the browser page asks for a token, run this in a terminal:
echo     tanuq token
echo.
start "" "http://127.0.0.1:8770"
