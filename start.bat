@echo off
REM ShopPilot — start the local FastAPI server and open the dashboard.
REM Double-click this file (or run from a terminal) to bring everything up.

cd /d "%~dp0"

if not exist ".venv\Scripts\uvicorn.exe" (
    echo [start.bat] ERROR: .venv not found at "%~dp0.venv".
    echo Run:  py -3.14 -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo [start.bat] Launching ShopPilot on http://127.0.0.1:8000
echo [start.bat] Dashboard:  http://127.0.0.1:8000/dashboard
echo [start.bat] Press Ctrl+C in this window to stop the server.
echo.

REM Open the dashboard in the default browser after a short delay so the
REM server has time to bind. The `start` command returns immediately, then
REM we exec uvicorn in the foreground.
start "" /b cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8000/dashboard"

".venv\Scripts\uvicorn.exe" main:app --host 127.0.0.1 --port 8000

REM If uvicorn exits (Ctrl+C or crash), keep the window open so the user can
REM read any error output before it disappears.
echo.
echo [start.bat] Server stopped.
pause
