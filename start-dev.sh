#!/bin/bash
# ASIC Scan Tool - Development Mode Launcher (Linux/macOS)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================"
echo "  ASIC Scan Tool - Starting Development Mode"
echo "============================================"
echo ""

# Start Python backend in background
echo "[1/2] Starting Python backend on port 8765..."
cd "$SCRIPT_DIR/backend"
python3 main.py &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Wait for backend to start
sleep 3

# Start Vite dev server
echo "[2/2] Starting Vite frontend on port 5173..."
cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Services running:"
echo "  Backend:  http://127.0.0.1:8765"
echo "  Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait and cleanup on exit
trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
