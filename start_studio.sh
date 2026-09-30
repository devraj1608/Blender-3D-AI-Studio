#!/usr/bin/env bash
# Start the Blender Image-to-3D Web Studio & API server
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
else
  echo "❌ Error: Virtual environment .venv not found. Run ./setup.sh first."
  exit 1
fi

PORT="${PORT:-8000}"

# Auto-cleanup any old/stale process on the same port
OLD_PID=$(lsof -ti :"$PORT" -sTCP:LISTEN 2>/dev/null || true)
if [ -n "$OLD_PID" ]; then
  echo "⚠️ Port $PORT is already in use by PID $OLD_PID. Stopping previous instance..."
  kill -9 $OLD_PID 2>/dev/null || true
  sleep 1
fi

echo "=========================================================="
echo "🚀 Blender Image-to-3D Studio"
echo "=========================================================="
echo "• Web Studio UI:  http://127.0.0.1:$PORT"
echo "• Blender Bridge: 127.0.0.1:9876"
echo "• TripoSR Device: ${TRIPOSR_DEVICE:-cpu}"
echo "=========================================================="
echo "Opening Web Studio in your browser..."

# Open browser on macOS
if command -v open &> /dev/null; then
  (sleep 1 && open "http://127.0.0.1:$PORT") &
fi

exec python web_app.py
