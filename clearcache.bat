@echo off
REM Libiry Cache Cleaner - Windows
REM Verwijdert de Libiry cache folder (~/.libiry/cache)

set CACHE_DIR=%USERPROFILE%\.libiry\cache

if exist "%CACHE_DIR%" (
    echo Clearing Libiry cache: %CACHE_DIR%
    rmdir /s /q "%CACHE_DIR%"
    echo Cache cleared.
) else (
    echo No cache found at %CACHE_DIR%
)

pause
