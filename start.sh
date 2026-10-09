#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# NexusAI Trading Platform — Local Development Startup
# ─────────────────────────────────────────────────────────────────────────────
set -e

echo ""
echo "  ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗ █████╗ ██╗"
echo "  ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝██╔══██╗██║"
echo "  ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗███████║██║"
echo "  ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║██╔══██║██║"
echo "  ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║██║  ██║██║"
echo "  ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝"
echo ""
echo "  Multi-Agent AI Trading Platform — Paper Trading Mode"
echo "─────────────────────────────────────────────────────────────────────────"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3.11+ required. Install from python.org"
    exit 1
fi

# Check Node
if ! command -v node &> /dev/null; then
    echo "❌ Node.js 20+ required. Install from nodejs.org"
    exit 1
fi

# Backend setup
echo ""
echo "📦 Setting up Python backend..."
cd backend

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

echo "✅ Backend dependencies installed"

# Start backend in background
echo ""
echo "🚀 Starting FastAPI backend on http://localhost:8000..."
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"

# Wait for backend to be ready
echo "   Waiting for backend..."
for i in {1..20}; do
    if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "✅ Backend is ready"
        break
    fi
    sleep 1
done

# Frontend setup
cd ../frontend
echo ""
echo "📦 Setting up React frontend..."
npm install --silent

echo ""
echo "🚀 Starting React dashboard on http://localhost:3000..."
npm run dev &
FRONTEND_PID=$!

echo ""
echo "─────────────────────────────────────────────────────────────────────────"
echo "✅ NexusAI Platform is running!"
echo ""
echo "  Dashboard:  http://localhost:3000"
echo "  API Docs:   http://localhost:8000/docs"
echo "  WebSocket:  ws://localhost:8000/ws"
echo ""
echo "  Kill switch: POST http://localhost:8000/api/controls/kill-switch"
echo ""
echo "  Press Ctrl+C to stop all services"
echo "─────────────────────────────────────────────────────────────────────────"

# Cleanup on exit
cleanup() {
    echo ""
    echo "Stopping services..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo "✅ All services stopped"
    exit 0
}
trap cleanup SIGINT SIGTERM

wait
