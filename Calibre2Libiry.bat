@echo off
:: Calibre2Libiry.bat — Launch Calibre2Libiry via the shared launcher.
:: No arguments : GUI mode   — pythonw.exe, no console window.
:: --debug      : Debug mode — python.exe, console stays open.
:: Other args   : CLI mode   — forwarded to Calibre2Libiry.py, console stays open.
cd /d "%~dp0"
if "%~1"=="" (
    if exist "venv\Scripts\pythonw.exe" (
        start "" venv\Scripts\pythonw.exe launcher.py calibre2libiry
    ) else (
        start "" pythonw launcher.py calibre2libiry
    )
) else (
    if exist "venv\Scripts\python.exe" (
        venv\Scripts\python.exe launcher.py calibre2libiry %*
    ) else (
        python launcher.py calibre2libiry %*
    )
    pause
)
