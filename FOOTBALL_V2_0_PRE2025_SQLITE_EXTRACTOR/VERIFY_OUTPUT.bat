@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Football V2.0 SQLite Output Verification

echo ========================================================================
echo FOOTBALL V2.0 SQLITE OUTPUT VERIFICATION
echo ========================================================================
echo.

if not exist "output\research_pre2025.sqlite3" (
    echo FAIL: output\research_pre2025.sqlite3 does not exist.
    set "RC=2"
    goto FINISH
)

where py >nul 2>nul
if not errorlevel 1 goto RUN_WITH_PY

where python >nul 2>nul
if errorlevel 1 goto NO_PYTHON

python -u extract_research.py --verify "output\research_pre2025.sqlite3"
set "RC=%ERRORLEVEL%"
goto FINISH

:RUN_WITH_PY
py -3 -u extract_research.py --verify "output\research_pre2025.sqlite3"
set "RC=%ERRORLEVEL%"
goto FINISH

:NO_PYTHON
echo FAIL: Python 3 was not found.
set "RC=3"

:FINISH
echo.
echo ========================================================================
echo VERIFY EXIT CODE: %RC%
echo ========================================================================
echo.
pause
exit /b %RC%
