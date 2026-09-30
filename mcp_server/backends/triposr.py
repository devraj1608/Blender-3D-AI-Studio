import os
import subprocess
import time
import logging
from pathlib import Path
import numpy as np

try:
    from ..config import (
        TRIPOSR_DIR,
        TRIPOSR_PYTHON,
        TRIPOSR_DEVICE,
        TRIPOSR_TIMEOUT,
        OUTPUTS,
    )
except (ImportError, ValueError):
    try:
        from mcp_server.config import (
            TRIPOSR_DIR,
            TRIPOSR_PYTHON,
            TRIPOSR_DEVICE,
            TRIPOSR_TIMEOUT,
            OUTPUTS,
        )
    except ImportError:
        from config import (
            TRIPOSR_DIR,
            TRIPOSR_PYTHON,
            TRIPOSR_DEVICE,
            TRIPOSR_TIMEOUT,
            OUTPUTS,
        )

logger = logging.getLogger("studio.triposr")


def reorient_upright(glb_path: str) -> None:
    """
    Reorient TripoSR mesh from (+Z up, +X back) to glTF 2.0 standard (+Y up).
    Runs using TripoSR python venv which has trimesh installed.
    """
    reorient_script = f"""
import trimesh, numpy as np
scene = trimesh.load('{glb_path}')
R = trimesh.transformations.rotation_matrix(np.radians(-90), [1, 0, 0])
scene.apply_transform(R)
scene.export('{glb_path}')
"""
    try:
        subprocess.run(
            [str(TRIPOSR_PYTHON), "-c", reorient_script],
            capture_output=True,
            text=True,
            timeout=15,
            check=True
        )
        logger.info(f"🔄 [TripoSR] Reoriented mesh {Path(glb_path).name} to glTF 2.0 upright (+Y up)")
    except Exception as e:
        logger.warning(f"⚠️ [TripoSR] Reorient fallback: {e}")


def run(
    image_path: str,
    mc_resolution: int = 256,
    no_remove_bg: bool = False,
    bake_texture: bool = False,
    foreground_ratio: float = 0.88,
    reorient: bool = True,
) -> str:
    """
    Run local neural 3D reconstruction using TripoSR.
    Runs 100% offline on local device.
    """
    img = Path(image_path).expanduser().resolve()
    if not img.is_file():
        raise FileNotFoundError(f"Image file not found: {img}")
    if not Path(TRIPOSR_PYTHON).exists():
        raise RuntimeError(
            f"TripoSR python binary not found at '{TRIPOSR_PYTHON}'. "
            "Please ensure TripoSR virtual environment is set up."
        )

    out_dir = OUTPUTS / f"{img.stem}_{int(time.time())}"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(TRIPOSR_PYTHON),
        str(TRIPOSR_DIR / "run.py"),
        str(img),
        "--output-dir",
        str(out_dir),
        "--model-save-format",
        "glb",
        "--mc-resolution",
        str(mc_resolution),
        "--foreground-ratio",
        str(foreground_ratio),
        "--device",
        TRIPOSR_DEVICE,
    ]
    if no_remove_bg:
        cmd.append("--no-remove-bg")
    if bake_texture:
        cmd.append("--bake-texture")
        cmd.extend(["--texture-resolution", "2048"])

    logger.info(f"⚡ [TripoSR] Starting 3D Reconstruction for {img.name} (Grid: {mc_resolution})")
    start = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(TRIPOSR_DIR),
        capture_output=True,
        text=True,
        timeout=TRIPOSR_TIMEOUT,
        stdin=subprocess.DEVNULL,
    )
    elapsed = round(time.time() - start, 1)

    glbs = sorted(out_dir.rglob("*.glb"))
    if not glbs and proc.returncode != 0:
        err_msg = proc.stderr[-2000:] if proc.stderr else "Subprocess exited with error"
        logger.error(f"❌ [TripoSR] Generation failed after {elapsed}s: {err_msg}")
        raise RuntimeError(f"TripoSR execution failed: {err_msg}")

    if not glbs:
        raise RuntimeError(f"TripoSR finished but no .glb file was produced in {out_dir}.")

    glb_file = str(glbs[0])
    file_size = os.path.getsize(glb_file)
    logger.info(f"✅ [TripoSR] 3D Mesh successfully generated in {elapsed}s: {Path(glb_file).name} ({file_size:,} bytes)")

    if reorient:
        reorient_upright(glb_file)

    return glb_file
