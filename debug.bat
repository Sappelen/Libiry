@echo off
cd /d "%~dp0"

REM Run with python.exe (not pythonw.exe) to see console output
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe main.py
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    python main.py
) else (
    echo Virtual environment not found.
    echo Please run install.bat first.
    pause
)
pause
