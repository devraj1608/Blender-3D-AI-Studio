# Blender 3D AI Studio

> **Transform 2D images into high-fidelity 3D models directly inside Blender with dual neural pipelines, local Vision LLM intelligence, and live studio viewport sync.**

---

## 🌟 Overview & Architecture

**Blender 3D AI Studio** bridges cutting-edge generative 3D diffusion and neural reconstruction directly with Blender 5.0 / 4.x. It offers an end-to-end studio workflow: upload or drop any 2D reference image, synthesize high-resolution 3D geometry with PBR textures, polish the mesh with photorealistic studio lighting and true-to-image color calibration, and view the interactive model in WebGL or Blender in real time.

```
       [ Input Image ] (PNG / JPG / WebP)
             │
             ├──► [ Modern Web Studio UI ] (http://127.0.0.1:8000) ──► Interactive WebGL Viewer
             │           │
             ├──► [ FastMCP Server ] ──► (LM Studio / Claude Desktop / Cursor / AI Agents)
             │           │
             ▼           ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                  DUAL 3D SYNTHESIS PIPELINE                 │
   │                                                             │
   │  [ Option 1: Microsoft TRELLIS ]   [ Option 2: TripoSR ]   │
   │  • High-Fidelity 3D Diffusion       • Fast Neural Meshing   │
   │  • PBR Material Maps (ZeroGPU)      • 100% Offline (CPU)    │
   │  • Sharp Limbs & Separate Geometry  • Camera UV Projection  │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
      [ Blender 5.0 Socket Bridge ] (Port 9876)
      • Automated .GLB import, normalization & grounding
      • Weighted normals, smooth shading & subsurf polish
      • True-color calibration (sRGB Standard + Hue/Sat Boost)
      • 3-point neutral studio photography lighting
      • Real-time EEVEE Next viewport snapshot & binary GLB export
                                  │
                                  ▼
      [ Local Vision LLM ] (Ollama + Qwen2.5-VL)
      • Semantic shape, proportion, and color breakdown
      • 3D render quality inspection and defect critique
```

---

## ✨ Features

- **Dual 3D Synthesis Engines**:
  - **🌟 Mode 1: Microsoft TRELLIS Foundation Model**: Generates complex, high-fidelity 3D meshes with detailed geometry, articulated limbs, and PBR textures via NVIDIA A100 ZeroGPU.
  - **⚡ Mode 2: TripoSR Neural Model**: Runs 100% locally and completely offline directly on your Mac or PC CPU. Zero cloud dependency, zero external API costs, complete privacy.
- **🎨 Exact Color Calibration & True-to-Image Reproduction**:
  - **Standard sRGB Color Management**: Eliminates AgX highlight desaturation and clipping in Blender.
  - **Neutral Studio Lighting**: Pure white balanced lights prevent color tinting and highlight glare.
  - **Automated PBR Vibrancy Boost**: Injects shader saturation and value compensation to match vibrant 2D reference artwork.
  - **Camera UV Image Projection**: Projects high-resolution reference pixels directly onto the front mesh surface with seamless falloff into detected dominant RGB colors.
- **🖥️ Luxury Web Studio UI (`http://127.0.0.1:8000`)**:
  - Modern dark luxury glassmorphism workbench.
  - Drag-and-drop file upload, file browsing, and clipboard paste (`Cmd + V` / `Ctrl + V`).
  - Interactive `<model-viewer>` with neutral tone-mapping, orbit controls, camera snapping (`Front`, `Side`, `Top`, `3/4 View`), auto-rotation, and instant `.GLB` download.
  - Live Blender controls: *Clear Scene*, *Studio Viewport Render Snapshot*, *Rotate 90°*.
- **🔑 Hugging Face Token Persistence**:
  - Enter your free Hugging Face token in the UI once; it is saved permanently to `.env` (`HF_TOKEN=...`) for priority ZeroGPU compute.
- **🤖 FastMCP Standards-Compliant Bridge**:
  - Connects seamlessly to AI agent harnesses (Claude Desktop, LM Studio, Cursor, Antigravity).

---

## 📁 Repository Structure

