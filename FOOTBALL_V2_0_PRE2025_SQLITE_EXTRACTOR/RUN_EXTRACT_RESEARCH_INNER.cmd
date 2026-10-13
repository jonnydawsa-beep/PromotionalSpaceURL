@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Football V2.0 Pre-2025 SQLite Extractor

echo ========================================================================
echo FOOTBALL V2.0 PRE-2025 SQLITE EXTRACTOR
echo ========================================================================
echo Reads: 2015.tar through 2024.tar only
echo Does NOT inspect: 2025.tar or 2026.tar
echo Output: output\research_pre2025.sqlite3
echo ========================================================================
echo.

set "RAWDIR=C:\BetfairMultiSport\Football\raw"

if exist "!RAWDIR!\2015.tar" goto HAVE_SOURCE

echo Default source folder was not found:
echo   !RAWDIR!
echo.
set /p "RAWDIR=Paste the folder containing 2015.tar through 2024.tar: "

:HAVE_SOURCE
for %%Y in (2015 2016 2017 2018 2019 2020 2021 2022 2023 2024) do (
    if not exist "!RAWDIR!\%%Y.tar" (
        echo.
        echo FAIL: Missing required source:
        echo   !RAWDIR!\%%Y.tar
        echo.
        goto SOURCE_FAIL
    )
)

echo Source folder:
echo   !RAWDIR!
echo.
echo Starting extraction. Progress will be shown live and written to:
echo   logs\extract_latest.log
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_extract.ps1" -RawDir "!RAWDIR!"
set "RC=!ERRORLEVEL!"
goto FINISH

:SOURCE_FAIL
set "RC=2"

:FINISH
echo.
echo ========================================================================
echo EXTRACTION EXIT CODE: !RC!
echo ========================================================================
if "!RC!"=="0" (
    echo SUCCESS
    echo.
    echo Next run:
    echo   VERIFY_OUTPUT.bat
    echo.
    echo Then upload these if size permits:
    echo   output\research_pre2025.sqlite3
    echo   output\extraction_report.json
) else (
    echo FAILED
    echo.
    echo Send this file back for diagnosis:
    echo   logs\extract_latest.log
)
echo.
pause
exit /b !RC!
