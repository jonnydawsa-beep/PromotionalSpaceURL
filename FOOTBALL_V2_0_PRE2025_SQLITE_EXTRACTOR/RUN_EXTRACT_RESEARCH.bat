@echo off
setlocal EnableExtensions
cd /d "%~dp0"

start "Football V2.0 Pre-2025 Extractor" "%ComSpec%" /k ""%~dp0RUN_EXTRACT_RESEARCH_INNER.cmd""
exit /b 0
