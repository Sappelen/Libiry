@echo off
cd /d "%~dp0"

:: Align Book Data Debug version - shows console output
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe align_book_data.py
    pause
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    python align_book_data.py
    pause
) else (
    echo Virtual environment not found.
    echo Please run install.bat first.
    pause
)

