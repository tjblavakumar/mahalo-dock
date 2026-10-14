@echo off
REM MAHALO-dock - stop the Dockerized stack (Windows 11, Docker Desktop).
REM
REM Usage:
REM   docker-down.bat          Stop + remove containers (keeps Gitea data)
REM   docker-down.bat --wipe   Also remove volumes (fresh Gitea on next up)
setlocal
cd /d "%~dp0"

if /i "%1"=="--wipe" (
  echo Stopping MAHALO-dock and removing volumes ^(Gitea data will be wiped^)...
  docker compose down -v
) else (
  echo Stopping MAHALO-dock ^(Gitea data preserved^)...
  docker compose down
)

endlocal