```
Blender-3D-AI-Studio/
├── README.md                 # Project documentation & usage guide
├── requirements.txt          # MCP server & Web Studio Python dependencies
├── .env.example              # Sample environment configuration
├── web_app.py                # FastAPI backend & Studio web server
├── launch_blender.sh         # One-click launcher for Blender + Bridge (macOS/Linux)
├── launch_blender.bat        # One-click launcher for Blender + Bridge (Windows)
├── start_studio.sh           # One-click launcher for the Web Studio (macOS/Linux)
├── start_studio.bat          # One-click launcher for the Web Studio (Windows)
├── setup.sh                  # Complete environment setup script
├── test_pipeline.py          # Diagnostic verification script
├── blender_addon/
│   └── mcp_bridge.py         # Blender 5.0 / 4.x add-on socket server
├── mcp_server/
│   ├── server.py             # FastMCP tools & entry point
│   ├── blender_client.py     # Socket client talking to Blender bridge
│   ├── config.py             # Central path, port & runtime settings
│   └── backends/
│       ├── __init__.py
│       ├── trellis.py        # TRELLIS ZeroGPU Gradio 5 adapter
│       ├── triposr.py        # TripoSR local neural reconstruction wrapper
│       └── vlm.py            # Local vision model Ollama client
├── web_ui/
│   └── index.html            # Luxury dark studio web interface
└── workspace/
    ├── inputs/               # Uploaded reference images (git ignored)
    └── outputs/              # Generated 3D models & snapshots (git ignored)
```

---

## 🚀 Quick Start

### 1. Prerequisites
- **Blender 4.0+ or 5.0+** installed on your system.
- **Python 3.10+**.
- *(Optional)* **Ollama** with `qwen2.5vl:3b` or `qwen2.5vl:7b` for local Vision AI.
- *(Optional)* Free **Hugging Face Token** for priority TRELLIS GPU compute ([get one here](https://huggingface.co/settings/tokens)).

### 2. Installation

Clone the repository and install dependencies:
```bash
git clone https://github.com/devraj1608/Blender-3D-AI-Studio.git
cd Blender-3D-AI-Studio

# Create virtual environment and install packages
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Launching the Studio

#### Step 1: Start Blender with the Socket Bridge
In your first terminal:
```bash
# macOS / Linux
./launch_blender.sh

# Windows
launch_blender.bat
```
*Blender will open and automatically start the MCP socket bridge listening on `127.0.0.1:9876`.*

#### Step 2: Start the Web Studio
In your second terminal:
```bash
# macOS / Linux
./start_studio.sh

# Windows
start_studio.bat
```
*Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.*

---

## 🎨 How to Use

1. **Upload an Image**:
   - Drag and drop your image into the drop zone, browse from your computer, or press `Cmd + V` / `Ctrl + V` to paste a screenshot.
2. **Choose Your 3D Engine**:
   - **🌟 TRELLIS Diffusion (Cloud A100)**: Best for complex characters, separated limbs, and detailed PBR textures.
   - **⚡ TripoSR Neural (100% Offline)**: Instant watertight mesh running on your local Mac/PC CPU.
3. **Configure Hugging Face Token (Optional for TRELLIS)**:
   - Click the **🔑 HF Token** button in the header, paste your token, and click **Save to .env**.
4. **Generate**:
   - Click **Generate 3D Model**.
   - Watch the real-time progress timeline as the Vision LLM analyzes proportions, the 3D geometry synthesizes, Blender applies mesh polish and true-color calibration, and the model renders in your interactive viewport.
5. **Inspect & Export**:
   - Rotate, pan, and zoom in the WebGL viewport.
   - Use the camera buttons (`Front`, `Side`, `Top`, `3/4`) or click **⬇️ Download .GLB**.
   - Check Blender to see the model fully loaded and ready for rigging, sculpting, or animation!

---

## 🔌 Connecting via MCP (AI Agents & LLMs)

Add the MCP server to your MCP configuration (e.g. `claude_desktop_config.json`, LM Studio, or Cursor):

```json
{
  "mcpServers": {
    "blender-3d-studio": {
      "command": "/path/to/Blender-3D-AI-Studio/.venv/bin/python",
      "args": ["/path/to/Blender-3D-AI-Studio/mcp_server/server.py"],
      "env": {
        "HF_TOKEN": "your_hugging_face_token_here",
        "VLM_MODEL": "qwen2.5vl:3b"
      }
    }
  }
}
```

Available MCP Tools:
- `generate_3d_from_image`: Generates a 3D model from an image and syncs to Blender.
- `render_preview`: Captures high-res viewport render from Blender camera.
- `clear_scene`: Cleans the Blender scene.
- `execute_blender_code`: Executes custom Python scripts inside Blender live.

---

## 🛠️ Diagnostics & Self-Test

Verify your system setup at any time:
```bash
./.venv/bin/python test_pipeline.py
```

---

## 📜 License

- Blender: GNU General Public License (GPL)
- TripoSR: MIT License
- TRELLIS: Apache 2.0 / MIT License
- FastMCP: MIT License
