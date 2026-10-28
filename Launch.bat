@echo off
title Fish It Assistant
cd /d "%~dp0"

echo Starting roblox-fishit-autoperfect...

:: Check if virtual environment exists
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" app.py
) else if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" app.py
) else (
    python app.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred while running the app.
    echo Make sure dependencies are installed: pip install -r requirements.txt
    pause
)
