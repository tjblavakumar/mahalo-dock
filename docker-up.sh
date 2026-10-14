#!/usr/bin/env bash
# MAHALO-dock — bring up the full Dockerized stack (Linux / macOS).
#
# Usage:
#   ./docker-up.sh              # real mode (Gitea-backed), builds + starts, detached
#   ./docker-up.sh mock         # offline mock mode (no Gitea)
#   ./docker-up.sh --foreground # run in the foreground (stream logs)
#
# Canonical path is plain `docker compose up` — this is just a convenience wrapper.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "No .env found — copying .env.example to .env (edit it to add your LLM keys)."
  cp .env.example .env
fi

MODE="real"
DETACH="-d"
for arg in "$@"; do
  case "$arg" in
    mock) MODE="mock" ;;
    --foreground|-f) DETACH="" ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [ "$MODE" = "mock" ]; then
  echo "Starting MAHALO-dock in OFFLINE MOCK mode (no Gitea)..."
  exec docker compose -f docker-compose.yml -f docker-compose.mock.yml up --build $DETACH \
    backend frontend mock-jira mock-confluence mock-github mock-servicenow
else
  echo "Starting MAHALO-dock in REAL mode (Gitea-backed)..."
  exec docker compose up --build $DETACH
fi
