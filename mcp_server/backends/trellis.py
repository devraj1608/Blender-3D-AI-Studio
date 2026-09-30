import os
import time
import shutil
import logging
import hashlib
import tempfile
import secrets
from pathlib import Path

import httpx
import gradio_client.utils as _gc_utils
from gradio_client import Client, handle_file
from gradio_client.client import Endpoint
from gradio_client.exceptions import AppError

# --- Patch gradio_client for full Gradio 5 Space Compatibility ---
_gc_utils.RAW_API_INFO_URL = "gradio_api/info?serialize=False"
_gc_utils.UPLOAD_URL = "gradio_api/upload"
_gc_utils.SSE_URL = "gradio_api/queue/data"
_gc_utils.SSE_DATA_URL = "gradio_api/queue/join"
_gc_utils.SSE_URL_V0 = "gradio_api/queue/join"
_gc_utils.SSE_DATA_URL_V0 = "gradio_api/queue/data"

_orig_json_schema = _gc_utils._json_schema_to_python_type
def _patched_json_schema(schema, defs):
    if not isinstance(schema, dict):
        return "Any"
    return _orig_json_schema(schema, defs)

_orig_get_type = _gc_utils.get_type
def _patched_get_type(schema):
    if not isinstance(schema, dict):
        return "Any"
    return _orig_get_type(schema)

_gc_utils._json_schema_to_python_type = _patched_json_schema
_gc_utils.get_type = _patched_get_type

# Patch Gradio 5 file downloader with correct /gradio_api/file=/ URL structure
def _clean_patched_download(self, x: dict) -> str:
    path = x.get("path", "")
    url_path = f"{self.root_url.rstrip('/')}/gradio_api/file=/{path.lstrip('/')}"
    if self.client.output_dir is not None:
        os.makedirs(self.client.output_dir, exist_ok=True)
    sha = hashlib.sha256()
    temp_dir = Path(tempfile.gettempdir()) / secrets.token_hex(20)
    temp_dir.mkdir(exist_ok=True, parents=True)
    with httpx.stream("GET", url_path, headers=self.client.headers, cookies=self.client.cookies, verify=self.client.ssl_verify, follow_redirects=True, timeout=180.0) as resp:
        resp.raise_for_status()
        dest_temp = temp_dir / Path(path).name
        with open(dest_temp, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=65536):
                sha.update(chunk)
                f.write(chunk)
    directory = Path(self.client.output_dir) / sha.hexdigest()
    directory.mkdir(exist_ok=True, parents=True)
    final_dest = directory / Path(path).name
    shutil.move(dest_temp, final_dest)
    return str(final_dest)

Endpoint._download_file = _clean_patched_download


try:
    from ..config import ROOT, OUTPUTS
except (ImportError, ValueError):
    try:
        from mcp_server.config import ROOT, OUTPUTS
    except ImportError:
        from config import ROOT, OUTPUTS

logger = logging.getLogger("studio.trellis")


def run(
    image_path: str,
    mesh_simplify: float = 0.95,
    texture_size: int = 1024,
    hf_token: str = None,
) -> str:
    """
    Generate high-fidelity 3D mesh with PBR textures using TRELLIS foundation model on NVIDIA A100 ZeroGPU.
    Accepts a HuggingFace user access token for priority ZeroGPU quota.
    """
    img = Path(image_path).expanduser().resolve()
    if not img.is_file():
        raise FileNotFoundError(f"Image not found at {img}")

    out_dir = OUTPUTS / f"{img.stem}_trellis_{int(time.time())}"
    out_dir.mkdir(parents=True, exist_ok=True)
    target_glb = out_dir / "model.glb"

    token = (hf_token or "").strip() or os.getenv("HF_TOKEN", "").strip()
    if not token:
        env_file = ROOT / ".env"
        if env_file.exists():
            try:
                from dotenv import dotenv_values
                token = (dotenv_values(env_file).get("HF_TOKEN") or "").strip()
            except Exception:
                pass

    if token:
        os.environ["HF_TOKEN"] = token
        masked = token[:4] + "..." + token[-4:] if len(token) > 8 else "***"
        logger.info(f"🔑 [TRELLIS] Authenticated with Hugging Face token ({masked}) for priority ZeroGPU compute.")
    else:
        logger.warning("⚠️ [TRELLIS] No Hugging Face token provided. Using public anonymous ZeroGPU queue.")

    logger.info("✨ [TRELLIS] Connecting to Hugging Face space 'trellis-community/TRELLIS'...")
    try:
        client = Client("trellis-community/TRELLIS", hf_token=token if token else None, httpx_kwargs={"timeout": 180.0})
        
        # Step 1: Initialize Session on ZeroGPU
        logger.info("🚀 [TRELLIS] Initializing session on ZeroGPU...")
        client.predict(api_name="/start_session")

        # Step 2: Preprocessing image (background removal & normalization)
        logger.info("🖼️ [TRELLIS] Preprocessing input image on ZeroGPU...")
        try:
            pre_res = client.predict(image=handle_file(str(img)), api_name="/preprocess_image")
            prep_img = pre_res if pre_res and Path(str(pre_res)).is_file() else str(img)
            logger.info(f"✅ [TRELLIS] Image preprocessed: {Path(prep_img).name}")
        except Exception as pe:
            logger.warning(f"⚠️ [TRELLIS] Preprocess warning: {pe}, using original image")
            prep_img = str(img)

        # Step 3: High-fidelity 3D Latent Diffusion Generation (Exact 10 parameters)
        logger.info("⏳ [TRELLIS] Predicting 3D geometry & PBR texture maps on NVIDIA A100 ZeroGPU...")
        res = client.predict(
            image=handle_file(str(prep_img)),
            multiimages=[],
            seed=0,
            ss_guidance_strength=7.5,
            ss_sampling_steps=12,
            slat_guidance_strength=3.0,
            slat_sampling_steps=12,
            multiimage_algo="stochastic",
            mesh_simplify=mesh_simplify,
            texture_size=texture_size,
            api_name="/generate_and_extract_glb",
        )
    except AppError as e:
        err_str = str(e)
        if "ZeroGPU quota" in err_str or "quota" in err_str.lower():
            msg = (
                "Hugging Face ZeroGPU quota reached. "
                "Please enter your free Hugging Face token (hf_...) in Token Settings to unlock your personal ZeroGPU quota."
            )
            logger.error(f"❌ [TRELLIS] {msg}")
            raise RuntimeError(msg)
        logger.error(f"❌ [TRELLIS] Inference error: {err_str}")
        raise RuntimeError(f"TRELLIS inference failed: {err_str}")
    except Exception as e:
        logger.error(f"❌ [TRELLIS] Connection error: {e}")
        raise RuntimeError(f"TRELLIS connection error: {e}")

    download_glb_path = res[2] if len(res) > 2 else res[1]
    if not download_glb_path or not Path(download_glb_path).is_file():
        raise RuntimeError("TRELLIS finished but did not return a valid GLB file.")

    shutil.copyfile(download_glb_path, target_glb)
    file_size = os.path.getsize(target_glb)
    logger.info(f"✅ [TRELLIS] High-fidelity 3D model successfully generated & saved: {target_glb.name} ({file_size:,} bytes)")
    return str(target_glb)
