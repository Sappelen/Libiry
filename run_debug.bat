@echo off
cd /d "%~dp0"

REM Debug version - shows console output
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe main.py
    pause
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    python main.py
    pause
) else (
    echo Virtual environment not found.
    echo Please run install.bat first.
    pause
)
