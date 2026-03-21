#!/bin/bash

# Define project root
# Define project root
# Uses the first argument or defaults to current directory
PROJECT_ROOT="${1:-$(pwd)}"

if [ ! -d "$PROJECT_ROOT/server" ]; then
    echo "❌ Error: Invalid Project Root: $PROJECT_ROOT"
    echo "   Missing 'server' directory. Please provide the correct path." 
    echo "   Usage: $0 <path_to_bim_planner_root>"
    exit 1
fi

# Check if concurrently is installed, if not, offer to run raw or install
# For now, we use a simple trap-based background job approach to avoid npm dependencies for the shell script itself.

echo "🚀 Starting BIM Planner Development Environment..."

# Function to kill background processes on exit
cleanup() {
    echo "Stopping servers..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit
}

trap cleanup SIGINT SIGTERM

# Start Backend
cd "$PROJECT_ROOT/server" || exit
echo "📦 Starting Backend..."
npm run dev &
BACKEND_PID=$!

# Start Frontend
cd "$PROJECT_ROOT" || exit
echo "🎨 Starting Frontend..."
npm run dev &
FRONTEND_PID=$!

echo "✅ Environment is up!"
echo "   - Frontend: http://localhost:5173"
echo "   - Backend:  http://localhost:3000"
echo "Press Ctrl+C to stop."

wait
