@echo off
echo ========================================
echo  Libiry Installation
echo ========================================
echo.

REM Check if Python 3.12 is available
py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.12 is not installed.
    echo.
    echo Please download and install Python 3.12 from:
    echo https://www.python.org/downloads/release/python-3120/
    echo.
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo Found Python 3.12
echo.

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment with Python 3.12...
    py -3.12 -m venv venv
    echo Virtual environment created.
    echo.
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo.
echo Installing dependencies...
pip install -r requirements.txt

echo.
echo ========================================
echo  Installation complete!
echo ========================================
echo.
echo To run Libiry, use: run.bat
echo.
pause
