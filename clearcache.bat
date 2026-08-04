@echo off
REM Libiry Cache Cleaner - Windows
REM Removes the Libiry cache folder

set CACHE_DIR=%LOCALAPPDATA%\Libiry\cache

if exist "%CACHE_DIR%" (
    echo Clearing Libiry cache: %CACHE_DIR%
    rmdir /s /q "%CACHE_DIR%"
    echo Cache cleared.
) else (
    echo No cache found at %CACHE_DIR%
)

pause
