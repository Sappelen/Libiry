@echo off
setlocal enabledelayedexpansion
REM Check PDF Tags - Test welke PDFs tags kunnen lezen/schrijven
REM
REM Gebruik:
REM   check_pdf_tags.bat           - Vraagt om folder keuze
REM   check_pdf_tags.bat [folder]  - Scant de opgegeven folder
REM
REM Voor PDFs waar tag-ondersteuning faalt, wordt een OPF sidecar file aangemaakt.

cd /d "%~dp0"

if "%~1"=="" (
    echo.
    echo Check PDF Tags - Test tag-ondersteuning voor PDFs
    echo ==================================================
    echo.
    echo Geef een folder op om te scannen, of sleep een folder op dit .bat bestand.
    echo.
    set /p FOLDER="Folder om te scannen (of Enter voor huidige folder): "
    if "!FOLDER!"=="" (
        set FOLDER=.
    )
    python check_pdf_tags.py "!FOLDER!"
) else (
    python check_pdf_tags.py "%~1"
)

echo.
pause
