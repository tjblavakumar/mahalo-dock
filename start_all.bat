@echo off
REM MAHALO3 - Start all services (Windows)
REM Usage: start_all.bat

setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"
REM Remove trailing backslash
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

set "PIDS_DIR=%PROJECT_DIR%\.pids"
if not exist "%PIDS_DIR%" mkdir "%PIDS_DIR%"

echo.
echo ============================================
echo   MAHALO3 - Starting all services
echo ============================================
echo.

REM --- Mock Jira ---
echo   [1/5] Starting Mock Jira on :5001...
cd /d "%PROJECT_DIR%\mock-services\jira"
if exist venv\Scripts\activate.bat (
    start "" /B cmd /c "call venv\Scripts\activate.bat && uvicorn main:app --host 0.0.0.0 --port 5001 > NUL 2>&1"
) else (
    start "" /B uvicorn main:app --host 0.0.0.0 --port 5001 > NUL 2>&1
)
timeout /t 2 /nobreak > NUL

REM --- Mock Confluence ---
echo   [2/5] Starting Mock Confluence on :5002...
cd /d "%PROJECT_DIR%\mock-services\confluence"
if exist venv\Scripts\activate.bat (
    start "" /B cmd /c "call venv\Scripts\activate.bat && uvicorn main:app --host 0.0.0.0 --port 5002 > NUL 2>&1"
) else (
    start "" /B uvicorn main:app --host 0.0.0.0 --port 5002 > NUL 2>&1
)
timeout /t 2 /nobreak > NUL

REM --- Mock GitHub ---
echo   [3/6] Starting Mock GitHub on :5003...
cd /d "%PROJECT_DIR%\mock-services\github"
if exist venv\Scripts\activate.bat (
    start "" /B cmd /c "call venv\Scripts\activate.bat && uvicorn main:app --host 0.0.0.0 --port 5003 > NUL 2>&1"
) else (
    start "" /B uvicorn main:app --host 0.0.0.0 --port 5003 > NUL 2>&1
)
timeout /t 2 /nobreak > NUL

REM --- Mock ServiceNow ---
echo   [4/6] Starting Mock ServiceNow on :5004...
cd /d "%PROJECT_DIR%\mock-services\servicenow"
if exist venv\Scripts\activate.bat (
    start "" /B cmd /c "call venv\Scripts\activate.bat && uvicorn main:app --host 0.0.0.0 --port 5004 > NUL 2>&1"
) else (
    start "" /B uvicorn main:app --host 0.0.0.0 --port 5004 > NUL 2>&1
)
timeout /t 2 /nobreak > NUL

REM --- Backend ---
echo   [5/6] Starting Backend on :8008...
cd /d "%PROJECT_DIR%\backend"
if exist venv\Scripts\activate.bat (
    start "" /B cmd /c "call venv\Scripts\activate.bat && uvicorn app.main:app --host 0.0.0.0 --port 8008 > NUL 2>&1"
) else (
    start "" /B uvicorn app.main:app --host 0.0.0.0 --port 8008 > NUL 2>&1
)
timeout /t 2 /nobreak > NUL

REM --- Frontend ---
echo   [6/6] Starting Frontend on :3000...
cd /d "%PROJECT_DIR%\frontend"
start "" /B cmd /c "set NEXT_PUBLIC_API_URL=http://localhost:8008&& npm run dev > NUL 2>&1"
timeout /t 3 /nobreak > NUL

echo.
echo ============================================
echo   All services started!
echo ============================================
echo.
echo   Mock Jira:        http://localhost:5001
echo   Mock Confluence:  http://localhost:5002
echo   Mock GitHub:      http://localhost:5003
echo   Mock ServiceNow:  http://localhost:5004
echo   Backend:          http://localhost:8008
echo   Frontend:         http://localhost:3000
echo.
echo   To stop all: stop_all.bat
echo.

cd /d "%PROJECT_DIR%"
endlocal
