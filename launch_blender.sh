#!/usr/bin/env bash
# Universal Cross-Platform Blender Launcher (macOS, Linux, Windows/Git Bash)
# Launches Blender and starts the Image3D MCP Bridge on 127.0.0.1:9876
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_SCRIPT="$SCRIPT_DIR/blender_addon/mcp_bridge.py"
OS_TYPE="$(uname -s)"
BLENDER_BIN=""

echo "=========================================================="
echo "🎨 Blender Image-to-3D Bridge Launcher"
echo "• OS Detected: $OS_TYPE"
echo "• Bridge Script: $BRIDGE_SCRIPT"
echo "=========================================================="

# 1. macOS Detection
if [ "$OS_TYPE" = "Darwin" ]; then
  if [ -f "/Applications/Blender.app/Contents/MacOS/Blender" ]; then
    BLENDER_BIN="/Applications/Blender.app/Contents/MacOS/Blender"
  elif [ -f "$HOME/Applications/Blender.app/Contents/MacOS/Blender" ]; then
    BLENDER_BIN="$HOME/Applications/Blender.app/Contents/MacOS/Blender"
  elif command -v blender &> /dev/null; then
    BLENDER_BIN="$(command -v blender)"
  fi

# 2. Linux Detection
elif [ "$OS_TYPE" = "Linux" ]; then
  if command -v blender &> /dev/null; then
    BLENDER_BIN="$(command -v blender)"
  elif [ -f "/usr/bin/blender" ]; then
    BLENDER_BIN="/usr/bin/blender"
  elif [ -f "/snap/bin/blender" ]; then
    BLENDER_BIN="/snap/bin/blender"
  elif [ -f "/usr/local/bin/blender" ]; then
    BLENDER_BIN="/usr/local/bin/blender"
  elif command -v flatpak &> /dev/null && flatpak info org.blender.Blender &> /dev/null; then
    BLENDER_BIN="flatpak_blender"
  fi

# 3. Windows (Git Bash / MSYS / CYGWIN) Detection
elif [[ "$OS_TYPE" == *"MINGW"* ]] || [[ "$OS_TYPE" == *"CYGWIN"* ]] || [[ "$OS_TYPE" == *"MSYS"* ]]; then
  WIN_BLENDER=$(find "/c/Program Files/Blender Foundation" -maxdepth 2 -name "blender.exe" 2>/dev/null | sort -V | tail -n 1 || true)
  if [ -n "$WIN_BLENDER" ] && [ -f "$WIN_BLENDER" ]; then
    BLENDER_BIN="$WIN_BLENDER"
  elif command -v blender &> /dev/null; then
    BLENDER_BIN="$(command -v blender)"
  fi
fi

# Fallback: check PATH
if [ -z "$BLENDER_BIN" ] && command -v blender &> /dev/null; then
  BLENDER_BIN="$(command -v blender)"
fi

if [ -z "$BLENDER_BIN" ]; then
  echo "❌ Error: Could not locate Blender automatically."
  echo ""
  echo "Please ensure Blender is installed on your system:"
  echo "• macOS: Download from https://www.blender.org/download/ (Install to /Applications)"
  echo "• Linux: sudo apt install blender  OR  sudo snap install blender --classic"
  echo "• Windows: Install from https://www.blender.org/download/"
  echo ""
  echo "Alternatively, open Blender manually, go to the 'Scripting' workspace, open:"
  echo "  $BRIDGE_SCRIPT"
  echo "and click the 'Run Script' button (▶️)."
  exit 1
fi

echo "🚀 Found Blender at: $BLENDER_BIN"
echo "🔌 Starting Blender with Image3D Bridge listening on 127.0.0.1:9876..."

if [ "$BLENDER_BIN" = "flatpak_blender" ]; then
  flatpak run org.blender.Blender --python "$BRIDGE_SCRIPT" &
elif [ "$OS_TYPE" = "Darwin" ]; then
  # On macOS, launch GUI with python script passed directly
  "$BLENDER_BIN" --python "$BRIDGE_SCRIPT" &
else
  "$BLENDER_BIN" --python "$BRIDGE_SCRIPT" &
fi

echo "✅ Blender launched! Bridge listening on port 9876."
