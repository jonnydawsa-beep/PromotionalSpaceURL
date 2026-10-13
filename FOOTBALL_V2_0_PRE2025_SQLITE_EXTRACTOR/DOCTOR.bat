@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Football V2.0 SQLite Extractor - Doctor

echo ========================================================================
echo FOOTBALL V2.0 PRE-2025 SQLITE EXTRACTOR - DOCTOR
echo ========================================================================
echo.

where py >nul 2>nul
if not errorlevel 1 goto RUN_WITH_PY

where python >nul 2>nul
if errorlevel 1 goto NO_PYTHON

python -u doctor.py
set "RC=%ERRORLEVEL%"
goto FINISH

:RUN_WITH_PY
py -3 -u doctor.py
set "RC=%ERRORLEVEL%"
goto FINISH

:NO_PYTHON
echo FAIL: Python 3 was not found.
echo Install Python 3 and tick "Add Python to PATH".
set "RC=3"

:FINISH
echo.
echo ========================================================================
echo DOCTOR EXIT CODE: %RC%
echo ========================================================================
echo.
pause
exit /b %RC%
