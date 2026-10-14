#!/usr/bin/env bash
# MAHALO-dock — stop the Dockerized stack (Linux / macOS).
#
# Usage:
#   ./docker-down.sh        # stop + remove containers (keeps Gitea data)
#   ./docker-down.sh --wipe # also remove volumes (fresh Gitea on next up)
set -euo pipefail
cd "$(dirname "$0")"

if [ "${1:-}" = "--wipe" ]; then
  echo "Stopping MAHALO-dock and removing volumes (Gitea data will be wiped)..."
  exec docker compose down -v
fi
echo "Stopping MAHALO-dock (Gitea data preserved)..."
exec docker compose down
