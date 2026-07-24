@echo off
cd /d "%~dp0"

:: Calibre2libiry Debug version - shows console output
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe calibre2libiry.py
    pause
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    python calibre2libiry.py
    pause
) else (
    echo Virtual environment not found.
    echo Please run install.bat first.
    pause
)
