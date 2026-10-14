#!/bin/bash
# MAHALO3 - Stop all services (Linux/macOS)
# Usage: ./stop_all.sh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDS_DIR="$PROJECT_DIR/.pids"

echo ""
echo "============================================"
echo "  MAHALO3 - Stopping all services"
echo "============================================"
echo ""

kill_port() {
    local port="$1"
    local service_name="$2"

    local pids
    pids=$(lsof -ti tcp:"$port" 2>/dev/null || ss -ltnp "sport = :$port" 2>/dev/null | awk 'NR>1 {print $NF}' | sed -E 's/.*pid=([0-9]+).*/\1/' || true)

    if [ -n "$pids" ]; then
        for pid in $pids; do
            if [ -n "$pid" ] && [ "$pid" != "" ]; then
                kill -9 "$pid" 2>/dev/null || true
                echo "  Stopped $service_name (PID $pid) on port $port"
            fi
        done
    fi
}

kill_port 5001 "Mock Jira"
kill_port 5002 "Mock Confluence"
kill_port 5003 "Mock GitHub"
kill_port 5004 "Mock ServiceNow"
kill_port 8008 "Backend"
kill_port 3000 "Frontend"

if [ -d "$PIDS_DIR" ]; then
    rm -rf "$PIDS_DIR"
fi

echo ""
echo "============================================"
echo "  All services stopped."
echo "============================================"
echo ""
