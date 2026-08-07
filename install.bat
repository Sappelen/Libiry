@echo off
echo ========================================
echo  Libiry Installation
echo ========================================
echo.

REM Accept Python 3.11 or 3.12
set PYTHON=
py -3.12 --version >nul 2>&1 && set PYTHON=py -3.12
if "%PYTHON%"=="" (
    py -3.11 --version >nul 2>&1 && set PYTHON=py -3.11
)
if "%PYTHON%"=="" (
    echo ERROR: Python 3.11 or 3.12 is not installed.
    echo.
    echo Download from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('%PYTHON% --version') do echo Found %%i
echo.

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    %PYTHON% -m venv venv
    echo.
)

REM Install dependencies
echo Installing dependencies...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

REM Create launcher
echo Creating launcher...
(
    echo @echo off
    echo cd /d "%~dp0"
    echo call venv\Scripts\activate.bat
    echo python main.py
) > Libiry.bat

REM Create desktop shortcut via PowerShell
echo Creating desktop shortcut...
powershell -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Libiry.lnk');$s.TargetPath='%~dp0Libiry.bat';$s.WorkingDirectory='%~dp0';$
s.IconLocation='%~dp0resources\icons\Libiry.ico';$s.Save()"

echo.
echo ========================================
echo  Installation complete!
echo ========================================
echo.
echo A desktop shortcut has been created.
echo You can also launch Libiry with: Libiry.bat
echo.
pause