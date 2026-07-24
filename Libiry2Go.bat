@echo off
:: Libiry2Go.bat — Launch Libiry2Go via the shared launcher.
:: No arguments : GUI mode   — pythonw.exe, no console window.
:: --debug      : Debug mode — python.exe, console stays open.
:: Other args   : CLI mode   — forwarded to libiry2go.py, console stays open.
cd /d "%~dp0"
if "%~1"=="" (
    if exist "venv\Scripts\pythonw.exe" (
        start "" venv\Scripts\pythonw.exe launcher.py libiry2go
    ) else (
        start "" pythonw launcher.py libiry2go
    )
) else (
    if exist "venv\Scripts\python.exe" (
        venv\Scripts\python.exe launcher.py libiry2go %*
    ) else (
        python launcher.py libiry2go %*
    )
    pause
)
