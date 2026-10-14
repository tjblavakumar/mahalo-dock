@echo off
REM MAHALO3 - First-time setup (Windows)
REM Usage: First_Setup.bat
REM
REM This script:
REM   1. Creates Python venvs and installs dependencies for backend + mock services
REM   2. Installs Node.js dependencies for the frontend
REM   3. Copies .env.example to .env (if .env doesn't already exist)
REM
REM After running this, update the OPENAI_API_KEY in .env, then run start_all.bat.

setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

echo.
echo ============================================
echo   MAHALO3 - First-Time Setup
echo ============================================
echo.

REM --- Check prerequisites ---
echo [Prerequisites] Checking python and node...

python --version > NUL 2>&1
if errorlevel 1 (
    echo   ERROR: Python is not installed or not in PATH.
    echo   Please install Python 3.11+ and try again.
    pause
    exit /b 1
)

node --version > NUL 2>&1
if errorlevel 1 (
    echo   ERROR: Node.js is not installed or not in PATH.
    echo   Please install Node.js 20+ and try again.
    pause
    exit /b 1
)

echo   Python found: & python --version
echo   Node found:   & node --version
echo.

REM --- Backend venv ---
echo [1/5] Setting up Backend virtual environment...
cd /d "%PROJECT_DIR%\backend"
if exist venv (
    echo   venv already exists, skipping creation.
) else (
    python -m venv venv
    echo   venv created.
)
call venv\Scripts\activate.bat
pip install --upgrade pip > NUL 2>&1
pip install -r requirements.txt
call deactivate
echo   Backend setup complete.
echo.

REM --- Mock Jira venv ---
echo [2/5] Setting up Mock Jira virtual environment...
cd /d "%PROJECT_DIR%\mock-services\jira"
if exist venv (
    echo   venv already exists, skipping creation.
) else (
    python -m venv venv
    echo   venv created.
)
call venv\Scripts\activate.bat
pip install --upgrade pip > NUL 2>&1
pip install -r requirements.txt
call deactivate
echo   Mock Jira setup complete.
echo.

REM --- Mock Confluence venv ---
echo [3/5] Setting up Mock Confluence virtual environment...
cd /d "%PROJECT_DIR%\mock-services\confluence"
if exist venv (
    echo   venv already exists, skipping creation.
) else (
    python -m venv venv
    echo   venv created.
)
call venv\Scripts\activate.bat
pip install --upgrade pip > NUL 2>&1
pip install -r requirements.txt
call deactivate
echo   Mock Confluence setup complete.
echo.

REM --- Mock GitHub venv ---
echo [4/5] Setting up Mock GitHub virtual environment...
cd /d "%PROJECT_DIR%\mock-services\github"
if exist venv (
    echo   venv already exists, skipping creation.
) else (
    python -m venv venv
    echo   venv created.
)
call venv\Scripts\activate.bat
pip install --upgrade pip > NUL 2>&1
pip install -r requirements.txt
call deactivate
echo   Mock GitHub setup complete.
echo.

REM --- Frontend npm install ---
echo [5/5] Installing Frontend dependencies...
cd /d "%PROJECT_DIR%\frontend"
call npm install
echo   Frontend setup complete.
echo.

REM --- Create .env from .env.example ---
cd /d "%PROJECT_DIR%"
if exist .env (
    echo [.env] File already exists, skipping copy.
) else (
    copy .env.example .env > NUL
    echo [.env] Created .env from .env.example.
)

echo.
echo ============================================
echo   Setup complete!
echo ============================================
echo.
echo   NEXT STEPS:
echo     1. Open .env and set your OPENAI_API_KEY
echo     2. Run start_all.bat to launch all services
echo.

cd /d "%PROJECT_DIR%"
endlocal
pause
