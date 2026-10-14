#!/bin/bash
# MAHALO3 - Start all services (Linux/macOS)
# Usage: ./start_all.sh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDS_DIR="$PROJECT_DIR/.pids"
mkdir -p "$PIDS_DIR"

echo ""
echo "============================================"
echo "  MAHALO3 - Starting all services"
echo "============================================"
echo ""

# --- Mock Jira ---
echo "  [1/5] Starting Mock Jira on :5001..."
cd "$PROJECT_DIR/mock-services/jira"
if [ -f "venv/bin/activate" ]; then
  nohup bash -lc 'source venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 5001 > /dev/null 2>&1' >/dev/null 2>&1 &
else
  nohup uvicorn main:app --host 0.0.0.0 --port 5001 >/dev/null 2>&1 &
fi
sleep 2

# --- Mock Confluence ---
echo "  [2/5] Starting Mock Confluence on :5002..."
cd "$PROJECT_DIR/mock-services/confluence"
if [ -f "venv/bin/activate" ]; then
  nohup bash -lc 'source venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 5002 > /dev/null 2>&1' >/dev/null 2>&1 &
else
  nohup uvicorn main:app --host 0.0.0.0 --port 5002 >/dev/null 2>&1 &
fi
sleep 2

# --- Mock GitHub ---
echo "  [3/6] Starting Mock GitHub on :5003..."
cd "$PROJECT_DIR/mock-services/github"
if [ -f "venv/bin/activate" ]; then
  nohup bash -lc 'source venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 5003 > /dev/null 2>&1' >/dev/null 2>&1 &
else
  nohup uvicorn main:app --host 0.0.0.0 --port 5003 >/dev/null 2>&1 &
fi
sleep 2

# --- Mock ServiceNow ---
echo "  [4/6] Starting Mock ServiceNow on :5004..."
cd "$PROJECT_DIR/mock-services/servicenow"
if [ -f "venv/bin/activate" ]; then
  nohup bash -lc 'source venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 5004 > /dev/null 2>&1' >/dev/null 2>&1 &
else
  nohup uvicorn main:app --host 0.0.0.0 --port 5004 >/dev/null 2>&1 &
fi
sleep 2

# --- Backend ---
echo "  [5/6] Starting Backend on :8008..."
cd "$PROJECT_DIR/backend"
if [ -f "venv/bin/activate" ]; then
  nohup bash -lc 'source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8008 > /dev/null 2>&1' >/dev/null 2>&1 &
else
  nohup uvicorn app.main:app --host 0.0.0.0 --port 8008 >/dev/null 2>&1 &
fi
sleep 2

# --- Frontend ---
echo "  [6/6] Starting Frontend on :3000..."
cd "$PROJECT_DIR/frontend"
nohup env NEXT_PUBLIC_API_URL=http://localhost:8008 npm run dev >/dev/null 2>&1 &
sleep 3

echo ""
echo "============================================"
echo "  All services started!"
echo "============================================"
echo ""
echo "  Mock Jira:        http://localhost:5001"
echo "  Mock Confluence:  http://localhost:5002"
echo "  Mock GitHub:      http://localhost:5003"
echo "  Mock ServiceNow:  http://localhost:5004"
echo "  Backend:          http://localhost:8008"
echo "  Frontend:         http://localhost:3000"
echo ""
echo "  To stop all: ./stop_all.sh"
echo ""

cd "$PROJECT_DIR"
