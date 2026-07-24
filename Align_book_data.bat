@echo off
:: Align book data.bat — Launch the metadata tool via the shared launcher.
:: No arguments : GUI mode   — pythonw.exe, no console window.
:: --debug      : Debug mode — python.exe, console stays open.
:: Other args   : CLI mode   — forwarded to the script, console stays open.
cd /d "%~dp0"
if "%~1"=="" (
    if exist "venv\Scripts\pythonw.exe" (
        start "" venv\Scripts\pythonw.exe launcher.py align_book_data
    ) else (
        start "" pythonw launcher.py align_book_data
    )
) else (
    if exist "venv\Scripts\python.exe" (
        venv\Scripts\python.exe launcher.py align_book_data %*
    ) else (
        python launcher.py align_book_data %*
    )
    pause
)
