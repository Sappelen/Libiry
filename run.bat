@echo off
cd /d "%~dp0"

REM Check if virtual environment exists
if exist "venv\Scripts\pythonw.exe" (
    start "" venv\Scripts\pythonw.exe main.py
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    start "" pythonw main.py
) else (
    echo Virtual environment not found.
    echo Please run install.bat first.
    pause
)
