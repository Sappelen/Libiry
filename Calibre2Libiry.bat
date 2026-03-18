@echo off
REM Calibre2Libiry - Convert Calibre metadata & covers to Libiry format
REM Double-click to open GUI, or pass a path for CLI mode

cd /d "%~dp0"

REM Check of er een argument is (CLI mode) of niet (GUI mode)
if "%~1"=="" (
    REM GUI mode - gebruik pythonw (geen console popup)
    if exist "venv\Scripts\pythonw.exe" (
        start "" venv\Scripts\pythonw.exe Calibre2Libiry.py
    ) else (
        start "" pythonw Calibre2Libiry.py
    )
) else (
    REM CLI mode - met console voor output
    if exist "venv\Scripts\python.exe" (
        venv\Scripts\python.exe Calibre2Libiry.py %*
    ) else (
        python Calibre2Libiry.py %*
    )
    pause
)
