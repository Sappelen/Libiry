@echo off
:: run.bat — Launch the main Libiry application via the shared launcher.
:: No arguments : GUI mode   — pythonw.exe, no console window.
:: --debug      : Debug mode — python.exe, console stays open.
cd /d "%~dp0"
if "%~1"=="" (
    if exist "venv\Scripts\pythonw.exe" (
        start "" venv\Scripts\pythonw.exe launcher.py main
    ) else (
        start "" pythonw launcher.py main
    )
) else (
    if exist "venv\Scripts\python.exe" (
        venv\Scripts\python.exe launcher.py main %*
    ) else (
        python launcher.py main %*
    )
    pause
)
