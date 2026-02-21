@echo off
:: Libiry2Go - Portable Book Catalog Generator
:: Double-click this file to start the GUI

cd /d "%~dp0"
python libiry2go.py

:: If Python is not found, show error
if errorlevel 1 (
    echo.
    echo Error: Python not found. Please install Python 3.8 or higher.
    echo https://www.python.org/downloads/
    pause
)
