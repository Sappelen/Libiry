@echo off
REM =============================================================================
REM Build script voor Windows - maakt Libiry installer
REM =============================================================================
REM Dit script:
REM 1. Installeert build dependencies
REM 2. Bouwt de executable met PyInstaller
REM 3. Maakt de installer met Inno Setup
REM
REM Vereisten:
REM - Python 3.10+ in PATH
REM - Inno Setup 6 geinstalleerd (standaard locatie)
REM
REM Gebruik: Dubbelklik of run vanuit command prompt in de Libiry folder
REM =============================================================================

echo.
echo ========================================
echo   Libiry Windows Build Script
echo ========================================
echo.

REM Controleer of we in de juiste folder zijn
if not exist "main.py" (
    echo ERROR: main.py niet gevonden. Run dit script vanuit de Libiry folder.
    pause
    exit /b 1
)

REM Maak dist folder als die niet bestaat
if not exist "dist" mkdir dist
if not exist "dist\installer" mkdir dist\installer

REM Activeer venv als die bestaat, anders gebruik system Python
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo No venv found, using system Python...
)

REM Installeer/update build tools
echo.
echo [1/4] Installing build dependencies...
pip install --upgrade pip
pip install --upgrade pyinstaller
pip install --upgrade kivy_deps.sdl2 kivy_deps.glew

REM Installeer app dependencies
echo.
echo [2/4] Installing app dependencies...
pip install -r requirements.txt

REM Bouw met PyInstaller
echo.
echo [3/4] Building executable with PyInstaller...
echo This may take a few minutes...
pyinstaller --clean --noconfirm libiry.spec

if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed!
    pause
    exit /b 1
)

REM Controleer of build succesvol was
if not exist "dist\Libiry\Libiry.exe" (
    echo.
    echo ERROR: Libiry.exe not found in dist\Libiry
    pause
    exit /b 1
)

echo.
echo PyInstaller build successful!

REM Bouw installer met Inno Setup
echo.
echo [4/4] Creating installer with Inno Setup...

REM Zoek Inno Setup compiler
set ISCC=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
)

if %ISCC%=="" (
    echo.
    echo WARNING: Inno Setup not found!
    echo Please install Inno Setup 6 from: https://jrsoftware.org/isinfo.php
    echo.
    echo The PyInstaller build is complete. You can find the portable version in:
    echo   dist\Libiry\
    echo.
    echo After installing Inno Setup, run this script again or compile installer.iss manually.
    pause
    exit /b 0
)

%ISCC% installer.iss

if errorlevel 1 (
    echo.
    echo ERROR: Inno Setup build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo   BUILD COMPLETE!
echo ========================================
echo.
echo Installer created: dist\installer\LibirySetup.exe
echo Portable version:  dist\Libiry\
echo.
pause
