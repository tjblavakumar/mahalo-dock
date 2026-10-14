@echo off
REM MAHALO-dock - bring up the full Dockerized stack (Windows 11, Docker Desktop).
REM
REM Usage:
REM   docker-up.bat          Real mode (Gitea-backed), builds + starts, detached
REM   docker-up.bat mock     Offline mock mode (no Gitea)
REM
REM Canonical path is plain "docker compose up" - this is just a convenience wrapper.
setlocal
cd /d "%~dp0"

if not exist .env (
  echo No .env found - copying .env.example to .env ^(edit it to add your LLM keys^).
  copy /y .env.example .env >nul
)

if /i "%1"=="mock" (
  echo Starting MAHALO-dock in OFFLINE MOCK mode ^(no Gitea^)...
  docker compose -f docker-compose.yml -f docker-compose.mock.yml up --build -d backend frontend mock-jira mock-confluence mock-github mock-servicenow
) else (
  echo Starting MAHALO-dock in REAL mode ^(Gitea-backed^)...
  docker compose up --build -d
)

endlocal
