#!/usr/bin/env bash
# Complete one-click setup script for Blender Image-to-3D Studio & MCP
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo "⚡ Blender Image-to-3D Studio - Initializing Setup"
echo "=========================================================="

# 1. Detect Python
UV_BIN="$HOME/.local/bin/uv"
if [ ! -f "$UV_BIN" ]; then
  if command -v uv &> /dev/null; then
    UV_BIN="uv"
  else
    echo "📦 Installing uv for ultra-fast environment management..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    UV_BIN="$HOME/.local/bin/uv"
  fi
fi

# 2. Main virtual environment
echo "🐍 Setting up main Python virtual environment (.venv)..."
if [ ! -d ".venv" ]; then
  "$UV_BIN" venv .venv --python 3.11
fi

echo "📦 Installing MCP server & Web Studio dependencies..."
"$UV_BIN" pip install -r requirements.txt --python .venv/bin/python
"$UV_BIN" pip install "mcp>=1.2.0,<2.0.0" --python .venv/bin/python

# 3. Third-party TripoSR setup
echo "🧠 Setting up TripoSR Neural Engine in third_party/TripoSR..."
mkdir -p third_party workspace/inputs workspace/outputs
if [ ! -d "third_party/TripoSR/.git" ]; then
  echo "Cloning TripoSR repository..."
  git clone https://github.com/VAST-AI-Research/TripoSR.git third_party/TripoSR
fi

if [ ! -d "third_party/TripoSR/.venv" ]; then
  echo "Creating TripoSR dedicated virtual environment..."
  "$UV_BIN" venv third_party/TripoSR/.venv --python 3.11
fi

echo "Installing PyTorch and TripoSR dependencies..."
"$UV_BIN" pip install torch torchvision --python third_party/TripoSR/.venv/bin/python
"$UV_BIN" pip install "omegaconf==2.3.0" "Pillow" "einops==0.7.0" "transformers==4.35.0" "trimesh" "rembg" "onnxruntime" "huggingface-hub" "imageio[ffmpeg]" "gradio" "xatlas" "moderngl" --python third_party/TripoSR/.venv/bin/python
"$UV_BIN" pip install scikit-build-core cmake pybind11 --python third_party/TripoSR/.venv/bin/python
"$UV_BIN" pip install --no-build-isolation "git+https://github.com/tatsy/torchmcubes.git" --python third_party/TripoSR/.venv/bin/python

# 4. Blender Bridge Add-on registration
BLENDER_ADDONS="$HOME/Library/Application Support/Blender/5.0/scripts/addons"
mkdir -p "$BLENDER_ADDONS"
echo "🔌 Installing Blender MCP bridge add-on..."
cp blender_addon/mcp_bridge.py "$BLENDER_ADDONS/mcp_bridge.py"

# Clean up any conflicting legacy addon if present
if [ -f "$BLENDER_ADDONS/addon.py" ]; then
  mv "$BLENDER_ADDONS/addon.py" "$BLENDER_ADDONS/addon.py.bak"
fi

if [ -f "/Applications/Blender.app/Contents/MacOS/Blender" ]; then
  echo "⚙️ Enabling mcp_bridge in Blender preferences..."
  /Applications/Blender.app/Contents/MacOS/Blender --background --python-expr "import bpy; bpy.ops.preferences.addon_enable(module='mcp_bridge'); bpy.ops.wm.save_userpref()" 2>/dev/null || true
fi

echo "=========================================================="
echo "🎉 Setup complete! You are ready to create 3D models!"
echo "• Start Web Studio:  ./start_studio.sh"
echo "• Launch Blender:    ./launch_blender.sh"
echo "• Run Diagnostics:   ./.venv/bin/python test_pipeline.py"
echo "=========================================================="
