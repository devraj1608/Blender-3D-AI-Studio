import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
WORKSPACE = ROOT / "workspace"
INPUTS = WORKSPACE / "inputs"
OUTPUTS = WORKSPACE / "outputs"

INPUTS.mkdir(parents=True, exist_ok=True)
OUTPUTS.mkdir(parents=True, exist_ok=True)

# Blender socket bridge
BLENDER_HOST = os.getenv("BLENDER_HOST", "127.0.0.1")
BLENDER_PORT = int(os.getenv("BLENDER_PORT", "9876"))

# TripoSR image-to-3D configuration
TRIPOSR_DIR = Path(os.getenv("TRIPOSR_DIR", ROOT / "third_party" / "TripoSR"))
_venv_py = TRIPOSR_DIR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
TRIPOSR_PYTHON = os.getenv("TRIPOSR_PYTHON", str(_venv_py))
TRIPOSR_DEVICE = os.getenv("TRIPOSR_DEVICE", "cpu")   # "cuda:0", "mps", or "cpu"
TRIPOSR_TIMEOUT = int(os.getenv("TRIPOSR_TIMEOUT", "1800"))

# Ollama local vision model
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
VLM_MODEL = os.getenv("VLM_MODEL", "qwen2.5vl:7b")
