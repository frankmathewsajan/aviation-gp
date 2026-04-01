#!/bin/bash
# GreenPath — Start both backend and frontend

echo "🌍 Starting GreenPath..."

# Install backend dependencies
echo "📦 Installing backend dependencies..."
cd backend && pip install -r requirements.txt &
PID_BACKEND_INSTALL=$!

# Install frontend dependencies
echo "📦 Installing frontend dependencies..."
cd frontend && npm install &
PID_FRONTEND_INSTALL=$!

# Wait for installs
wait $PID_BACKEND_INSTALL
wait $PID_FRONTEND_INSTALL

echo "✅ Dependencies installed"

# Start backend
echo "🚀 Starting backend on port 8000..."
cd backend && uvicorn main:app --reload --port 8000 &

# Start frontend
echo "🚀 Starting frontend on port 3000..."
cd frontend && npm run dev &

echo ""
echo "═══════════════════════════════════════"
echo "  GreenPath is running!"
echo "  Frontend: http://localhost:3000"
echo "  Backend:  http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo "═══════════════════════════════════════"
echo ""

wait
