@echo off
REM MAHALO3 - Stop all services (Windows)
REM Usage: stop_all.bat

setlocal enabledelayedexpansion

echo.
echo ============================================
echo   MAHALO3 - Stopping all services
echo ============================================
echo.

REM Kill processes on each known port
call :kill_port 5001 "Mock Jira"
call :kill_port 5002 "Mock Confluence"
call :kill_port 5003 "Mock GitHub"
call :kill_port 5004 "Mock ServiceNow"
call :kill_port 8008 "Backend"
call :kill_port 3000 "Frontend"

REM Clean up .pids directory if it exists
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
if exist "%PROJECT_DIR%\.pids" rmdir /s /q "%PROJECT_DIR%\.pids"

echo.
echo ============================================
echo   All services stopped.
echo ============================================
echo.

endlocal
goto :eof

REM --- Subroutine: kill processes on a given port ---
:kill_port
set "PORT=%~1"
set "SERVICE_NAME=%~2"

REM Find PID(s) listening on the port
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":%PORT% "') do (
    set "PID=%%a"
    if not "!PID!"=="0" (
        taskkill /PID !PID! /F > NUL 2>&1
        if !errorlevel! equ 0 (
            echo   Stopped %SERVICE_NAME% ^(PID !PID!^) on port %PORT%
        )
    )
)
goto :eof
