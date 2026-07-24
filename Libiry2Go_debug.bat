@echo off
cd /d "%~dp0"

:: Libiry2Go Debug version - shows console output
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe libiry2go.py
    pause
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    python libiry2go.py
    pause
) else (
    echo Virtual environment not found.
    echo Please run install.bat first.
    pause
)
