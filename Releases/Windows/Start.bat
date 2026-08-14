@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title XMaoMusic OffsetEditor - Startup

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1"
set "START_EXIT_CODE=%ERRORLEVEL%"

if not "%START_EXIT_CODE%"=="0" (
    echo.
    echo Startup failed. Review the message above, then press any key to close.
    pause >nul
)

exit /b %START_EXIT_CODE%
