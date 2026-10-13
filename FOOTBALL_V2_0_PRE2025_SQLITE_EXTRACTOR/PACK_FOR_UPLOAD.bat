@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Football V2.0 Package for Upload

echo ========================================================================
echo FOOTBALL V2.0 PACKAGE SQLITE FOR UPLOAD
echo ========================================================================
echo Creates ordered 400 MiB ZIP parts plus a SHA256 manifest.
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

python -u pack_for_upload.py
set "RC=%ERRORLEVEL%"
goto FINISH

:RUN_WITH_PY
py -3 -u pack_for_upload.py
set "RC=%ERRORLEVEL%"
goto FINISH

:NO_PYTHON
echo FAIL: Python 3 was not found.
set "RC=3"

:FINISH
echo.
echo ========================================================================
echo PACK EXIT CODE: %RC%
echo ========================================================================
if "%RC%"=="0" (
    echo Upload every file in the upload folder.
)
echo.
pause
exit /b %RC%
